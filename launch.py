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
    if not args.no_browser:
        def open_when_ready():
            for _ in range(40):
                try:
                    with urllib.request.urlopen(url + "/api/status", timeout=0.4):
                        webbrowser.open(url)
                        return
                except Exception:
                    time.sleep(0.3)
        threading.Thread(target=open_when_ready, daemon=True).start()
    print("香料图鉴：" + url)
    print("关闭此窗口或按 Ctrl+C 停止服务。")
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=args.port,log_level="warning"))
    if args.managed:
        app.state.launcher_shutdown=lambda:setattr(server,'should_exit',True)
    server.run()
