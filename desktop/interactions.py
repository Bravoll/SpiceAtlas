"""Tray click interpretation separated from native messages for reliable testing."""
import time

class TrayClicks:
    def __init__(self, scheduler, toggle, open_browser, delay=500, clock=time.monotonic):
        self.scheduler,self.toggle,self.open_browser=scheduler,toggle,open_browser
        self.delay,self.clock=max(150,int(delay)),clock
        self.timer=None
        self.ignore_until=0
        self.last_select=-10

    def cancel(self):
        if self.timer is not None:
            self.scheduler.after_cancel(self.timer)
            self.timer=None

    def receive(self,kind):
        now=self.clock()
        if kind=='keyboard':
            self.cancel();self.toggle();return
        if kind=='double':
            self.cancel()
            if now<self.ignore_until:return
            self.ignore_until=now+self.delay/1000
            self.open_browser();return
        if now<self.ignore_until or now-self.last_select<.045:return
        self.last_select=now
        if self.timer is not None:
            self.receive('double');return
        def single():
            self.timer=None
            self.toggle()
        self.timer=self.scheduler.after(self.delay+25,single)
