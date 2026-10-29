"""Verify a portable ZIP and exercise first-start APIs in an isolated extraction.

Use the project's installed Python environment. No external services or personal
credentials are used. Native Windows GUI validation remains a separate task.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile


SMOKE = r'''
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from atlas.health import health
with patch.object(health, 'check', new_callable=AsyncMock, return_value={}):
 with TestClient(app) as client:
  status=client.get('/api/status').json()
  assert status['version']=='0.6.0', status
  assert status['catalogue']['total']==18379
  assert status['app_id']=='spice-atlas-local' and not status['managed']
  assert 'control_token' not in status
  assert client.get('/api/catalog?q=JDB%20Group').json()['total']==0
  assert client.get('/api/catalog/audit?limit=1').json()['total']==699
  prefs=client.get('/api/settings').json()
  assert prefs['reader_font_size']==17 and prefs['animation_level']==2
  assert prefs['startup_mode']=='resume'
  assert not any(v for k,v in prefs.items() if k.startswith('has_') and k.endswith('_key'))
  for key,label in [('thyme','Thymus (genus)'),('cinnamon','Cinnamomum (genus)'),('paprika','Capsicum (ingredient genus)')]:
   item=client.get('/api/entry/'+key).json()
   assert item['scientific_en']==label and '（' in item['scientific']
  basil=client.get('/api/entry/basil').json()
  assert basil['spoken_english']=='Basil' and basil['pinyin']
  assert client.get('/api/catalog/random?scope=culinary&exclude=basil').json()['id']!='basil'
  body={'entry':'basil','frameOpen':True,'frameMode':'responsive','frameExpanded':True,'imageProfile':'jar','mainScroll':100,'lm_api_key':'must-not-save'}
  assert client.post('/api/view-state',json=body).status_code==200
  view=client.get('/api/view-state').json()
  assert view['frameMode']=='responsive' and view['frameExpanded'] and view['imageProfile']=='jar'
  assert 'lm_api_key' not in view
  assert client.post('/api/launcher/shutdown').status_code==404
  assert client.post('/api/settings',json={'reader_font_size':24,'animation_level':3}).status_code==200
  assert client.get('/api/settings').json()['animation_level']==3
  for asset in ['interactions.js','interactions.css','experience.js','experience.css','atlas-icon.svg','atlas-icon.ico']:
   assert client.get('/static/'+asset).status_code==200
  home=client.get('/')
  assert 'interactions.js' in home.text and 'readingNavigator' in home.text
  assert 'media-src' in home.headers['Content-Security-Policy']
  print(json.dumps({'passed':True,'version':'0.6.0','records':18379,'audit_decisions':699,'checks':['fresh workspace initialization','clean catalogue and JDB exclusion','default settings and no saved keys','English scientific labels preserve raw metadata','local pinyin and random exclusion','expanded/responsive view persistence','view excludes unknown secret fields','unmanaged shutdown unavailable','settings roundtrip','all new static assets served','application lifespan shutdown']}))
'''


def managed_http_smoke(release, env):
    """Run the real uvicorn entry point, with external startup probes disabled."""
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
    secret, instance=uuid.uuid4().hex, uuid.uuid4().hex
    child_env={**env,'SPICE_LAUNCHER_CONTROL_TOKEN':secret,'SPICE_LAUNCHER_INSTANCE':instance}
    code='''
import runpy, sys
from atlas.health import health
health.start=lambda:None
async def idle():pass
health.stop=idle
sys.argv=['launch.py','--managed','--no-browser','--port',sys.argv[1]]
runpy.run_path('launch.py',run_name='__main__')
'''
    process=subprocess.Popen([sys.executable,'-c',code,str(port)],cwd=release,env=child_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url=f'http://127.0.0.1:{port}'
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Managed server exited before readiness')
            try:
                with opener.open(url+'/api/status',timeout=.5) as response:
                    status=json.loads(response.read())
                break
            except (OSError,ValueError):
                time.sleep(.1)
        else:
            raise RuntimeError('Managed server did not become ready')
        assert status['app_id']=='spice-atlas-local' and status['managed']
        assert status['instance_id']==instance and secret not in json.dumps(status)
        denied=urllib.request.Request(url+'/api/launcher/shutdown',data=b'',headers={'X-Atlas-Launcher':'wrong'})
        try:
            opener.open(denied,timeout=2)
            raise AssertionError('Wrong shutdown key was accepted')
        except urllib.error.HTTPError as error:
            assert error.code==403
        accepted=urllib.request.Request(url+'/api/launcher/shutdown',data=b'',headers={'X-Atlas-Launcher':secret})
        with opener.open(accepted,timeout=2) as response:
            assert response.status==200
        output=process.communicate(timeout=15)[0]
        assert process.returncode==0 and secret not in output
        return {'passed':True,'entrypoint':'launch.py --managed --no-browser','real_local_http':True,'instance_matched':True,'wrong_key_status':403,'shutdown_status':200,'exit_code':process.returncode,'external_health_probes':'disabled for isolated smoke'}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


def verify(path):
    with tempfile.TemporaryDirectory(prefix='spice-release-') as temporary:
        directory=Path(temporary)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None, 'ZIP CRC failed'
            names=archive.namelist()
            roots={Path(name).parts[0] for name in names}
            assert len(roots)==1, 'Expected one release root'
            release=directory/roots.pop()
            for name in names:
                target=(directory/name).resolve()
                assert target.is_relative_to(directory.resolve()), 'Unsafe archive path'
                relative=Path(name).relative_to(release.name)
                assert not {'node_modules','.venv','.git','__pycache__','launcher','versions','version_trash','media'} & set(relative.parts), relative
                assert relative.name not in {'config.local.json','versions.json','.env'}, relative
            archive.extractall(directory)
        required=['main.py','launch.py','Start_Atlas.pyw','run.cmd','run_console.cmd','run.sh','desktop/core.py','desktop/gui.py','desktop/win_native.py','atlas/launcher_protocol.py','README.md','README.en.md','README.zh-CN.md','static/interactions.js','static/interactions.css','static/atlas-icon.ico','static/atlas-icon.svg','docs/MOTION_DESIGN.zh-CN.md','data/catalogue.sqlite3']
        assert all((release/name).is_file() for name in required), 'Missing required release files'
        for name in ['run.cmd','run_console.cmd']:
            raw=(release/name).read_bytes()
            assert b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n',b''), 'Windows launcher line endings'
        with sqlite3.connect(release/'data/catalogue.sqlite3') as database:
            assert database.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert database.execute('SELECT COUNT(*) FROM entries').fetchone()[0]==18379
        homepage=(release/'README.md').read_text()
        assert homepage.index('<a id="english">')<homepage.index('<a id="chinese">')
        assert (release/'README.en.md').read_text().strip() in homepage
        assert (release/'README.zh-CN.md').read_text().strip() in homepage
        env={k:v for k,v in os.environ.items() if not k.startswith(('LM_','GOOGLE_','AZURE_','SPICE_'))}
        env.update(SPICE_DATA_DIR=str(release/'data'),PYTHONPATH=str(release),PYTHONUTF8='1')
        process=subprocess.run([sys.executable,'-c',SMOKE],cwd=release,env=env,capture_output=True,text=True,timeout=90)
        if process.returncode:
            raise RuntimeError(process.stderr[-5000:] or process.stdout[-5000:])
        smoke=json.loads(process.stdout.strip().splitlines()[-1])
        managed=managed_http_smoke(release,env)
        return {'zip':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':len(names),'archive_integrity':True,'required_files':len(required),'readme_language_order':'English, Chinese','smoke':smoke,'managed_server_smoke':managed,'native_windows_tested':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--report',type=Path)
    options=parser.parse_args()
    result=verify(options.archive.resolve())
    if options.report:
        options.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
