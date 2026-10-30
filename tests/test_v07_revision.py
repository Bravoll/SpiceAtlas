"""Regression contracts for review changes: provenance, pause delivery, weighted cache and navigation."""
import asyncio,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
import httpx
from fastapi.testclient import TestClient
from atlas.cache_memory import CACHE_MODE,MemoryCache,memory_cache
from atlas.anticipation import Anticipation
from atlas.catalogue import catalogue
from atlas.providers import Reader
from atlas.preferences import preferences
from atlas.storage import Store
from atlas.runtime import runtime
from atlas.health import Health
from atlas.resources import available
from atlas.workspaces import workspaces
from desktop.gui import Window
from main import app
from test_v07 import WorkspaceFixture

ARTICLE={'mode':'article','entry_id':'basil','source':'enwiki','title':'Basil','html':'<p>Source text</p>','focus_html':'<p>Source text</p>','language':'en','revision_id':42,'fetched_at':'2026-10-28T00:00:00Z'}

class RevisedFixture(WorkspaceFixture):
    def setUp(self):
        super().setUp();self.flags=(runtime.phase,runtime.needs_retest);runtime.phase='running';runtime.needs_retest=False
        for key,scientific in [('parsley','Petroselinum crispum'),('basil','Ocimum basilicum')]:
            catalogue.upsert({'id':key,'name_en':key.title(),'name_zh':'欧芹' if key=='parsley' else '罗勒','scientific':scientific,'scope':'culinary','review_state':'curated','sources_resolved':True,'wiki':{'enwiki':key.title(),'zhwiki':'歐芹' if key=='parsley' else '羅勒'},'forms':[{'id':'flakes','name':'干叶','name_en':'Dried leaves'},{'id':'fresh','name':'鲜叶','name_en':'Fresh leaves'}]})
        self.manager=Anticipation(Reader(Store()));self.client=TestClient(app)
    def tearDown(self):
        memory_cache.clear(self.manager.store.namespace);runtime.phase,runtime.needs_retest=self.flags;super().tearDown()
    def observe(self,kind,number,manager=None):
        manager=manager or self.manager
        for i in range(number):manager.record_operation({'id':manager.session+'-'+kind+'-'+str(i),'kind':kind,'context':{'entry':'basil'}})

class MemoryTests(unittest.TestCase):
    def test_lru_is_bounded_and_namespaces_do_not_mix(self):
        cache=MemoryCache(max_bytes=180,namespace_bytes=80)
        for i in range(3):cache.put('version-a',str(i),{'v':'a'*24})
        self.assertIsNone(cache.get('version-a','0'));self.assertIsNotNone(cache.get('version-a','2'));self.assertIsNone(cache.get('version-b','2'))
        for i in range(3):cache.put('version-b',str(i),{'v':'b'*24})
        self.assertLessEqual(cache.bytes,180);self.assertLessEqual(cache.stats('version-a')['bytes'],80);self.assertLessEqual(cache.stats('version-b')['bytes'],80)
    def test_expired_prediction_is_removed(self):
        cache=MemoryCache();cache.put('a','x',{'text':'test'},ttl=-1);self.assertIsNone(cache.get('a','x'));self.assertEqual(cache.bytes,0)

class ResourceTests(RevisedFixture,unittest.TestCase):
    def test_prediction_payload_is_memory_only_and_version_scoped(self):
        token=CACHE_MODE.set('memory')
        try:self.manager.store.put('article:basil:enwiki:en',ARTICLE)
        finally:CACHE_MODE.reset(token)
        with self.manager.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM cache').fetchone()[0],0)
        self.assertEqual(self.manager.store.get('article:basil:enwiki:en')['tier'],'memory')
        new=workspaces.create('empty','default')
        with workspaces.use(new['id']):self.assertIsNone(self.manager.store.get('article:basil:enwiki:en'))
    def test_six_distinct_accesses_promote_but_duplicate_transport_does_not(self):
        desc=self.manager.descriptor({'kind':'article','entry':'basil','source':'enwiki','preferred':'en'})
        self.manager.store.put(self.manager.keys(desc)[0],ARTICLE,ttl=-1)
        with patch.object(self.manager,'sticky_ids',return_value=[]):
            self.assertEqual(self.manager.observe(desc,'event-0'),1);self.assertEqual(self.manager.observe(desc,'event-0'),1)
            for i in range(1,6):self.manager.observe(desc,'event-'+str(i))
            hit=self.manager.lookup(desc,'event-5',protected_only=True)
        self.assertTrue(hit['hit']);self.assertEqual(hit['tier'],'retained');self.assertEqual(hit['value']['fetched_at'],ARTICLE['fetched_at']);self.assertEqual(hit['value']['delivery'],'retained_cache')
        self.assertEqual(self.manager.stats()['packets'][0]['hits'],6)
    def test_frequent_memory_packet_is_copied_to_persistent_cache(self):
        desc=self.manager.descriptor({'kind':'article','entry':'basil','source':'enwiki','preferred':'en'});key=self.manager.keys(desc)[0]
        token=CACHE_MODE.set('memory')
        try:self.manager.store.put(key,ARTICLE)
        finally:CACHE_MODE.reset(token)
        with patch.object(self.manager,'sticky_ids',return_value=[]):
            for i in range(6):self.manager.observe(desc,str(i))
        memory_cache.clear(self.manager.store.namespace)
        self.assertEqual(self.manager.store.get(key)['tier'],'retained')
    def test_first_page_and_favorite_are_protected_without_six_accesses(self):
        desc=self.manager.descriptor({'kind':'article','entry':'basil','source':'enwiki','preferred':'en'})
        self.manager.observe(desc,'first');self.manager.store.put(self.manager.keys(desc)[0],ARTICLE,ttl=-1)
        self.assertTrue(self.manager.lookup(desc,'first',protected_only=True)['hit'])
    def test_copy_carries_resource_dictionary_and_statistics_but_not_memory(self):
        desc=self.manager.descriptor({'kind':'article','entry':'basil','source':'enwiki','preferred':'en'});self.manager.observe(desc,'retained');self.manager.store.put(self.manager.keys(desc)[0],ARTICLE)
        self.observe('source',4);token=CACHE_MODE.set('memory')
        try:self.manager.store.put('speculation-only',{'not':'persistent'})
        finally:CACHE_MODE.reset(token)
        child=workspaces.create('copy','copy')
        with workspaces.use(child['id']):
            copied=Anticipation(Reader(Store()));self.assertEqual(copied.stats()['history_total'],4);self.assertEqual(copied.stats()['session_total'],0);self.assertEqual(copied.stats()['packets'][0]['hits'],1)
            self.assertTrue(copied.lookup(desc,track=False)['hit']);self.assertIsNone(copied.store.get('speculation-only'))
    def test_lookup_endpoint_rejects_local_resources_and_isolates_operation_counts(self):
        with patch('main.anticipation',self.manager):
            self.assertEqual(self.client.post('/api/cache/lookup',json={'resource':{'kind':'catalogue','entry':'basil'}}).status_code,400)
            self.assertEqual(self.client.post('/api/cache/operation',json={'id':'local-page','kind':'page','context':{'entry':'basil'}}).status_code,400)
            self.assertEqual(self.client.get('/api/cache/stats').json()['history_total'],0)
    def test_cached_other_cards_are_returned_without_network_reader(self):
        desc={'kind':'other','entry':'basil'};self.manager.observe(desc,'one');self.manager.store.put(self.manager.keys(desc)[0],{'mode':'collection','cards':[{'title':'Cached source','source_url':'https://en.wikibooks.org/wiki/Cookbook:Basil','html':'<p>Source</p>'}]})
        with patch('main.anticipation',self.manager),patch('main.stream_cards') as network:
            rows=[json.loads(line) for line in self.client.get('/api/other-sources/basil/stream').text.splitlines()]
        network.assert_not_called();self.assertEqual(rows[-1]['reason'],'cache');self.assertEqual(rows[1]['card']['title'],'Cached source')

class StatisticsTests(RevisedFixture,unittest.TestCase):
    def test_history_session_recent_and_weights_transition(self):
        self.observe('entry',100);fresh=Anticipation(Reader(Store()))
        initial=fresh.stats();self.assertEqual(initial['history_total'],100);self.assertEqual(initial['session_total'],0);self.assertEqual(initial['effective_weights'],{'history':1.,'session':0.,'recent':0.})
        self.observe('source',30,fresh);result=fresh.stats()
        self.assertEqual(result['history_total'],130);self.assertEqual(result['session_total'],30);self.assertEqual(result['recent_total'],30);self.assertEqual(result['rows'][0]['kind'],'source');self.assertEqual(result['effective_weights'],{'history':.2,'session':.3,'recent':.5})
        preferences.save({'cache_weight_history':.8,'cache_weight_session':.1,'cache_weight_recent':.1});self.assertEqual(fresh.stats()['rows'][0]['kind'],'entry')
    def test_duplicate_operation_and_no_local_training(self):
        payload={'id':'single-click','kind':'form','context':{'entry':'basil','form':'fresh'}}
        self.assertTrue(self.manager.record_operation(payload)['counted']);self.assertFalse(self.manager.record_operation(payload)['counted']);self.assertEqual(self.manager.stats()['history_total'],1)
        for kind in ['search','page','treePage','typeStyle']:
            with self.assertRaises(ValueError):self.manager.record_operation({**payload,'id':kind,'kind':kind})
        self.assertEqual(self.manager.stats()['history_total'],1)
    def test_custom_shortcuts_and_weight_validation(self):
        keys={'tree_previous':'h','tree_next':'j','entry_previous':'k','entry_next':'l'};preferences.save({'shortcuts':keys});self.assertEqual(preferences.values()['shortcuts'],keys)
        for invalid in [{'shortcuts':{**keys,'entry_next':'h'}},{'shortcuts':{**keys,'entry_next':'R'}},{'cache_weight_history':0,'cache_weight_session':0,'cache_weight_recent':0},{'cache_promote_hits':1},{'cache_session_threshold':2}]:
            with self.assertRaises(ValueError):preferences.save(invalid)

class ForecastTests(RevisedFixture,unittest.IsolatedAsyncioTestCase):
    async def test_one_step_predictions_use_memory_and_only_available_actions(self):
        self.observe('form',8)
        with patch.object(self.manager,'sticky_ids',return_value=[]):plan=self.manager.plan({'entry':'basil','form':'flakes','profile':'auto','visible_entries':['parsley'],'preferred':'en'})
        self.assertEqual(plan['depth'],1);self.assertTrue(plan['prediction_only_memory']);self.assertTrue(plan['jobs']);self.assertTrue(all(row['tier']=='memory' for row in plan['jobs']));job=next(row for row in plan['jobs'] if row['action']=='form');self.assertEqual(job['resource']['form'],'fresh')
        async def image(*args):
            self.manager.store.put(self.manager.keys(job['resource'])[0],{'mode':'images','images':[{'id':'a'*24,'thumbnail_url':'https://upload.wikimedia.org/example.jpg','provider':'commons'}]});return {'mode':'images'}
        with patch.object(self.manager.reader,'images',side_effect=image):result=await self.manager.fetch(job['resource'],'memory',plan['generation'])
        self.assertTrue(result['ok']);self.assertEqual(self.manager.lookup(job['resource'],track=False)['tier'],'memory')
        with self.manager.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM cache').fetchone()[0],0)
    async def test_activity_cancels_pending_work_and_old_generation(self):
        started=asyncio.Event();cancelled=asyncio.Event()
        async def slow(*args):
            started.set()
            try:await asyncio.sleep(5)
            finally:cancelled.set()
        raw={'kind':'images','entry':'basil','form':'fresh'}
        with patch.object(self.manager.reader,'images',side_effect=slow):
            task=asyncio.create_task(self.manager.fetch(raw,'memory',0));await started.wait();self.manager.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cancelled.is_set())
        with self.assertRaisesRegex(ValueError,'context changed'):await self.manager.fetch(raw,'memory',0)
    async def test_longterm_idle_warming_requires_protected_entry(self):
        with patch.object(self.manager,'sticky_ids',return_value=[]):
            with self.assertRaisesRegex(ValueError,'protected'):await self.manager.fetch({'kind':'images','entry':'basil'},'longterm',0)

class DiagnosticTests(RevisedFixture,unittest.IsolatedAsyncioTestCase):
    async def test_deadline_unknown_preserves_entry_points_and_publishes_once(self):
        health=Health(budget_ms=30)
        async def slow(spec,gate):await asyncio.sleep(1)
        with patch.object(health,'specs',return_value=[{'id':'enwiki','kind':'api','url':'https://en.wikipedia.org'}]),patch.object(health,'probe',side_effect=slow):
            health.restart();rid=health.report()['round_id'];report=await health.tasks[self.version]
        self.assertIsNone(report['services']['enwiki']['ok']);self.assertEqual(report['services']['enwiki']['status'],'unconfirmed');self.assertTrue(available('enwiki',report));self.assertEqual(report['completed_rounds'],1)
        late=health.browser_results([{'id':'enwiki','ok':True}],rid);self.assertTrue(late['browser_results_ignored']);self.assertIsNone(late['services']['enwiki']['ok'])
    async def test_browser_and_backend_failures_are_not_conflated(self):
        health=Health();report=health.publish([{'id':'enwiki','ok':False}]);self.assertIsNone(report['services']['enwiki']['ok']);self.assertTrue(available('enwiki',report))
        report=health.publish([{'id':'enwiki','ok':False}],{'enwiki':{'ok':False,'checked_at':'now'}});self.assertFalse(available('enwiki',report))
        report=health.publish([{'id':'enwiki','ok':False}],{'enwiki':{'ok':True,'checked_at':'now'}});self.assertTrue(available('enwiki',report))
    async def test_pause_notice_is_emitted_before_gate_then_resume_needs_manual_retest(self):
        checker=Health(budget_ms=25);key,queue=runtime.subscribe()
        with patch.dict(os.environ,{'SPICE_LAUNCHER_CONTROL_TOKEN':'revision-test'}),patch.object(app.state,'launcher_shutdown',Mock(),create=True),patch('main.health',checker),patch.object(checker,'specs',return_value=[]):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                task=asyncio.create_task(client.post('/api/launcher/control',headers={'X-Atlas-Launcher':'revision-test'},json={'action':'pause'}))
                first=await asyncio.wait_for(queue.get(),.3);self.assertEqual(first['kind'],'service.pausing');self.assertFalse(runtime.paused)
                self.assertEqual((await client.get('/api/catalog')).status_code,200);self.assertEqual((await task).status_code,200)
                self.assertTrue(runtime.paused);self.assertEqual((await client.get('/api/catalog')).status_code,503)
                notice=(await client.get('/api/health')).json()['notifications'][0];self.assertEqual((await client.post('/api/notifications/'+notice['id']+'/dismiss')).status_code,200)
                resumed=(await client.post('/api/launcher/control',headers={'X-Atlas-Launcher':'revision-test'},json={'action':'resume'})).json();self.assertTrue(resumed['needs_retest']);self.assertFalse(resumed['paused'])
                plan=(await client.post('/api/health/round')).json();self.assertEqual(plan['phase'],'awaiting_retest');self.assertFalse(plan['probes'])
                manual=(await client.post('/api/settings/diagnostics')).json();self.assertFalse(manual['needs_retest']);self.assertEqual(manual['phase'],'checking');await checker.tasks[self.version]
        runtime.listeners.pop(key,None)

class ReadingAndNavigationTests(RevisedFixture,unittest.TestCase):
    def test_auto_english_keeps_v06_article_pipeline_when_probe_disabled_buttons(self):
        preferences.save({'ui_language':'en'});expected={**ARTICLE,'entry_id':'parsley'}
        with patch('main.reader.article',new_callable=AsyncMock,return_value=expected) as read,patch('main.health.report',return_value={'phase':'ready','services':{'enwiki':{'ok':False},'zhwiki':{'ok':False},'other_sources':{'ok':True}}}):
            result=self.client.get('/api/article/parsley?source=auto').json()
        self.assertEqual(result['mode'],'article');self.assertEqual(result['html'],expected['html']);self.assertEqual(read.await_args.args[1],'auto')
    def test_local_subcategory_pages_keep_total_and_disjoint_ids(self):
        for i in range(10):
            catalogue.node('revision-'+str(i),'子集 '+str(i),'Subset '+str(i),'category','culinary',parent='root-culinary')
            with catalogue.connect() as db:db.execute('INSERT OR IGNORE INTO membership VALUES(?,?)',('revision-'+str(i),'basil'))
        one=self.client.get('/api/catalog/nodes?parent=root-culinary&limit=3').json();two=self.client.get('/api/catalog/nodes?parent=root-culinary&limit=3&offset=3').json()
        self.assertGreaterEqual(one['total'],10);self.assertEqual(len(one['nodes']),3);self.assertTrue(one['has_more']);self.assertFalse({n['id'] for n in one['nodes']} & {n['id'] for n in two['nodes']})
    def test_window_minimum_tracks_measured_dpi_content(self):
        window=Window.__new__(Window);window.root=Mock();window.panel=Mock();window.panel.winfo_reqwidth.return_value=730;window.panel.winfo_reqheight.return_value=555
        window.root.winfo_width.return_value=620;window.root.winfo_height.return_value=440
        window.fit_window(preferred=(620,440));window.root.minsize.assert_called_with(730,555);window.root.geometry.assert_called_with('730x555')


class LiveImagePipelineContracts(RevisedFixture,unittest.IsolatedAsyncioTestCase):
    async def test_reviewed_file_metadata_can_finish_before_slow_searches(self):
        item=catalogue.get('parsley');item['forms'][0]['preferred_images']=['Parsley Dried.JPG'];catalogue.upsert(item)
        page={'pageid':42,'title':'File:Parsley Dried.JPG','imageinfo':[{'mime':'image/jpeg','url':'https://upload.wikimedia.org/wikipedia/commons/example.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Parsley_Dried.JPG','extmetadata':{'LicenseShortName':{'value':'Public domain'}}}]}
        with patch('atlas.providers.request_json',new_callable=AsyncMock,return_value={'query':{'pages':[page]}}) as network:
            result=await self.manager.reader.images('parsley','commons','flakes',True)
        self.assertEqual(len(result['images']),1);self.assertEqual(network.await_count,1);self.assertEqual(network.await_args.args[1]['titles'],'File:Parsley Dried.JPG');self.assertNotIn('gsrsearch',network.await_args.args[1])
        self.assertEqual(result['images'][0]['license'],'Public domain')
    async def test_packaging_filter_does_not_reuse_a_dried_leaf_file_hint(self):
        item=catalogue.get('parsley');item['forms'][0]['preferred_images']=['Parsley Dried.JPG']
        plans=self.manager.reader.commons_plans(item,'flakes','jar');self.assertIn('gsrsearch',plans[0]);self.assertNotIn('titles',plans[0])
