"""0.6 startup ownership, authorization and display-only label normalization."""
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from atlas.catalogue import catalogue
from atlas.launcher_protocol import APP_ID, project_key
from atlas.localization import scientific_english
from desktop.core import Starter, Runner, StartupCancelled, redact, local_status
from main import app
from desktop.gui import Window


class WindowLifecycleTests(unittest.TestCase):
    def test_window_loop_failure_still_cleans_owned_process_and_tray(self):
        window=Window.__new__(Window)
        window.root=Mock()
        window.root.mainloop.side_effect=RuntimeError('UI loop interrupted')
        window.starter=Mock()
        window.worker=Mock()
        window.tray=Mock()
        window.tk=Mock(TclError=RuntimeError)
        with self.assertRaisesRegex(RuntimeError,'UI loop interrupted'):
            window.run()
        window.starter.cancelled.set.assert_called_once()
        window.starter.stop.assert_called_once()
        window.worker.join.assert_called_once_with(timeout=5)
        window.starter.close.assert_called_once()
        window.tray.close.assert_called_once()
        window.root.destroy.assert_called_once()


class LabelsAndControlTests(unittest.TestCase):
    def test_english_labels_keep_original_identity(self):
        for entry_id,expected in [('thyme','Thymus (genus)'),('cinnamon','Cinnamomum (genus)'),('paprika','Capsicum (ingredient genus)')]:
            item=catalogue.get(entry_id)
            self.assertEqual(item['scientific_en'],expected)
            self.assertIn('（',item['scientific'])
        self.assertEqual(scientific_english('Salvia rosmarinus'),'Salvia rosmarinus')

    def test_shutdown_is_not_exposed_in_console_mode(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(TestClient(app).post('/api/launcher/shutdown').status_code,404)

    def test_only_launcher_secret_can_request_owned_shutdown(self):
        shutdown=Mock()
        with patch.dict(os.environ,{'SPICE_LAUNCHER_CONTROL_TOKEN':'fixture-launch-secret','SPICE_LAUNCHER_INSTANCE':'fixture-instance'}),patch.object(app.state,'launcher_shutdown',shutdown,create=True):
            client=TestClient(app)
            self.assertEqual(client.post('/api/launcher/shutdown').status_code,403)
            self.assertEqual(client.post('/api/launcher/shutdown',headers={'X-Atlas-Launcher':'wrong'}).status_code,403)
            shutdown.assert_not_called()
            status=client.get('/api/status')
            self.assertEqual(status.json()['instance_id'],'fixture-instance')
            self.assertNotIn('fixture-launch-secret',status.text)
            self.assertEqual(client.post('/api/launcher/shutdown',headers={'X-Atlas-Launcher':'fixture-launch-secret'}).status_code,200)
            shutdown.assert_called_once()

    def test_project_identity_does_not_publish_the_local_path(self):
        root=Path(__file__).resolve().parents[1]
        value=TestClient(app).get('/api/status').json()
        self.assertEqual(value['project_key'],project_key(root))
        self.assertNotIn(str(root),json.dumps(value))

    def test_project_icon_has_multiple_valid_sizes(self):
        data=(Path(__file__).resolve().parents[1]/'static/atlas-icon.ico').read_bytes()
        reserved,kind,count=struct.unpack_from('<HHH',data)
        self.assertEqual((reserved,kind),(0,1));self.assertGreaterEqual(count,5)
        for n in range(count):
            _,_,_,_,_,_,size,offset=struct.unpack_from('<BBBBHHII',data,6+n*16)
            self.assertLessEqual(offset+size,len(data))


class FakeProcess:
    def __init__(self):self.code=None;self.returncode=None;self.terminated=False;self.stdout=io.StringIO('')
    def poll(self):return self.code
    def wait(self,timeout=None):self.code=0;return 0
    def terminate(self):self.terminated=True;self.code=-1
    def kill(self):self.terminated=True;self.code=-9


class FakeRunner:
    def __init__(self,root,log,cancelled,job):self.commands=[];self.environment=None;self.process=FakeProcess();self.fail=False
    def run(self,args):
        self.commands.append([str(x) for x in args])
        if self.fail:raise RuntimeError('dependency setup failed')
    def spawn(self,args,env=None):self.commands.append([str(x) for x in args]);self.environment=env;return self.process


class BootstrapTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.events=[];self.browser=Mock(return_value=True)
    def tearDown(self):self.temp.cleanup()
    def starter(self,status=None):return Starter(self.root,self.events.append,runner_factory=FakeRunner,status_reader=status or (lambda p:None),browser=self.browser)
    def close(self,starter):starter.runner.process.code=0;starter.close()

    def test_real_milestones_only_open_browser_after_instance_is_ready(self):
        starter=self.starter()
        def status(port):
            if starter.server is None:return None
            return {'app_id':APP_ID,'project_key':project_key(self.root),'instance_id':starter.instance}
        starter.status_reader=status
        with patch('desktop.core.shutil.which',return_value='uv'),patch('desktop.core.available_port',return_value=8777):starter.run()
        stages=[e['percent'] for e in self.events if e['kind']=='stage']
        self.assertEqual(stages,[5,15,30,70,80,88,90,97,100])
        self.browser.assert_called_once_with('http://127.0.0.1:8777')
        self.assertIn('--managed',starter.runner.commands[-1])
        self.assertIn('--inexact',starter.runner.commands[0])
        self.assertEqual(starter.runner.environment['SPICE_LAUNCHER_INSTANCE'],starter.instance)
        self.assertNotIn(starter.control_token,starter.session.read_text())
        self.assertNotIn(starter.control_token,starter.log.path.read_text())
        self.close(starter)

    def test_install_failure_keeps_progress_below_ready_and_keeps_log(self):
        starter=self.starter();starter.runner.fail=True
        with patch('desktop.core.shutil.which',return_value='uv'):starter.run()
        self.assertEqual(starter.percent,30)
        self.assertTrue(any(e['kind']=='error' for e in self.events))
        self.assertFalse(any(e['kind']=='ready' for e in self.events))
        self.browser.assert_not_called()
        self.assertIn('dependency setup failed',starter.log.path.read_text())
        self.close(starter)

    def test_existing_same_project_service_is_never_spawned_or_stopped(self):
        starter=self.starter(lambda p:{'app_id':APP_ID,'project_key':project_key(self.root),'instance_id':'existing'})
        starter.run()
        self.assertEqual(starter.runner.commands,[])
        self.assertTrue(any(e['kind']=='existing' for e in self.events))
        self.assertIsNone(starter.server)
        self.close(starter)

    def test_wrong_readiness_nonce_never_opens_browser(self):
        starter=self.starter(lambda p:{'app_id':APP_ID,'project_key':project_key(self.root),'instance_id':'another-instance'} if p==8777 else None)
        with patch('desktop.core.shutil.which',return_value='uv'),patch('desktop.core.available_port',return_value=8777),patch('desktop.core.time.monotonic',side_effect=[0,1,121]),patch.object(starter.cancelled,'wait',return_value=False),patch.object(starter,'stop'):
            starter.run()
        self.browser.assert_not_called()
        self.assertTrue(any(e['kind']=='error' for e in self.events))
        self.close(starter)

    def test_pip_fallback_creates_environment_and_checks_dependencies(self):
        starter=self.starter()
        starter.status_reader=lambda p:({'project_key':project_key(self.root),'instance_id':starter.instance} if starter.server else None)
        with patch('desktop.core.shutil.which',return_value=None),patch('desktop.core.available_port',return_value=8777):starter.run()
        self.assertIn('venv',starter.runner.commands[0]);self.assertIn('pip',starter.runner.commands[1])
        self.assertIn('--disable-pip-version-check',starter.runner.commands[1])
        self.close(starter)

    def test_cancelled_setup_is_not_reported_as_ready(self):
        starter=self.starter()
        starter.runner.run=Mock(side_effect=StartupCancelled())
        with patch('desktop.core.shutil.which',return_value='uv'):starter.run()
        self.assertTrue(any(e['kind']=='cancelled' for e in self.events))
        self.assertFalse(any(e['kind']=='ready' for e in self.events))
        self.close(starter)

    def test_stop_does_not_send_secret_to_a_different_local_service(self):
        starter=self.starter(lambda p:{'project_key':'other','instance_id':'other'})
        starter.server=starter.runner.process
        with patch('desktop.core.urllib.request.build_opener') as network:starter.stop()
        network.assert_not_called();self.assertTrue(starter.server.terminated)
        self.close(starter)

    def test_logs_redact_proxy_credentials_and_bearer_tokens(self):
        value=redact('https://alice:password@proxy.example/ Bearer fixture-secret')
        self.assertNotIn('password',value);self.assertNotIn('fixture-secret',value)

    def test_windows_child_creation_is_hidden_and_never_uses_shell(self):
        runner=Runner(self.root,Mock(),threading.Event())
        process=FakeProcess()
        with patch('desktop.core.os.name','nt'),patch.object(subprocess,'CREATE_NO_WINDOW',0x08000000,create=True),patch.object(subprocess,'CREATE_NEW_PROCESS_GROUP',0x200,create=True),patch('desktop.core.subprocess.Popen',return_value=process) as popen:
            runner.spawn(['python.exe','launch.py'])
        self.assertEqual(popen.call_args.kwargs['creationflags'],0x08000200)
        self.assertFalse(popen.call_args.kwargs['shell'])


if __name__=='__main__':unittest.main()
