"""Upgrade contract: preserve local state, validate before writes, rollback the entire chain."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import update

class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.target=self.root/'existing';self.source=self.root/'download';self.target.mkdir();self.source.mkdir()
        self.old_project=b'[project]\nname="spice-atlas-local-test"\nversion="0.6.0"\n'
        (self.target/'main.py').write_bytes(b'old application');(self.target/'pyproject.toml').write_bytes(self.old_project)
        self.preserved={'.venv/keep.txt':b'dependencies','data/versions/one/catalogue.sqlite3':b'local catalogue','data/versions/one/cache.sqlite3':b'long-term cache','data/versions/one/config.local.json':b'{"token":"private-local"}','data/versions.json':b'workspace registry','data/version_manager.jsonl':b'workspace history','data/catalogue.sqlite3':b'baseline','config.local.json':b'legacy config'}
        for name,value in self.preserved.items():
            p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
        self.manifest={'format':1,'app_id':'spice-atlas-local','build':'test','target_version':'0.7.0','steps':[]}
    def tearDown(self):self.temp.cleanup()
    def step(self,before='0.6.0',after='0.7.0',old_body=b'old application',new_body=b'new application'):
        prefix='payload/'+after;rows=[]
        for name,old,new in [('main.py',old_body,new_body),('pyproject.toml',self.old_project.replace(b'0.6.0',before.encode()),self.old_project.replace(b'0.6.0',after.encode()))]:
            src=self.source/prefix/name;src.parent.mkdir(parents=True,exist_ok=True);src.write_bytes(new)
            rows.append({'path':name,'source':prefix+'/'+name,'sha256':update.digest(new),'before_sha256':[update.digest(update.canonical(old)),update.digest(update.canonical(new))],'before_missing':False})
        step={'id':before+'-to-'+after,'from_versions':[before,after],'to_version':after,'migration':'preserve-workspaces-v1','dependencies_changed':False,'files':rows};self.manifest['steps'].append(step);self.manifest['target_version']=after;return step
    def save(self):(self.source/'update_manifest.json').write_text(json.dumps(self.manifest))
    def apply(self,**kwargs):
        self.save()
        with patch('update.ensure_stopped'):return update.apply_update(self.source,self.target,emit=lambda _:None,**kwargs)
    def assert_preserved(self):
        for name,value in self.preserved.items():self.assertEqual((self.target/name).read_bytes(),value,name)
    def test_in_place_update_preserves_dependencies_all_workspaces_and_cache(self):
        self.step();result=self.apply();self.assertEqual(update.version_of(self.target),'0.7.0');self.assert_preserved();self.assertTrue(Path(result['backup'],'files/main.py').is_file());self.assertFalse((self.target/'data/update.lock').exists())
    def test_dry_run_performs_no_writes(self):
        self.step();before=set(self.target.rglob('*'));result=self.apply(dry_run=True);self.assertTrue(result['dry_run']);self.assertEqual(before,set(self.target.rglob('*')));self.assertEqual((self.target/'main.py').read_bytes(),b'old application')
    def test_three_versions_apply_in_order_and_commit_one_final_version(self):
        self.step();self.step('0.7.0','0.8.0',b'new application',b'eight');self.step('0.8.0','0.9.0',b'eight',b'nine');result=self.apply();self.assertEqual(len(result['steps']),3);self.assertEqual(update.version_of(self.target),'0.9.0');self.assertEqual(len((self.target/'data/update_history.jsonl').read_text().splitlines()),1);self.assert_preserved()
    def test_failure_in_later_step_restores_every_step_and_removes_added_files(self):
        first=self.step();extra=self.source/'extra';extra.write_bytes(b'added')
        first['files'].append({'path':'static/new.js','source':'extra','sha256':update.digest(b'added'),'before_sha256':[],'before_missing':True})
        self.step('0.7.0','0.8.0',b'new application',b'eight')
        def fail(step,path):
            if step.startswith('0.7.0'):raise OSError('injected failure')
        with self.assertRaises(OSError):self.apply(hook=fail)
        self.assertEqual((self.target/'main.py').read_bytes(),b'old application');self.assertEqual(update.version_of(self.target),'0.6.0');self.assertFalse((self.target/'static/new.js').exists());self.assert_preserved()
    def test_corrupt_payload_is_rejected_before_any_backup_or_write(self):
        step=self.step();(self.source/step['files'][0]['source']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(update.UpdateError,'checksum'):self.apply()
        self.assertFalse((self.target/'data/updates').exists());self.assert_preserved()
    def test_local_code_edits_are_not_silently_overwritten(self):
        self.step();(self.target/'main.py').write_bytes(b'user edit')
        with self.assertRaisesRegex(update.UpdateError,'differs'):self.apply()
        self.assertEqual((self.target/'main.py').read_bytes(),b'user edit')
    def test_private_local_paths_cannot_enter_a_manifest(self):
        for path in ['.venv/keep.txt','data/versions/one/config.local.json','data/catalogue.sqlite3','data/versions.json','.git/config','config.local.json','../outside.py','static/../main.py','static/CON.js']:
            with self.subTest(path=path),self.assertRaises(update.UpdateError):update.managed_path(path)
    def test_unknown_migration_and_incomplete_chain_are_rejected(self):
        step=self.step();step['migration']='unknown'
        with self.assertRaisesRegex(update.UpdateError,'migration'):self.apply()
        step['migration']='preserve-workspaces-v1';self.manifest['target_version']='0.9.0'
        with self.assertRaisesRegex(update.UpdateError,'complete upgrade chain'):self.apply()
    def test_symlink_cannot_redirect_application_writes(self):
        self.step();outside=self.root/'outside';outside.mkdir();(self.target/'static').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(update.UpdateError):update.checked_path(self.target,'static/a.js')
    def test_unchanged_requirements_never_reinstall_or_recreate_environment(self):
        self.step()
        with patch('update.sync_dependencies') as sync:self.apply();sync.assert_not_called()
        self.assert_preserved()
    def test_failed_dependency_reconciliation_restores_environment(self):
        self.step()['dependencies_changed']=True
        def failed(*args):
            (self.target/'.venv/keep.txt').write_bytes(b'changed');raise update.UpdateError('dependency failure')
        with patch('update.sync_dependencies',side_effect=failed),self.assertRaises(update.UpdateError):self.apply()
        self.assertEqual(update.version_of(self.target),'0.6.0');self.assert_preserved()
    def test_same_version_reapplication_is_safe(self):
        self.step();self.apply();again=self.apply();self.assertEqual(again['files'],0);self.assert_preserved()
    def test_existing_lock_is_not_removed_by_second_updater(self):
        self.step();lock=self.target/'data/update.lock';lock.write_text('12345')
        with self.assertRaisesRegex(update.UpdateError,'Another update'):self.apply()
        self.assertEqual(lock.read_text(),'12345')
    def test_owned_live_service_refuses_upgrade_without_stopping_other_apps(self):
        from atlas.launcher_protocol import project_key
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'app_id':'spice-atlas-local','project_key':project_key(self.target)}).encode()
        response=Reply();response.target=self.target
        with patch('update.urllib.request.build_opener') as remote:
            remote.return_value.open.return_value=response
            with self.assertRaisesRegex(update.UpdateError,'Close Spice Atlas'):update.ensure_stopped(self.target)
