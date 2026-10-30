"""Testable startup milestones and owned-process lifecycle, independent of Tk/Win32."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

from atlas.launcher_protocol import APP_ID, project_key

STAGES = {'environment': 5, 'prepare': 15, 'dependencies': 30, 'verify': 70,
          'catalogue': 80, 'server': 88, 'waiting': 90, 'browser': 97, 'ready': 100}


def redact(line):
    line = re.sub(r'(https?://)[^\s/@]+(?::[^\s/@]*)?@', r'\1[redacted]@', str(line))
    line = re.sub(r'(?i)(bearer\s+)[a-z0-9._~+/-]+', r'\1[redacted]', line)
    line = re.sub(r'(?i)((?:[?&]|\b)(?:api[_-]?key|key|token|secret|password)=)[^&\s]+', r'\1[redacted]', line)
    return line[-10000:]


def local_status(port, timeout=.6):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{int(port)}/api/status', timeout=timeout) as response:
            value=json.loads(response.read(100000))
            return value if isinstance(value,dict) else None
    except (OSError, ValueError, TypeError):
        return None


def available_port(preferred=8765):
    for port in range(preferred, min(65536, preferred+30)):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise RuntimeError('No available local port near ' + str(preferred))


class StartupCancelled(Exception):
    pass


class Log:
    def __init__(self, root, emit):
        directory = Path(root)/'data/launcher/logs'
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory/(datetime.now().strftime('%Y%m%d-%H%M%S')+f'-{os.getpid()}.log')
        self.stream = self.path.open('a', encoding='utf-8')
        self.lock = threading.RLock()
        self.emit = emit

    def write(self, line):
        line = redact(line).rstrip()
        if not line:
            return
        with self.lock:
            if self.stream.closed:
                return
            self.stream.write(datetime.now(timezone.utc).isoformat(timespec='seconds')+' '+line+'\n')
            self.stream.flush()
        self.emit({'kind': 'log', 'text': line})

    def close(self):
        with self.lock:
            self.stream.close()


class Runner:
    def __init__(self, root, log, cancelled, job=None):
        self.root, self.log, self.cancelled, self.job = Path(root), log, cancelled, job
        self.active = None
        self.lock = threading.RLock()

    def spawn(self, args, env=None):
        flags = (getattr(subprocess, 'CREATE_NO_WINDOW', 0) |
                 getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) if os.name == 'nt' else 0
        process = subprocess.Popen([str(x) for x in args], cwd=self.root, env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   errors='replace', creationflags=flags, shell=False)
        if self.job:
            try:
                self.job.assign(process)
            except OSError:
                self.log.write('Job assignment unavailable; owned process handle retained.')
        def drain():
            if process.stdout:
                for line in process.stdout:
                    self.log.write(line)
                process.stdout.close()
        threading.Thread(target=drain, daemon=True).start()
        return process

    def run(self, args):
        if self.cancelled.is_set():
            raise StartupCancelled()
        process = self.spawn(args)
        with self.lock:
            self.active = process
        try:
            while process.poll() is None:
                if self.cancelled.wait(.08):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise StartupCancelled()
            if process.returncode:
                if self.cancelled.is_set():
                    raise StartupCancelled()
                raise RuntimeError(f'{Path(str(args[0])).name} returned {process.returncode}. See startup log.')
        finally:
            with self.lock:
                self.active = None


class Starter:
    def __init__(self, root, emit, *, port=8765, job=None, runner_factory=Runner,
                 status_reader=local_status, browser=None):
        import webbrowser
        self.root, self.emit, self.preferred_port = Path(root).resolve(), emit, port
        self.cancelled = threading.Event()
        self.job, self.log = job, Log(self.root, emit)
        self.runner = runner_factory(self.root, self.log, self.cancelled, job)
        from .browser import open_url
        self.status_reader, self.browser = status_reader, browser or open_url
        self.server = None
        self.port = port
        self.instance = secrets.token_urlsafe(18)
        self.control_token = secrets.token_urlsafe(32)
        self.percent = 0
        self.session = self.root/'data/launcher/session.json'
        self.url = f'http://127.0.0.1:{port}'

    def stage(self, name, *, busy=False):
        self.percent = max(self.percent, STAGES[name])
        self.log.write(f'Stage: {name} ({self.percent}%)')
        value = {'instance_id': self.instance, 'owner_pid': os.getpid(), 'port': self.port,
                 'project_key': project_key(self.root), 'stage': name}
        temporary = self.session.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(self.session)
        self.emit({'kind': 'stage', 'stage': name, 'percent': self.percent, 'busy': busy})

    def run(self):
        try:
            self.stage('environment')
            if sys.version_info < (3, 11):
                raise RuntimeError('Python 3.11 or newer is required.')
            existing = self.status_reader(self.preferred_port)
            if existing and existing.get('app_id') == APP_ID and existing.get('project_key') == project_key(self.root):
                self.emit({'kind': 'existing', 'url': self.url})
                return
            self.stage('prepare')
            venv_python = self.root/('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
            uv = shutil.which('uv')
            self.stage('dependencies', busy=True)
            if uv:
                self.runner.run([uv, 'sync', '--frozen', '--inexact'])
            else:
                if not venv_python.is_file():
                    base = Path(sys.executable)
                    if base.name.lower() == 'pythonw.exe':
                        base = base.with_name('python.exe')
                    self.runner.run([base, '-m', 'venv', self.root/'.venv'])
                self.runner.run([venv_python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.txt'])
            self.stage('verify')
            self.runner.run([venv_python, '-c', 'import fastapi,uvicorn,httpx,bs4,bleach,opencc,pypinyin'])
            self.stage('catalogue', busy=True)
            self.runner.run([venv_python, '-c', "from atlas.seed import ensure_baseline; from pathlib import Path; ensure_baseline(Path('data/catalogue.sqlite3'))"])
            if self.cancelled.is_set():
                raise StartupCancelled()
            self.port = available_port(self.preferred_port)
            self.url = f'http://127.0.0.1:{self.port}'
            self.stage('server')
            env = {**os.environ, 'SPICE_LAUNCHER_INSTANCE': self.instance,
                   'SPICE_LAUNCHER_CONTROL_TOKEN': self.control_token, 'PYTHONUTF8': '1'}
            self.server = self.runner.spawn([venv_python, 'launch.py', '--port', self.port, '--managed', '--no-browser'], env)
            self.stage('waiting', busy=True)
            deadline = time.monotonic()+120
            while time.monotonic() < deadline:
                if self.cancelled.is_set():
                    raise StartupCancelled()
                if self.server.poll() is not None:
                    raise RuntimeError('The local server exited during startup. See startup log.')
                status = self.status_reader(self.port)
                if status and status.get('instance_id') == self.instance and status.get('project_key') == project_key(self.root):
                    break
                self.cancelled.wait(.2)
            else:
                raise RuntimeError('The local server did not become ready within 120 seconds.')
            self.stage('browser')
            try:
                opened = bool(self.browser(self.url))
            except Exception:
                opened = False
            self.stage('ready')
            self.emit({'kind': 'ready', 'url': self.url, 'browser_opened': opened})
        except StartupCancelled:
            self.emit({'kind': 'cancelled'})
        except Exception as exc:
            self.log.write(str(exc))
            self.stop()
            self.emit({'kind': 'error', 'message': redact(str(exc)), 'log': str(self.log.path)})

    def stop(self):
        self.cancelled.set()
        process = self.server
        if process is not None and process.poll() is None:
            try:
                identity=self.status_reader(self.port)
                if not identity or identity.get('instance_id')!=self.instance or identity.get('project_key')!=project_key(self.root):
                    raise OSError('Owned server is not reachable')
                request = urllib.request.Request(self.url+'/api/launcher/shutdown', method='POST',
                            headers={'X-Atlas-Launcher': self.control_token}, data=b'')
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=2):
                    pass
                process.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()

    def set_paused(self, paused):
        """Control only this launcher's matching live instance; keep its port/process."""
        if self.server is None or self.server.poll() is not None:
            raise RuntimeError('The managed service is not running.')
        identity=self.status_reader(self.port)
        if not identity or identity.get('instance_id')!=self.instance or identity.get('project_key')!=project_key(self.root):
            raise RuntimeError('The local service is not this launcher instance.')
        request=urllib.request.Request(self.url+'/api/launcher/control',method='POST',
            data=json.dumps({'action':'pause' if paused else 'resume'}).encode(),
            headers={'X-Atlas-Launcher':self.control_token,'Content-Type':'application/json'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request,timeout=5) as response:
            result=json.loads(response.read(100000))
        self.log.write('Service paused' if result['paused'] else 'Service resumed')
        return result

    def close(self):
        self.stop()
        if self.job:
            self.job.close()
        try:
            if json.loads(self.session.read_text()).get('instance_id') == self.instance:
                self.session.unlink()
        except (OSError, ValueError):
            pass
        self.log.close()
