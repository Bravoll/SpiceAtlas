"""Deadline, ownership, pause/resume, source safety and completion-order contracts."""
import asyncio,io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
import httpx
from fastapi.testclient import TestClient
from atlas.catalogue import Catalogue
from atlas.health import Health
from atlas.preferences import Preferences,DEFAULTS,preferences
from atlas.runtime import runtime,scrub
from atlas.workspaces import Workspaces,workspaces
from atlas.other_sources import extract_article,public_host,fetch_html,stream_cards
from atlas.source_registry import provider_for,registry
from atlas.network import SourceFailure
from desktop.interactions import TrayClicks
from desktop.gui import Window,ZH,EN
from desktop.core import Starter,redact
from main import app

ENTRY={'id':'parsley','scientific':'Petroselinum crispum','name_en':'Parsley','scope':'culinary'}

class WorkspaceFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);baseline=root/'catalogue.sqlite3';db=Catalogue(baseline,seed=False)
        for key in ('parsley','basil'):db.upsert({'id':key,'name_en':key.title(),'scope':'culinary'})
        ws=Workspaces(root,baseline)
        self.patcher=patch.multiple(workspaces,root=ws.root,baseline=ws.baseline,registry=ws.registry,context=ws.context);self.patcher.start()
        self.oldpath=preferences._path;preferences._path=None;self.env=patch('atlas.preferences.ENV',{});self.env.start()
        self.old_pause=runtime.paused;runtime.paused=False;runtime.paused_jobs=[]
        self.version=workspaces.active_id;Catalogue(workspaces.directory()/'catalogue.sqlite3',seed=False)
    def tearDown(self):
        runtime.paused=self.old_pause;runtime.paused_jobs=[];preferences._path=self.oldpath;self.env.stop();self.patcher.stop();self.temp.cleanup()

class RoundTests(WorkspaceFixture,unittest.IsolatedAsyncioTestCase):
    async def test_publish_once_at_deadline_and_ignore_late_browser_recovery(self):
        checker=Health(budget_ms=55);cancelled=asyncio.Event()
        specs=[{'id':name,'kind':'api','url':'https://example.org'} for name in ['fast','slow','commons']]
        async def probe(spec,gate):
            if spec['id']=='slow':
                try:await asyncio.sleep(2)
                finally:cancelled.set()
            return {'id':spec['id'],'ok':spec['id']=='fast'}
        with patch.object(checker,'specs',return_value=specs),patch.object(checker,'probe',side_effect=probe):
            before=time.monotonic();checker.restart();rid=checker.report()['round_id']
            checker.browser_results([{'id':'commons','ok':True}],rid)
            self.assertTrue(checker.report()['initial']);self.assertEqual(checker.report()['services'],{})
            report=await checker.tasks[self.version];await asyncio.wait_for(cancelled.wait(),.2)
            self.assertLess(time.monotonic()-before,.4);self.assertFalse(report['services']['slow']['ok']);self.assertTrue(report['services']['commons']['ok'])
            revision=report['revision'];late=checker.browser_results([{'id':'commons','ok':False}],rid)
            self.assertTrue(late['browser_results_ignored']);self.assertEqual(late['revision'],revision);self.assertTrue(late['services']['commons']['ok'])

    async def test_new_round_keeps_previous_published_availability_while_checking(self):
        checker=Health(budget_ms=25);checker.publish([{'id':'google','ok':False}])
        with patch.object(checker,'specs',return_value=[]):
            checker.restart();report=checker.report()
            from atlas.resources import available
            self.assertFalse(available('google',report));self.assertFalse(report['initial'])
            await checker.tasks[self.version]

    async def test_first_browser_activation_is_not_an_unbounded_restart_loop(self):
        checker=Health(budget_ms=25)
        with patch.object(checker,'specs',return_value=[]):
            first=checker.begin_for_browser();second=checker.begin_for_browser();self.assertEqual(first['round_id'],second['round_id'])
            await checker.tasks[self.version]
            third=checker.begin_for_browser();self.assertEqual(first['round_id'],third['round_id']);self.assertEqual(third['probes'],[])
        self.assertEqual(Health().budget_ms,2000);self.assertEqual(Health.interval,600)

class RuntimeTests(WorkspaceFixture,unittest.TestCase):
    def test_owned_control_pause_then_resume_same_instance(self):
        with patch.dict(os.environ,{'SPICE_LAUNCHER_CONTROL_TOKEN':'test-only-secret','SPICE_LAUNCHER_INSTANCE':'same-instance'}),patch.object(app.state,'launcher_shutdown',Mock(),create=True):
            client=TestClient(app)
            self.assertEqual(client.post('/api/launcher/control',json={'action':'pause'}).status_code,403)
            with self.assertLogs('spice_atlas.runtime',level='INFO') as logs:
                paused=client.post('/api/launcher/control',headers={'X-Atlas-Launcher':'test-only-secret'},json={'action':'pause'})
                self.assertTrue(paused.json()['paused']);self.assertEqual(client.get('/api/catalog').status_code,503)
                self.assertEqual(client.get('/api/status').json()['instance_id'],'same-instance')
                self.assertEqual(client.get('/api/health').status_code,200)
                resumed=client.post('/api/launcher/control',headers={'X-Atlas-Launcher':'test-only-secret'},json={'action':'resume'})
                self.assertFalse(resumed.json()['paused']);self.assertEqual(client.get('/api/catalog').status_code,200)
            self.assertNotIn('test-only-secret','\n'.join(logs.output));self.assertTrue(any('service.resume' in line for line in logs.output))

    def test_unmanaged_pause_is_not_exposed(self):
        with patch.dict(os.environ,{},clear=True):self.assertEqual(TestClient(app).post('/api/launcher/control',json={'action':'pause'}).status_code,404)

    def test_ui_terminal_bridge_does_not_log_secret_fields(self):
        with self.assertLogs('spice_atlas.runtime',level='INFO') as logs:
            self.assertEqual(TestClient(app).post('/api/ui-events',json={'action':'change','control':'modelKey','lm_api_key':'do-not-log','value':'also-private','entry':'parsley'}).status_code,200)
        value='\n'.join(logs.output);self.assertIn('modelKey',value);self.assertNotIn('do-not-log',value);self.assertNotIn('also-private',value)
        self.assertEqual(scrub({'api_key':'secret'})['api_key'],'[redacted]');self.assertNotIn('secret',redact('https://host/?key=secret'))

    def test_new_timeout_settings_are_bounded(self):
        p=Preferences(Path(self.temp.name)/'settings.json')
        out=p.save({'other_source_timeout':4,'other_total_timeout':12,'other_max_cards':8,'other_search_enabled':False});self.assertEqual(out['other_max_cards'],8)
        for patch_value in [{'other_total_timeout':0},{'other_max_cards':1.5},{'other_source_timeout':31}]:
            with self.assertRaises(ValueError):p.save(patch_value)

class Scheduler:
    def __init__(self):self.pending={};self.number=0
    def after(self,delay,callback):self.number+=1;self.pending[self.number]=callback;return self.number
    def after_cancel(self,key):self.pending.pop(key,None)
    def finish(self):
        todo=list(self.pending.values());self.pending.clear()
        for callback in todo:callback()

class DesktopTests(unittest.TestCase):
    def test_single_click_toggle_and_double_click_only_opens_browser(self):
        scheduler=Scheduler();toggle=Mock();browser=Mock();clock=[0]
        click=TrayClicks(scheduler,toggle,browser,delay=400,clock=lambda:clock[0])
        click.receive('single');self.assertFalse(toggle.called);scheduler.finish();toggle.assert_called_once();toggle.reset_mock()
        clock[0]=1;click.receive('single');clock[0]=1.15;click.receive('double');clock[0]=1.17;click.receive('single');scheduler.finish()
        browser.assert_called_once();toggle.assert_not_called()
        clock[0]=2;click.receive('keyboard');toggle.assert_called_once()

    def test_native_duplicate_select_message_is_not_a_double_click(self):
        scheduler=Scheduler();toggle=Mock();browser=Mock();clock=[0]
        click=TrayClicks(scheduler,toggle,browser,clock=lambda:clock[0]);click.receive('single');clock[0]=.01;click.receive('single');scheduler.finish()
        toggle.assert_called_once();browser.assert_not_called()

    def test_details_button_can_hide_and_restore_user_window_sizes(self):
        window=Window.__new__(Window);window.root=Mock();window.root.winfo_width.return_value=610;window.root.winfo_height.return_value=370
        window.log_view=Mock();window.details_button=Mock();window.text=ZH;window.details_visible=False;window.expanded_size=(760,600)
        window.details();self.assertTrue(window.details_visible);window.details_button.configure.assert_called_with(text=ZH['hide_details'])
        window.root.winfo_width.return_value=820;window.root.winfo_height.return_value=650;window.details();self.assertFalse(window.details_visible);window.log_view.pack_forget.assert_called_once();window.root.geometry.assert_called_with('610x370')
        window.details();window.root.geometry.assert_called_with('820x650');self.assertEqual(ZH['title'],EN['title']);self.assertEqual(ZH['title'],'香料图鉴 - Spice Atlas')

    def test_pause_command_refuses_foreign_local_service_before_sending_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            starter=Starter(folder,lambda event:None);starter.server=Mock();starter.server.poll.return_value=None;starter.status_reader=lambda port:{'instance_id':'foreign','project_key':'foreign'}
            with patch('urllib.request.build_opener') as opener:
                with self.assertRaises(RuntimeError):starter.set_paused(True)
                opener.assert_not_called()
            starter.server=None;starter.close()

class HtmlTests(unittest.TestCase):
    def test_first_page_adapters_unwrap_public_search_links(self):
        import base64
        from atlas.search_pages import parse_results
        target='https://www.kew.org/plants/parsley'
        google='<a href="https://www.google.com/url?q='+target+'"><h3>Parsley</h3></a>'
        bing='<li class="b_algo"><h2><a href="https://www.bing.com/ck/?u=a1'+base64.urlsafe_b64encode(target.encode()).decode().rstrip('=')+'">Parsley</a></h2></li>'
        for engine,markup in [('google',google),('bing',bing),('bing_cn',bing)]:
            rows=parse_results(markup,engine);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['url'],target)

    def test_html_sanitizes_active_content_and_namespaces_every_anchor(self):
        markup='<html lang="en"><title>Parsley reference</title><main><h2 id="main">Petroselinum crispum</h2><p id="entryName">'+('Synthetic reader test paragraph. '*12)+'</p><a href="#main">Section</a><a href="/reference">More</a><script>steal()</script><img src="https://example.org/x"><a href="javascript:alert(1)" onclick="steal()">Bad link</a></main></html>'
        card=extract_article(markup,'https://plants.ces.ncsu.edu/plants/petroselinum-crispum/',ENTRY)
        self.assertNotIn('<script',card['html']);self.assertNotIn('steal()',card['html']);self.assertNotIn('javascript:',card['html']);self.assertNotIn('<img',card['html']);self.assertNotIn('id="entryName"',card['html'])
        self.assertIn('href="#'+card['toc'][0]['id']+'"',card['html']);self.assertIn('href="https://plants.ces.ncsu.edu/reference"',card['html'])

    def test_wrong_species_or_verification_is_not_an_article(self):
        for text in ['Salvia officinalis '+('Other species text. '*30),'Just a moment Parsley '+('Verify you are human. '*30)]:
            with self.assertRaises(SourceFailure):extract_article('<main><h1>Unrelated</h1><p>'+text+'</p></main>','https://www.kew.org/example',ENTRY)

    def test_name_only_in_a_late_related_species_list_is_not_the_selected_article(self):
        markup='<main><h1>Salvia officinalis</h1><p>'+('Unrelated sage description. '*140)+'</p><h2>Other plants</h2><p>Petroselinum crispum</p></main>'
        with self.assertRaises(SourceFailure):extract_article(markup,'https://www.kew.org/plants/sage',ENTRY)

    def test_url_registry_rejects_private_hosts_credentials_ports_and_stage_domains(self):
        for url in ['http://127.0.0.1','https://localhost/x','https://www.kew.org.evil.example/x','https://user:password@www.kew.org/x','https://www.kew.org:1234/x','https://www.kew.org:bad/x','https://stage.worldfloraonline.org/taxon/x']:
            self.assertIsNone(provider_for(url),url)
        self.assertTrue(provider_for('https://www.kew.org/plants/pepper'))

class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_dns_address_is_rejected(self):
        loop=asyncio.get_running_loop()
        with patch.object(loop,'getaddrinfo',new_callable=AsyncMock,return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(SourceFailure,'Non-public'):await public_host('https://www.kew.org/plants/pepper')

    async def test_completion_order_and_timeout_cancel_remaining_work(self):
        cancelled=[]
        async def gbif(entry):
            try:await asyncio.sleep(1)
            finally:cancelled.append('gbif')
        async def wiki(entry,kind):
            await asyncio.sleep(.012 if kind=='wikibooks' else .032)
            return {'title':kind,'html':'<p>synthetic</p>','toc':[],'source_url':'https://'+('en.wikibooks.org' if kind=='wikibooks' else 'species.wikimedia.org')+'/wiki/Test'}
        prefs={**DEFAULTS,'other_search_enabled':False,'other_total_timeout':.075,'other_source_timeout':.06,'other_max_cards':6}
        with patch('atlas.other_sources.gbif_card',side_effect=gbif),patch('atlas.other_sources.wiki_card',side_effect=wiki),patch('atlas.other_sources.known_candidates',return_value=[]):
            before=time.monotonic();events=[event async for event in stream_cards(ENTRY,prefs,{})]
        self.assertLess(time.monotonic()-before,.4);self.assertEqual([r['card']['provider'] for r in events if r['type']=='card'],['wikibooks','wikispecies']);self.assertIn('gbif',cancelled);self.assertEqual(events[-1]['type'],'done')

    async def test_closing_stream_cancels_inflight_sources(self):
        cancelled=[]
        async def slow(*args):
            try:await asyncio.sleep(2)
            finally:cancelled.append(True)
        prefs={**DEFAULTS,'other_search_enabled':False}
        with patch('atlas.other_sources.gbif_card',side_effect=slow),patch('atlas.other_sources.wiki_card',side_effect=slow),patch('atlas.other_sources.known_candidates',return_value=[]):
            stream=stream_cards(ENTRY,prefs,{})
            await anext(stream)
            task=asyncio.create_task(anext(stream));await asyncio.sleep(.02);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            await stream.aclose()
        self.assertEqual(len(cancelled),3)

class ResearchTests(unittest.TestCase):
    def test_sample_has_all_184_distinct_entries_and_honest_provenance(self):
        root=Path(__file__).resolve().parents[1];sample=json.loads((root/'data/source_research/sample_v07.json').read_text());ids={e['id'] for e in sample['entries']}
        self.assertEqual(len(ids),184);self.assertEqual({e['sampling_stratum'] for e in sample['entries']},{'curated_common_proxy','other_culinary_proxy','botanical_reference_proxy'})
        covered=set()
        for file in (root/'data/source_research').glob('supplement_*.json'):
            data=json.loads(file.read_text());rows=data.get('entries',data.get('records',data.get('results',[])))
            covered.update(row['entry_id'] for row in rows)
        self.assertEqual(covered,ids);self.assertEqual(len(registry()['providers']),21);self.assertTrue({'baidu_baike','mccormick'}<={p['id'] for p in registry()['providers']})
        direct=[json.loads(line) for line in (root/'data/source_research/first_pages_v07.jsonl').read_text().splitlines()]
        self.assertEqual(len(direct),552);self.assertEqual({row['engine'] for row in direct},{'google','bing','bing_cn'})
