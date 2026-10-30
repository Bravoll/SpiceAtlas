"""Start the local app and open its page after the server becomes ready."""
import argparse
import threading
import time
import urllib.request
import webbrowser

import uvicorn
from main import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--managed", action="store_true", help="Owned by the windowed desktop launcher")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    print("香料图鉴：" + url)
    print("关闭此窗口或按 Ctrl+C 停止服务。")
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=args.port,log_level="warning"))
    if args.managed:
        app.state.launcher_shutdown=lambda:setattr(server,'should_exit',True)
    if not args.no_browser:
        from desktop.browser import wait_and_open
        from desktop.core import local_status
        from atlas.launcher_protocol import APP_ID,project_key
        from pathlib import Path
        stopped=threading.Event()
        def owned_ready():
            status=local_status(args.port)
            return bool(status and status.get('app_id')==APP_ID and status.get('project_key')==project_key(Path(__file__).parent))
        threading.Thread(target=lambda:wait_and_open(url,owned_ready,cancelled=stopped),daemon=True).start()
        try:server.run()
        finally:stopped.set()
    else:server.run()
