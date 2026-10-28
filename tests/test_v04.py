"""Regression checks for language policy, data admission and isolated workspaces."""
import asyncio,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
import httpx
from atlas.workspaces import Workspaces,workspaces
from atlas.catalogue import Catalogue,catalogue
from atlas.activity import activity
from atlas.preferences import preferences,Preferences
from atlas.resources import language_policy,resource_plan
from atlas.curation import admit
from atlas.health import Health
from atlas.translations import cloud_translate,excluded,validate_numbers
from atlas.image_lexicon import lexicon
from atlas.providers import Reader,ARTICLE_VARIANT
from atlas.storage import ROOT,Store
from main import app
from fastapi.testclient import TestClient

class LocaleTests(unittest.TestCase):
 def test_complete_mode_matrix(self):
  for mode,browser,domestic,locale in [('auto','zh-CN',True,'zh-Hans'),('auto','zh-SG',True,'zh-Hans'),('auto','zh-TW',False,'zh-Hant'),('auto','en-AU',False,'en'),('zh-Hans','zh-CN',False,'zh-Hans'),('zh-Hant','en-AU',False,'zh-Hant'),('en','zh-CN',False,'en')]:
   with self.subTest(mode=mode,browser=browser):
    value=language_policy(mode,browser);self.assertEqual(value['domestic'],domestic);self.assertEqual(value['ui'],locale)
 def test_matching_language_order_and_market(self):
  item=catalogue.get('parsley')
  for mode,browser,ids,host in [('auto','zh-CN',['baidu','bing','zhwiki'],'cn.bing.com'),('zh-Hans','zh-CN',['zhwiki','bing','google'],'www.bing.com'),('zh-Hant','en',['zhwiki','bing','google'],'www.bing.com'),('auto','en-AU',['enwiki','bing','google'],'www.bing.com')]:
   rows=resource_plan(item,mode,browser)['sources'];self.assertEqual([r['id'] for r in rows[:3]],ids);self.assertIn(host,rows[1]['url']);self.assertTrue(all(r['primary'] for r in rows[:3]))
 def test_unavailable_removed_without_mutating_rank_policy(self):
  item=catalogue.get('parsley');report={'services':{'google':{'ok':False},'baidu':{'ok':False}}}
  rows=resource_plan(item,'zh-Hans','zh-CN',report=report)['sources'];self.assertFalse(any(r['id'] in {'google','baidu'} for r in rows));self.assertEqual(rows[0]['id'],'zhwiki')
 def test_content_language_is_independent(self):self.assertEqual(language_policy('en','en','zh-Hant')['locale'],'zh-Hant')

class DataTests(unittest.TestCase):
 def test_wrong_entities_quarantined(self):
  for q in ('JDB Group','加多宝','加多寶','masala dabba','Wong Lo Kat'):
   self.assertEqual(catalogue.page(q)['total'],0,q)
  with catalogue.connect() as db:
   self.assertEqual(db.execute("SELECT status FROM quarantine WHERE id='wd-Q18231093'").fetchone()[0],'rejected')
 def test_curated_ranges_preserved(self):
  original=json.loads((ROOT/'data/catalog.json').read_text())
  for item in original['entries']:self.assertEqual(catalogue.get(item['id']).get('scope_note',''),item.get('scope_note',''))
 def test_counts_search_and_integrity(self):
  with catalogue.connect() as db:
   self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(db.execute('SELECT COUNT(*) FROM entries').fetchone()[0],db.execute('SELECT COUNT(*) FROM entry_search').fetchone()[0])
  self.assertEqual(catalogue.page('莳萝')['entries'][0]['id'],catalogue.page('蒔蘿')['entries'][0]['id']);self.assertEqual(catalogue.page('羅勒')['entries'][0]['id'],'basil')
 def test_future_company_and_container_rejected(self):
  self.assertEqual(admit({'id':'brand','name_en':'Example','entity_types':['Q431289']})['status'],'excluded')
  self.assertEqual(admit({'id':'box','wikidata_id':'Q23808433'})['status'],'excluded')
 def test_unknown_not_automatically_culinary(self):self.assertEqual(admit({'id':'unknown','name_en':'Example spice story'})['status'],'pending')
 def test_taxon_not_confirmation_of_edibility(self):
  decision=admit({'id':'plant','scientific':'Examplea species','entity_types':['Q16521']});self.assertEqual(decision['scope'],'botanical');self.assertEqual(decision['review_state'],'reference_only')
 def test_sampling_is_real_and_counted(self):
  data=json.loads((ROOT/'data/image_lexicon_seed.json').read_text());self.assertEqual(data['sampled_materials'],len({r['name'] for r in data['samples']}));self.assertEqual(data['sampled_queries'],len(data['samples']));self.assertGreaterEqual(data['sampled_materials'],25)
  self.assertTrue(all('filetype:bitmap' in row['request_parameters']['srsearch'] for row in data['samples']));self.assertEqual(len(data['profiles']),12)
 def test_fresh_and_flakes_queries_and_ranking(self):
  entry=catalogue.get('parsley');fresh=entry['forms'][1];flakes=entry['forms'][0];self.assertNotEqual(lexicon.queries(entry,fresh)['queries'],lexicon.queries(entry,flakes)['queries'])
  ranked=lexicon.rank(entry,fresh,[{'title':'Parsley powder.jpg'},{'title':'Parsley fresh leaves.jpg'}]);self.assertEqual(len(ranked),1)

 def test_packaging_profile_does_not_change_knowledge(self):
  item=catalogue.get('parsley');before=json.dumps(item,ensure_ascii=False);form=lexicon.form(item,'flakes','jar');plan=lexicon.queries(item,form);self.assertEqual(plan['profile'],'jar');self.assertTrue(any('jar' in q for q in plan['queries']));self.assertEqual(before,json.dumps(item,ensure_ascii=False))
 def test_image_profile_api_validates_and_has_browser_queries(self):
  client=TestClient(app);result=client.get('/api/browser-plan/images/parsley?form=fresh&profile=jar');self.assertEqual(result.status_code,200);self.assertEqual(result.json()['profile']['profile'],'jar');self.assertEqual(client.get('/api/browser-plan/images/parsley?profile=invalid').status_code,400)

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);baseline=root/'catalogue.sqlite3';base=Catalogue(baseline,seed=False)
  for key in ('parsley','basil','thyme'):base.upsert({'id':key,'name_en':key.title(),'scope':'culinary'})
  self.ws=Workspaces(root,baseline);self.patch=patch.multiple(workspaces,root=self.ws.root,baseline=self.ws.baseline,registry=self.ws.registry,context=self.ws.context);self.patch.start();self.env=patch('atlas.preferences.ENV',{});self.env.start();self.oldpath=preferences._path;preferences._path=None
  self.first=workspaces.active_id;Catalogue(workspaces.directory()/'catalogue.sqlite3',seed=False)
 def tearDown(self):preferences._path=self.oldpath;self.env.stop();self.patch.stop();self.temp.cleanup()
 def test_copy_and_default_isolate_every_store(self):
  preferences.save({'ui_language':'zh-Hant','lm_api_key':'fixture-private'});activity.favorite('parsley');activity.visit('basil');Store().put('example',{'value':1});item=workspaces.create('Copy');blank=workspaces.create('Defaults','default')
  with workspaces.use(item['id']):
   self.assertEqual(preferences.values()['lm_api_key'],'fixture-private');activity.favorite('thyme');preferences.save({'ui_language':'en'});Store().put('example',{'value':2})
  with workspaces.use(self.first):
   self.assertEqual(preferences.values()['ui_language'],'zh-Hant');self.assertEqual(len(activity.collection('favorites')),1);self.assertEqual(Store().get('example')['value']['value'],1)
  with workspaces.use(blank['id']):self.assertEqual(preferences.values()['lm_api_key'],'');self.assertEqual(activity.collection('favorites'),[]);self.assertIsNone(Store().get('example'))
 def test_order_manager_and_recoverable_delete(self):
  item=workspaces.create('A');workspaces.reorder([item['id'],self.first]);self.assertEqual(workspaces.list()['versions'][0]['id'],item['id']);workspaces.remove(item['id']);self.assertEqual(len(workspaces.trash()),1);workspaces.restore(item['id']);self.assertEqual(len(workspaces.list()['versions']),2)
  with self.assertRaises(ValueError):workspaces.reorder([self.first])
 def test_last_version_protected(self):
  with self.assertRaises(ValueError):workspaces.remove(self.first)
 def test_stale_tab_cannot_write_new_version(self):
  item=workspaces.create('Next');workspaces.switch(item['id']);response=TestClient(app).post('/api/settings',json={'ui_language':'en'},headers={'X-Atlas-Version':self.first});self.assertEqual(response.status_code,409);self.assertEqual(preferences.values()['ui_language'],'auto')
 def test_history_favorite_order_and_local_search(self):
  activity.favorite('thyme');activity.favorite('parsley');activity.reorder('favorites',['parsley','thyme']);data=catalogue.page('pars',collection='favorites');self.assertEqual(data['total'],1);self.assertEqual(data['entries'][0]['id'],'parsley')
  self.assertEqual([r['entry_id'] for r in activity.collection('favorites')],['parsley','thyme'])
 def test_copy_job_is_paused_with_cursor(self):
  with catalogue.connect() as db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',('job','wiki','running',2,10,json.dumps({'queue':[{'continue':'token'}]}),'','now'))
  item=workspaces.create('Job copy')
  with workspaces.use(item['id']):
   with catalogue.connect() as db:row=db.execute('SELECT * FROM jobs').fetchone()
   self.assertEqual(row['status'],'paused');self.assertIn('token',row['state'])
 def test_configuration_log_has_no_credentials(self):
  client=TestClient(app);client.post('/api/settings',json={'lm_api_key':'super-secret-fixture','google_translate_key':'cloud-fixture'});self.assertNotIn('secret-fixture',json.dumps(activity.events()));self.assertNotIn('cloud-fixture',json.dumps(activity.events()))

 def test_application_startup_and_shutdown_manage_background_check(self):
  from atlas.health import health
  with patch.object(health,'check',new_callable=AsyncMock,return_value={}) as checker:
   with TestClient(app) as client:
    self.assertEqual(client.get('/api/status').status_code,200)
    self.assertIsNotNone(health.loop_task)
   self.assertGreaterEqual(checker.await_count,1);self.assertIsNone(health.loop_task)

 def test_late_async_write_stays_in_origin_version(self):
  next_version=workspaces.create('Next')
  async def scenario():
   event=asyncio.Event()
   async def delayed():
    await event.wait();preferences.save({'lm_model':'origin-model'})
   with workspaces.use(self.first):task=asyncio.create_task(delayed())
   workspaces.switch(next_version['id']);event.set();await task
  asyncio.run(scenario())
  with workspaces.use(self.first):self.assertEqual(preferences.values()['lm_model'],'origin-model')
  with workspaces.use(next_version['id']):self.assertEqual(preferences.values()['lm_model'],'')

class HealthTests(WorkspaceTests):
 def test_health_lifecycle_silent_success_and_persistent_changes(self):
  health=Health();row={'id':'google','ok':True};health.publish([row]);self.assertEqual(activity.notifications(),[]);health.publish([{'id':'google','ok':False,'http_status':403}]);self.assertEqual(len(activity.notifications()),1);health.publish([{'id':'google','ok':False}]);self.assertEqual(len(activity.notifications()),1);health.publish([row]);self.assertEqual(len(activity.notifications()),2);activity.dismiss(activity.notifications()[0]['id']);self.assertEqual(len(activity.notifications()),1);self.assertEqual(row,{'id':'google','ok':True})
 def test_browser_route_overrides_backend_failure(self):
  health=Health();health.browser_results([{'id':'commons','ok':True}]);report=health.publish([{'id':'commons','ok':False}]);self.assertTrue(report['services']['commons']['ok']);self.assertFalse(report['services']['commons']['backend_ok'])
 def test_unconfigured_functions_are_ignored(self):self.assertFalse(any(s['kind']=='function' for s in Health().specs()));self.assertEqual(Health.interval,600)

class CloudTests(unittest.IsolatedAsyncioTestCase):
 async def test_google_official_payload_and_traditional_target(self):
  p={**preferences.values(),'google_translate_key':'fixture-key'};fake=AsyncMock();fake.__aenter__.return_value=fake;fake.post.return_value=httpx.Response(200,json={'data':{'translations':[{'translatedText':'歐芹 12'}]}},request=httpx.Request('POST','https://translation.googleapis.com'))
  with patch('atlas.translations.httpx.AsyncClient',return_value=fake):result=await cloud_translate('google',['Parsley 12'],'zh-Hant',p)
  self.assertEqual(result,['歐芹 12']);args=fake.post.call_args;self.assertEqual(args.kwargs['json']['target'],'zh-TW');self.assertIn('notranslate',args.kwargs['json']['q'][0]);self.assertEqual(args.kwargs['params']['key'],'fixture-key')
 async def test_azure_official_key_region_payload(self):
  p={**preferences.values(),'azure_translate_key':'fixture-key','azure_region':'australiaeast'};fake=AsyncMock();fake.__aenter__.return_value=fake;fake.post.return_value=httpx.Response(200,json=[{'translations':[{'text':'歐芹','to':'zh-Hant'}]}],request=httpx.Request('POST','https://api.cognitive.microsofttranslator.com'))
  with patch('atlas.translations.httpx.AsyncClient',return_value=fake) as factory:await cloud_translate('azure',['Parsley'],'zh-Hant',p)
  self.assertEqual(factory.call_args.kwargs['headers']['Ocp-Apim-Subscription-Region'],'australiaeast');self.assertEqual(fake.post.call_args.kwargs['params']['to'],'zh-Hant')
 async def test_exclusions_skip_adapter_before_fetch(self):
  with tempfile.TemporaryDirectory() as td:
   reader=Reader(Store(Path(td)/'cache.sqlite3'))
   with patch('atlas.providers.preferences.values',return_value={**preferences.values(),'excluded_languages':['en']}),patch('atlas.providers.local_translate',new_callable=AsyncMock) as remote:
    result=await reader.translate('parsley','enwiki');self.assertTrue(result['skipped']);remote.assert_not_called()
 def test_number_integrity_and_chinese_group(self):
  with self.assertRaises(ValueError):validate_numbers('12 percent','13 percent')
  self.assertTrue(excluded('zh-Hant',['zh']));self.assertTrue(excluded('zh-Hans',['zh']))

if __name__=='__main__':unittest.main()
