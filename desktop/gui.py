"""Windows launch progress and tray controller. All Tk calls stay on its UI thread."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import threading
import time
import webbrowser

from atlas.launcher_protocol import APP_ID, project_key
from .core import Starter, local_status
from .win_native import InstanceMutex, ProcessJob, Tray, chinese_ui, enable_dpi, message

EN = {
 'title':'Spice Atlas · Launch', 'subtitle':'Your local botanical reading desk',
 'environment':'Checking Python and existing service', 'prepare':'Preparing the local environment',
 'dependencies':'Checking and installing packages', 'verify':'Verifying application packages',
 'catalogue':'Preparing the catalogue', 'server':'Starting the background service',
 'waiting':'Waiting for the local page to become ready', 'browser':'Opening your browser',
 'ready':'Spice Atlas is ready', 'milestones':'Stage progress · package downloads may take a while',
 'open':'Open Spice Atlas', 'status':'Startup status', 'logs':'Open startup log',
 'stop':'Stop service & exit', 'hide':'Hide to tray', 'details':'Show details',
 'running':'Running in the background. Use the tray icon to open or stop it.',
 'stopping':'Saving state and stopping the service…', 'error':'Could not start. Details are in the startup log.',
 'duplicate':'Spice Atlas is already starting. Open its tray icon to see progress.',
 'existing':'This folder already has a running service. The existing page will open.',
 'no_tray':'This status window remains available while the service runs.',
}
ZH = {
 'title':'香料图鉴 · 启动', 'subtitle':'在本机打开一页植物与风味的图鉴',
 'environment':'检查 Python 与已有服务', 'prepare':'准备本地运行环境',
 'dependencies':'检查和安装依赖包', 'verify':'验证程序依赖', 'catalogue':'准备馆藏数据库',
 'server':'启动后台服务', 'waiting':'等待本地网页就绪', 'browser':'打开浏览器',
 'ready':'香料图鉴已就绪', 'milestones':'阶段进度 · 首次下载依赖可能需要一些时间',
 'open':'打开香料图鉴', 'status':'查看启动状态', 'logs':'打开启动日志',
 'stop':'停止服务并退出', 'hide':'收起到托盘', 'details':'显示详细过程',
 'running':'正在后台运行，可通过托盘图标打开网页或停止服务。',
 'stopping':'正在保存状态并停止服务…', 'error':'启动未完成，具体原因已记录到启动日志。',
 'duplicate':'香料图鉴正在启动，请通过已有的托盘图标查看进度。',
 'existing':'这个目录已有运行中的服务，将打开已有网页。',
 'no_tray':'服务运行期间可通过此状态窗口进行操作。',
}


class Window:
    def __init__(self, root_path, mutex, text):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.text, self.mutex = tk, ttk, text, mutex
        self.events = queue.Queue(maxsize=1500)
        self.root_path, self.ready, self.stopping = Path(root_path), False, False
        self.keep_visible, self.last_open = False, 0.0
        self.root = tk.Tk()
        self.root.title(text['title'])
        self.root.configure(bg='#f2f6ee')
        self.root.geometry('560x320')
        self.root.minsize(520,320)
        self.root.resizable(True,True)
        self.root.protocol('WM_DELETE_WINDOW',self.hide)
        icon = self.root_path/'static/atlas-icon.ico'
        try:
            self.root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
        self.root.update_idletasks()
        x=max(0,(self.root.winfo_screenwidth()-560)//2)
        y=max(0,(self.root.winfo_screenheight()-320)//2)
        self.root.geometry(f'560x320+{x}+{y}')
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('Atlas.Horizontal.TProgressbar',background='#355a3b',troughcolor='#dce6d5',borderwidth=0,lightcolor='#355a3b',darkcolor='#355a3b')
        font = 'Microsoft YaHei UI' if text is ZH else 'Segoe UI'
        self.root.option_add('*Font',(font,10))
        panel=tk.Frame(self.root,bg='#f2f6ee',padx=30,pady=24)
        panel.pack(fill='both',expand=True)
        tk.Label(panel,text='SPICE ATLAS',font=('Georgia',22),fg='#355a3b',bg='#f2f6ee',anchor='w').pack(fill='x')
        tk.Label(panel,text=text['subtitle'],fg='#62715e',bg='#f2f6ee',anchor='w').pack(fill='x',pady=(6,25))
        status_row=tk.Frame(panel,bg='#f2f6ee');status_row.pack(fill='x')
        self.status=tk.StringVar(value=text['environment'])
        self.percent=tk.StringVar(value='0%')
        tk.Label(status_row,textvariable=self.status,fg='#2e3d2f',bg='#f2f6ee',anchor='w').pack(side='left',fill='x',expand=True)
        tk.Label(status_row,textvariable=self.percent,fg='#62715e',bg='#f2f6ee').pack(side='right')
        self.progress=ttk.Progressbar(panel,style='Atlas.Horizontal.TProgressbar',maximum=100,length=480)
        self.progress.pack(fill='x',pady=(14,10))
        self.note=tk.StringVar(value=text['milestones'])
        tk.Label(panel,textvariable=self.note,fg='#62715e',bg='#f2f6ee',anchor='w',wraplength=480,justify='left').pack(fill='x')
        buttons=tk.Frame(panel,bg='#f2f6ee');buttons.pack(fill='x',pady=(22,0))
        self.open_button=ttk.Button(buttons,text=text['open'],command=self.open_page,state='disabled')
        self.open_button.pack(side='left')
        ttk.Button(buttons,text=text['details'],command=self.details).pack(side='left',padx=8)
        self.stop_button=ttk.Button(buttons,text=text['stop'],command=self.stop)
        self.stop_button.pack(side='right')
        self.log_view=tk.Text(panel,height=12,bg='#fbfcf8',fg='#344932',relief='flat',font=('Consolas',9),wrap='word',state='disabled')
        self.tray=None
        try:
            self.tray=Tray(self.root,icon,lambda action:self.send({'kind':'tray','action':action}),text)
        except OSError:
            self.note.set(text['no_tray'])
        try:
            job=ProcessJob()
        except OSError:
            job=None
        self.starter=Starter(root_path,self.send,job=job)
        self.worker=threading.Thread(target=self.starter.run,daemon=True)
        self.worker.start()
        self.root.after(70,self.pump)

    def send(self, value):
        try:
            self.events.put_nowait(value)
        except queue.Full:
            if value.get('kind')!='log':
                try:
                    self.events.get_nowait()
                    self.events.put_nowait(value)
                except queue.Empty:
                    pass

    def details(self):
        self.keep_visible=True
        self.log_view.pack(fill='both',expand=True,pady=(16,0))
        self.root.geometry('680x560')

    def show(self):
        self.keep_visible=True
        self.root.deiconify()
        self.root.lift()

    def hide(self):
        if self.stopping:
            return
        if self.tray:
            self.root.withdraw()
        else:
            self.root.iconify()

    def open_page(self):
        if self.stopping:
            return
        if not self.ready:
            self.show()
            return
        now=time.monotonic()
        if now-self.last_open>.5:
            self.last_open=now
            webbrowser.open(self.starter.url)

    def open_log(self):
        os.startfile(self.starter.log.path)

    def stop(self):
        if self.stopping:
            return
        self.stopping=True
        self.root.deiconify()
        self.status.set(self.text['stopping'])
        self.stop_button.configure(state='disabled')
        self.open_button.configure(state='disabled')
        self.progress.configure(mode='indeterminate')
        self.progress.start(18)
        def finish():
            self.starter.cancelled.set()
            self.starter.stop()
            self.worker.join(timeout=5)
            self.starter.close()
            self.send({'kind':'exit'})
        threading.Thread(target=finish,daemon=True).start()

    def pump(self):
        for _ in range(200):
            try:
                event=self.events.get_nowait()
            except queue.Empty:
                break
            kind=event['kind']
            if kind=='log':
                self.log_view.configure(state='normal')
                self.log_view.insert('end',event['text']+'\n')
                self.log_view.see('end')
                self.log_view.configure(state='disabled')
            elif kind=='stage':
                self.status.set(self.text[event['stage']])
                self.percent.set(str(event['percent'])+'%')
                self.progress.stop()
                self.progress.configure(mode='determinate',value=event['percent'])
                if event.get('busy'):
                    self.progress.configure(mode='indeterminate')
                    self.progress.start(22)
                if self.tray:
                    self.tray.status('Spice Atlas · '+self.text[event['stage']])
            elif kind=='ready':
                self.ready=True
                self.open_button.configure(state='normal')
                self.note.set(self.text['running']+'\n'+event['url'])
                if self.tray:
                    self.tray.notify(self.text['ready']+'\n'+event['url'])
                    if event['browser_opened']:
                        self.root.after(1800,lambda:self.hide() if not self.keep_visible else None)
            elif kind=='error':
                self.progress.stop()
                self.status.set(self.text['error'])
                self.note.set(event['message'])
                self.show()
                self.details()
                if self.tray:
                    self.tray.notify(self.text['error'])
            elif kind=='existing':
                webbrowser.open(event['url'])
                self.note.set(self.text['existing'])
                self.root.after(1000,self.stop)
            elif kind=='tray':
                {'open':self.open_page,'status':self.show,'logs':self.open_log,'stop':self.stop}[event['action']]()
            elif kind=='exit':
                if self.tray:
                    self.tray.close()
                self.mutex.close()
                self.root.destroy()
                return
        if self.ready and not self.stopping and self.starter.server and self.starter.server.poll() is not None:
            self.ready=False
            self.open_button.configure(state='disabled')
            self.status.set(self.text['error'])
            self.show()
            self.details()
        self.root.after(70,self.pump)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.starter.cancelled.set()
            self.starter.stop()
            self.worker.join(timeout=5)
            self.starter.close()
            if self.tray:
                self.tray.close()
            try:
                self.root.destroy()
            except self.tk.TclError:
                pass


def main():
    if os.name!='nt':
        raise SystemExit('Use run.sh or python launch.py on this operating system.')
    root=Path(__file__).resolve().parents[1]
    enable_dpi()
    text=ZH if chinese_ui() else EN
    mutex=InstanceMutex(project_key(root))
    if mutex.existing:
        try:
            session=json.loads((root/'data/launcher/session.json').read_text())
            status=local_status(session['port'])
            if status and status.get('app_id')==APP_ID and status.get('project_key')==project_key(root):
                webbrowser.open(f"http://127.0.0.1:{int(session['port'])}")
            else:
                message(text['duplicate'])
        except (OSError,ValueError,KeyError):
            message(text['duplicate'])
        finally:
            mutex.close()
        return
    try:
        try:
            Window(root,mutex,text).run()
        except ImportError:
            message('Python with Tcl/Tk is required for this launcher. Install the standard Python distribution, or use run_console.cmd.\n\n启动窗口需要 Tcl/Tk。可安装标准 Python，或使用 run_console.cmd。')
    except Exception as exc:
        message('Spice Atlas could not start. Use run_console.cmd for diagnostics.\n\n'+str(exc)[:250])
    finally:
        mutex.close()
