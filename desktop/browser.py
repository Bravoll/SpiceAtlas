"""Open the owned loopback page without depending on a console or proxy routing."""
import os,time,threading,webbrowser
from urllib.parse import urlsplit

def open_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'}:return False
    if os.name=='nt':
        try:os.startfile(url);return True
        except OSError:pass
    try:return bool(webbrowser.open(url,new=2))
    except Exception:return False

def wait_and_open(url,status_reader,opener=open_url,timeout=120,cancelled=None,poll=.2):
    cancelled=cancelled or threading.Event();deadline=time.monotonic()+timeout
    while time.monotonic()<deadline and not cancelled.is_set():
        try:
            if status_reader():return bool(opener(url))
        except (OSError,ValueError):pass
        cancelled.wait(min(poll,max(0,deadline-time.monotonic())))
    return False
