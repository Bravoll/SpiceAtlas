"""Windows launch progress and tray controller. All Tk calls stay on its UI thread."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import threading
import time
from .browser import open_url

from atlas.launcher_protocol import APP_ID, project_key
from .core import Starter, local_status
from .interactions import TrayClicks
from .win_native import InstanceMutex, ProcessJob, Tray, chinese_ui, enable_dpi, message

EN = {
 'title':'香料图鉴 - Spice Atlas', 'subtitle':'Your local botanical reading desk',
 'environment':'Checking Python and existing service', 'prepare':'Preparing the local environment',
 'dependencies':'Checking and installing packages', 'verify':'Verifying application packages',
 'catalogue':'Preparing the catalogue', 'server':'Starting the background service',
 'waiting':'Waiting for the local page to become ready', 'browser':'Opening your browser',
 'ready':'Spice Atlas is ready', 'milestones':'Stage progress · package downloads may take a while',
 'log_end':'Jump to latest', 'browser_failed':'The page is ready. Automatic browser opening failed; use Open Spice Atlas.',
 'open':'Open Spice Atlas', 'status':'Show / hide window', 'visibility':'Show / hide window', 'logs':'Open startup log',
 'stop':'Stop service & exit', 'hide':'Hide to tray', 'details':'Show details', 'hide_details':'Hide details', 'pause':'Pause service', 'resume':'Resume service', 'paused':'Service paused · resume from this window or tray', 'control_error':'Could not change the service state: ',
 'running':'Running in the background. Use the tray icon to open or stop it.',
 'stopping':'Saving state and stopping the service…', 'error':'Could not start. Details are in the startup log.',
 'duplicate':'Spice Atlas is already starting. Open its tray icon to see progress.',
 'existing':'This folder already has a running service. The existing page will open.',
 'no_tray':'This status window remains available while the service runs.',
}
ZH = {
 'title':'香料图鉴 - Spice Atlas', 'subtitle':'在本机打开一页植物与风味的图鉴',
 'environment':'检查 Python 与已有服务', 'prepare':'准备本地运行环境',
 'dependencies':'检查和安装依赖包', 'verify':'验证程序依赖', 'catalogue':'准备馆藏数据库',
 'server':'启动后台服务', 'waiting':'等待本地网页就绪', 'browser':'打开浏览器',
 'ready':'香料图鉴已就绪', 'milestones':'阶段进度 · 首次下载依赖可能需要一些时间',
 'log_end':'跳到最新', 'browser_failed':'网页已就绪，但未能自动打开浏览器；请点击“打开香料图鉴”。',
 'open':'打开香料图鉴', 'status':'显示／隐藏界面', 'visibility':'显示／隐藏界面', 'logs':'打开启动日志',
 'stop':'停止服务并退出', 'hide':'收起到托盘', 'details':'显示详细过程', 'hide_details':'隐藏详细过程', 'pause':'暂停服务', 'resume':'继续服务', 'paused':'服务已暂停 · 可从此窗口或托盘继续', 'control_error':'服务状态未能更改：',
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
        self.details_visible=False
        self.paused=False
        self.control_pending=False
        self.compact_size=(620,440)
        self.expanded_size=(760,600)
        self.root = tk.Tk()
        self.root.title(text['title'])
        self.root.configure(bg='#f2f6ee')
        self.root.geometry('620x440')
        self.root.minsize(580,420)
        self.root.resizable(True,True)
        self.root.protocol('WM_DELETE_WINDOW',self.hide)
        icon = self.root_path/'static/atlas-icon.ico'
        try:
            self.root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
        self.root.update_idletasks()
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('Atlas.Horizontal.TProgressbar',background='#355a3b',troughcolor='#dce6d5',borderwidth=0,lightcolor='#355a3b',darkcolor='#355a3b')
        font = 'Microsoft YaHei UI' if text is ZH else 'Segoe UI'
        self.root.option_add('*Font',(font,10))
        style.configure('Atlas.TButton',font=(font,10),padding=(14,9),background='#edf2e8',foreground='#355a3b',bordercolor='#c3d0bb',lightcolor='#edf2e8',darkcolor='#edf2e8',focuscolor='#668367',borderwidth=1,relief='flat')
        style.map('Atlas.TButton',background=[('active','#dfead8'),('pressed','#d0dfc8')],foreground=[('disabled','#87917f')],bordercolor=[('active','#7d9778')])
        style.configure('Primary.Atlas.TButton',background='#355a3b',foreground='#fbfcf8',lightcolor='#355a3b',darkcolor='#355a3b',bordercolor='#355a3b')
        style.map('Primary.Atlas.TButton',background=[('disabled','#dce4d5'),('active','#476e4b'),('pressed','#294c2f')],foreground=[('disabled','#87917f')])
        style.configure('Stop.Atlas.TButton',foreground='#725341')
        panel=self.panel=tk.Frame(self.root,bg='#f2f6ee',padx=26,pady=22)
        panel.pack(fill='both',expand=True)
        tk.Label(panel,text='SPICE ATLAS',font=('Georgia',22),fg='#355a3b',bg='#f2f6ee',anchor='w').pack(fill='x')
        self.subtitle_label=tk.Label(panel,text=text['subtitle'],fg='#62715e',bg='#f2f6ee',anchor='w',justify='left',wraplength=540)
        self.subtitle_label.pack(fill='x',pady=(6,23))
        status_row=tk.Frame(panel,bg='#f2f6ee');status_row.pack(fill='x')
        self.status=tk.StringVar(value=text['environment'])
        self.percent=tk.StringVar(value='0%')
        self.status_label=tk.Label(status_row,textvariable=self.status,fg='#2e3d2f',bg='#f2f6ee',anchor='w',justify='left',wraplength=475)
        self.status_label.pack(side='left',fill='x',expand=True)
        tk.Label(status_row,textvariable=self.percent,fg='#62715e',bg='#f2f6ee').pack(side='right')
        self.progress=ttk.Progressbar(panel,style='Atlas.Horizontal.TProgressbar',maximum=100,length=480)
        self.progress.pack(fill='x',pady=(14,10))
        self.note=tk.StringVar(value=text['milestones'])
        self.note_label=tk.Label(panel,textvariable=self.note,fg='#62715e',bg='#f2f6ee',anchor='w',wraplength=540,justify='left')
        self.note_label.pack(fill='x')
        buttons=tk.Frame(panel,bg='#f2f6ee');buttons.pack(fill='x',pady=(22,0))
        buttons.columnconfigure((0,1),weight=1,uniform='actions')
        self.open_button=ttk.Button(buttons,text=text['open'],style='Primary.Atlas.TButton',command=self.open_page,state='disabled')
        self.open_button.grid(row=0,column=0,sticky='ew',padx=(0,5),pady=(0,8))
        self.details_button=ttk.Button(buttons,text=text['details'],style='Atlas.TButton',command=self.details)
        self.details_button.grid(row=0,column=1,sticky='ew',padx=(5,0),pady=(0,8))
        self.pause_button=ttk.Button(buttons,text=text['pause'],style='Atlas.TButton',command=self.toggle_pause,state='disabled')
        self.pause_button.grid(row=1,column=0,sticky='ew',padx=(0,5))
        self.stop_button=ttk.Button(buttons,text=text['stop'],style='Stop.Atlas.TButton',command=self.stop)
        self.stop_button.grid(row=1,column=1,sticky='ew',padx=(5,0))
        self.log_panel=tk.Frame(panel,bg='#f2f6ee')
        log_tools=tk.Frame(self.log_panel,bg='#f2f6ee');log_tools.pack(fill='x',pady=(0,5))
        ttk.Button(log_tools,text=text['log_end'],style='Atlas.TButton',command=lambda:self.log_view.see('end')).pack(side='right')
        log_body=tk.Frame(self.log_panel,bg='#f2f6ee');log_body.pack(fill='both',expand=True)
        self.log_view=tk.Text(log_body,height=8,bg='#fbfcf8',fg='#344932',relief='flat',highlightthickness=1,highlightbackground='#d6e0cf',font=('Consolas',9),wrap='word',state='disabled')
        self.log_scrollbar=ttk.Scrollbar(log_body,orient='vertical',command=self.log_view.yview)
        self.log_view.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_scrollbar.pack(side='right',fill='y');self.log_view.pack(side='left',fill='both',expand=True)
        self.root.bind('<Configure>',self.resize_labels,add='+')
        self.fit_window(initial=True)
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
        self.tray_clicks=TrayClicks(self.root,self.toggle_visibility,self.open_page,getattr(self.tray,'click_delay',500))
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
        self.set_details(not self.details_visible)

    def resize_labels(self,event):
        if event.widget is not self.root:return
        width=max(280,event.width-56)
        self.note_label.configure(wraplength=width)
        self.subtitle_label.configure(wraplength=width)
        self.status_label.configure(wraplength=max(220,width-65))

    def fit_window(self,initial=False,preferred=None):
        """Use Tk's measured font/DPI requirements, never crop the action rows."""
        if preferred and hasattr(self,'note_label'):
            self.note_label.configure(wraplength=max(280,preferred[0]-56))
            self.subtitle_label.configure(wraplength=max(280,preferred[0]-56))
        self.root.update_idletasks()
        width=max(580,self.panel.winfo_reqwidth())
        height=max(420,self.panel.winfo_reqheight())
        self.root.minsize(width,height)
        size=preferred or (self.root.winfo_width(),self.root.winfo_height())
        target=(max(width,size[0]),max(height,size[1]))
        if initial:
            self.compact_size=target
            x=max(0,(self.root.winfo_screenwidth()-target[0])//2)
            y=max(0,(self.root.winfo_screenheight()-target[1])//2)
            self.root.geometry(f'{target[0]}x{target[1]}+{x}+{y}')
        else:self.root.geometry(f'{target[0]}x{target[1]}')

    def set_details(self,visible):
        if self.details_visible==visible:return
        self.keep_visible=True
        if visible:
            self.compact_size=(self.root.winfo_width(),self.root.winfo_height())
            getattr(self,'log_panel',self.log_view).pack(fill='both',expand=True,pady=(16,0))
            size=self.expanded_size
        else:
            self.expanded_size=(self.root.winfo_width(),self.root.winfo_height())
            getattr(self,'log_panel',self.log_view).pack_forget()
            size=self.compact_size
        self.details_visible=visible
        self.details_button.configure(text=self.text['hide_details' if visible else 'details'])
        if hasattr(self,'panel'):self.fit_window(preferred=size)
        else:self.root.geometry(f'{size[0]}x{size[1]}')

    def toggle_visibility(self):
        if self.stopping:return
        if self.root.state() in {'withdrawn','iconic'}:self.show()
        else:self.hide()

    def toggle_pause(self):
        if not self.ready or self.stopping or self.control_pending:return
        self.control_pending=True
        self.pause_button.configure(state='disabled')
        target=not self.paused
        def apply():
            try:
                value=self.starter.set_paused(target)
                self.send({'kind':'control','paused':value['paused']})
            except Exception as exc:
                self.send({'kind':'control_error','message':str(exc)})
        threading.Thread(target=apply,daemon=True).start()

    def append_log(self,line):
        follow=self.log_view.yview()[1]>.97
        self.log_view.configure(state='normal')
        self.log_view.insert('end',line+'\n')
        lines=int(self.log_view.index('end-1c').split('.')[0])
        if lines>5000:self.log_view.delete('1.0',f'{lines-5000}.0')
        if follow:self.log_view.see('end')
        self.log_view.configure(state='disabled')

    def show(self):
        self.keep_visible=True
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

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
            open_url(self.starter.url)

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
        self.pause_button.configure(state='disabled')
        self.tray_clicks.cancel()
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
                self.append_log(event['text'])
            elif kind=='stage':
                self.status.set(self.text[event['stage']])
                self.percent.set(str(event['percent'])+'%')
                self.progress.stop()
                self.progress.configure(mode='determinate',value=event['percent'])
                if event.get('busy'):
                    self.progress.configure(mode='indeterminate')
                    self.progress.start(22)
                if self.tray:
                    self.tray.status(self.text[event['stage']])
            elif kind=='ready':
                self.ready=True
                self.pause_button.configure(state='normal')
                if self.tray:self.tray.service_ready=True
                self.open_button.configure(state='normal')
                self.note.set(self.text['running' if event['browser_opened'] else 'browser_failed']+'\n'+event['url'])
                self.fit_window()
                if self.tray:
                    self.tray.notify(self.text['ready']+'\n'+event['url'])
                    if event['browser_opened']:
                        self.root.after(1800,lambda:self.hide() if not self.keep_visible else None)
            elif kind=='error':
                self.progress.stop()
                self.status.set(self.text['error'])
                self.note.set(event['message'])
                self.show()
                self.set_details(True)
                if self.tray:
                    self.tray.notify(self.text['error'])
            elif kind=='existing':
                open_url(event['url'])
                self.note.set(self.text['existing'])
                self.root.after(1000,self.stop)
            elif kind=='control':
                self.control_pending=False
                if self.stopping:continue
                self.paused=event['paused']
                self.pause_button.configure(state='normal',text=self.text['resume' if self.paused else 'pause'])
                self.status.set(self.text['paused' if self.paused else 'ready'])
                self.note.set(self.text['paused' if self.paused else 'running']+'\n'+self.starter.url)
                self.fit_window()
                if self.tray:
                    self.tray.paused=self.paused
                    self.tray.status(self.text['paused' if self.paused else 'ready'])
            elif kind=='control_error':
                self.control_pending=False
                if not self.stopping:
                    self.pause_button.configure(state='normal')
                    self.note.set(self.text['control_error']+event['message'])
                    self.append_log(event['message'])
            elif kind=='tray':
                action=event['action']
                if action.startswith('click:'):self.tray_clicks.receive(action.split(':',1)[1])
                else:{'open':self.open_page,'visibility':self.toggle_visibility,'logs':self.open_log,'pause':self.toggle_pause,'stop':self.stop}[action]()
            elif kind=='exit':
                if self.tray:
                    self.tray.close()
                self.mutex.close()
                self.root.destroy()
                return
        if self.ready and not self.stopping and self.starter.server and self.starter.server.poll() is not None:
            self.ready=False
            self.pause_button.configure(state='disabled')
            if self.tray:self.tray.service_ready=False
            self.open_button.configure(state='disabled')
            self.status.set(self.text['error'])
            self.show()
            self.set_details(True)
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
                open_url(f"http://127.0.0.1:{int(session['port'])}")
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
