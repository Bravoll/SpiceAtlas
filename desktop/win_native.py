"""Small Win32 adapters. No PowerShell policy changes or third-party tray dependency."""
from __future__ import annotations
import ctypes as C
import os
import time

APP_NAME='香料图鉴 - Spice Atlas'


def _windows():
    if os.name != 'nt':
        raise OSError('Windows desktop integration is only available on Windows.')
    return C.WinDLL('kernel32', use_last_error=True), C.WinDLL('user32', use_last_error=True)


class InstanceMutex:
    def __init__(self, key):
        self.kernel, _ = _windows()
        self.kernel.CreateMutexW.argtypes = [C.c_void_p, C.c_int, C.c_wchar_p]
        self.kernel.CreateMutexW.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\SpiceAtlas_'+key)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        self.existing = C.get_last_error() == 183

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class ProcessJob:
    def __init__(self):
        self.kernel, _ = _windows()
        class Basic(C.Structure):
            _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64), ('flags', C.c_uint32),
                        ('min_working_set', C.c_size_t), ('max_working_set', C.c_size_t),
                        ('active_processes', C.c_uint32), ('affinity', C.c_size_t),
                        ('priority', C.c_uint32), ('scheduling', C.c_uint32)]
        class IO(C.Structure):
            _fields_ = [(x, C.c_uint64) for x in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(C.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', C.c_size_t),
                        ('job_memory', C.c_size_t), ('peak_process_memory', C.c_size_t), ('peak_job_memory', C.c_size_t)]
        self.kernel.CreateJobObjectW.argtypes = [C.c_void_p, C.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = C.c_void_p
        self.kernel.SetInformationJobObject.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_uint32]
        self.kernel.AssignProcessToJobObject.argtypes = [C.c_void_p, C.c_void_p]
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        limit = Extended()
        limit.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, C.byref(limit), C.sizeof(limit)):
            self.close()
            raise C.WinError(C.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise C.WinError(C.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class Tray:
    """Uses the Tk top-level's message loop; all UI work is queued for Tk's thread."""
    MESSAGE = 0x8000+43

    def __init__(self, root, icon, send, labels):
        _, self.user = _windows()
        self.shell = C.WinDLL('shell32', use_last_error=True)
        self.root, self.send, self.labels = root, send, labels
        self.hwnd = None
        self.old_proc = None
        self.icon = None
        self.added = False
        self.tooltip=APP_NAME
        self.paused=False
        self.service_ready=False
        self.last_menu=-10.0
        self.user.GetDoubleClickTime.restype=C.c_uint
        self.click_delay=int(self.user.GetDoubleClickTime())
        self.user.GetParent.argtypes = [C.c_void_p]
        self.user.GetParent.restype = C.c_void_p
        self.user.LoadImageW.argtypes = [C.c_void_p,C.c_wchar_p,C.c_uint,C.c_int,C.c_int,C.c_uint]
        self.user.LoadImageW.restype = C.c_void_p
        self.user.DestroyIcon.argtypes = [C.c_void_p]
        self.user.RegisterWindowMessageW.argtypes = [C.c_wchar_p]
        self.user.RegisterWindowMessageW.restype = C.c_uint
        self.user.CreatePopupMenu.restype = C.c_void_p
        self.user.AppendMenuW.argtypes = [C.c_void_p,C.c_uint,C.c_size_t,C.c_wchar_p]
        self.user.TrackPopupMenu.argtypes = [C.c_void_p,C.c_uint,C.c_int,C.c_int,C.c_int,C.c_void_p,C.c_void_p]
        self.user.TrackPopupMenu.restype = C.c_uint
        self.user.DestroyMenu.argtypes = [C.c_void_p]
        self.user.SetForegroundWindow.argtypes = [C.c_void_p]
        self.user.PostMessageW.argtypes = [C.c_void_p,C.c_uint,C.c_size_t,C.c_ssize_t]
        self.user.CallWindowProcW.argtypes = [C.c_void_p,C.c_void_p,C.c_uint,C.c_size_t,C.c_ssize_t]
        self.user.CallWindowProcW.restype = C.c_ssize_t
        self.set_proc = getattr(self.user, 'SetWindowLongPtrW', self.user.SetWindowLongW)
        self.set_proc.argtypes = [C.c_void_p,C.c_int,C.c_ssize_t]
        self.set_proc.restype = C.c_ssize_t
        class GUID(C.Structure):
            _fields_ = [('a',C.c_uint32),('b',C.c_uint16),('c',C.c_uint16),('d',C.c_ubyte*8)]
        class NID(C.Structure):
            _fields_ = [('cbSize',C.c_uint32),('hWnd',C.c_void_p),('uID',C.c_uint),
                        ('uFlags',C.c_uint),('uCallbackMessage',C.c_uint),('hIcon',C.c_void_p),
                        ('szTip',C.c_wchar*128),('dwState',C.c_uint32),('dwStateMask',C.c_uint32),
                        ('szInfo',C.c_wchar*256),('uVersion',C.c_uint),('szInfoTitle',C.c_wchar*64),
                        ('dwInfoFlags',C.c_uint32),('guidItem',GUID),('hBalloonIcon',C.c_void_p)]
        self.NID = NID
        self.shell.Shell_NotifyIconW.argtypes = [C.c_uint,C.POINTER(NID)]
        self.shell.Shell_NotifyIconW.restype = C.c_int
        root.update_idletasks()
        self.hwnd = self.user.GetParent(root.winfo_id()) or root.winfo_id()
        self.icon = self.user.LoadImageW(None, str(icon), 1, 0, 0, 0x10|0x40)
        if not self.icon:
            raise OSError('Project icon could not be loaded.')
        self.taskbar_created = self.user.RegisterWindowMessageW('TaskbarCreated')
        callback = C.WINFUNCTYPE(C.c_ssize_t,C.c_void_p,C.c_uint,C.c_size_t,C.c_ssize_t)
        def wndproc(hwnd, message, wparam, lparam):
            try:
                if message == self.MESSAGE:
                    event = lparam & 0xffff
                    if event==0x203:
                        self.send('click:double')
                    elif event in (0x400,0x202):
                        self.send('click:single')
                    elif event==0x401:
                        self.send('click:keyboard')
                    elif event in (0x7b,0x205):
                        if time.monotonic()-self.last_menu>.3:
                            self.last_menu=time.monotonic();self.menu()
                    return 0
                if message == self.taskbar_created:
                    self.add()
            except Exception:
                pass
            return self.user.CallWindowProcW(self.old_proc,hwnd,message,wparam,lparam)
        self.callback = callback(wndproc)
        C.set_last_error(0)
        self.old_proc = self.set_proc(self.hwnd,-4,C.cast(self.callback,C.c_void_p).value)
        if not self.old_proc and C.get_last_error():
            self.user.DestroyIcon(self.icon)
            raise C.WinError(C.get_last_error())
        if not self.add():
            self.close()
            raise OSError('The notification area is unavailable.')

    def data(self):
        data = self.NID()
        data.cbSize, data.hWnd, data.uID = C.sizeof(data), self.hwnd, 1
        return data

    def add(self):
        data = self.data()
        data.uFlags, data.uCallbackMessage, data.hIcon = 1|2|4|0x80, self.MESSAGE, self.icon
        data.szTip = self.tooltip[:127]
        self.added = bool(self.shell.Shell_NotifyIconW(0,C.byref(data)))
        if self.added:
            data.uVersion = 4
            self.shell.Shell_NotifyIconW(4,C.byref(data))
        return self.added

    def status(self, text):
        self.tooltip=APP_NAME+' · '+text if not text.startswith(APP_NAME) else text
        if self.added:
            data = self.data()
            data.uFlags, data.szTip = 4|0x80, self.tooltip[:127]
            self.shell.Shell_NotifyIconW(1,C.byref(data))

    def notify(self, text):
        if self.added:
            data = self.data()
            data.uFlags, data.szInfoTitle, data.szInfo, data.dwInfoFlags = 0x10|4|0x80, APP_NAME, text[:255], 1
            data.szTip=self.tooltip[:127]
            self.shell.Shell_NotifyIconW(1,C.byref(data))

    def menu(self):
        class Point(C.Structure):
            _fields_ = [('x',C.c_int32),('y',C.c_int32)]
        position = Point()
        self.user.GetCursorPos(C.byref(position))
        menu = self.user.CreatePopupMenu()
        try:
            for item,key in ((1,'visibility'),(2,'open'),(3,'logs')):
                self.user.AppendMenuW(menu,0,item,self.labels[key])
            self.user.AppendMenuW(menu,0 if self.service_ready else 1,4,self.labels['resume' if self.paused else 'pause'])
            self.user.AppendMenuW(menu,0x800,0,None)
            self.user.AppendMenuW(menu,0,5,self.labels['stop'])
            self.user.SetForegroundWindow(self.hwnd)
            selected = self.user.TrackPopupMenu(menu,0x100|0x80|2,position.x,position.y,0,self.hwnd,None)
            self.user.PostMessageW(self.hwnd,0,0,0)
            if selected:
                self.send({1:'visibility',2:'open',3:'logs',4:'pause',5:'stop'}[selected])
        finally:
            self.user.DestroyMenu(menu)

    def close(self):
        if self.added:
            self.shell.Shell_NotifyIconW(2,C.byref(self.data()))
            self.added = False
        if self.old_proc:
            self.set_proc(self.hwnd,-4,self.old_proc)
            self.old_proc = None
        if self.icon:
            self.user.DestroyIcon(self.icon)
            self.icon = None


def message(text):
    _, user = _windows()
    user.MessageBoxW.argtypes = [C.c_void_p,C.c_wchar_p,C.c_wchar_p,C.c_uint]
    user.MessageBoxW(None,text,'Spice Atlas',0x40)


def chinese_ui():
    kernel, _ = _windows()
    return kernel.GetUserDefaultUILanguage() & 0x3ff == 4


def enable_dpi():
    _, user = _windows()
    try:
        user.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
        user.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except AttributeError:
        user.SetProcessDPIAware()
