"""Review-3 contracts: language identity, real source adapters, frames and browser startup."""
import asyncio,json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
import httpx
from atlas.wiki_languages import resolve_languages,mapped_entry,cache_key
from atlas.web_sources import frame_headers,frame_check,image_results,read_reference
from atlas.other_sources import gbif_card,extract_article,public_host
from atlas.network import SourceFailure
from atlas.storage import Store
from atlas.catalogue import catalogue
from atlas.anticipation import Anticipation
from atlas.providers import Reader
from atlas.workspaces import workspaces
from desktop.browser import open_url,wait_and_open
from test_v07_revision import RevisedFixture,ARTICLE
from main import app

ENTRY={'id':'parsley','scientific':'Petroselinum crispum','name_en':'Parsley','name_zh':'欧芹','wiki':{'enwiki':'Parsley'},'scope':'culinary','wikidata_id':'Q25284'}

class LanguageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'cache.db')
    async def asyncTearDown(self):self.tmp.cleanup()
    async def test_english_anchor_discovers_language_without_mutating_catalogue_input(self):
        response={'query':{'pages':[{'title':'Parsley','pageid':1,'langlinks':[{'lang':'zh','title':'歐芹'},{'lang':'fr','title':'Persil'}]}]}}
        with patch('atlas.wiki_languages.fetch_json',new_callable=AsyncMock,return_value=response) as remote:
            value=await resolve_languages(ENTRY,self.store);again=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹');self.assertEqual(value['methods']['zh'],'english_langlink');self.assertEqual(remote.await_count,1)
        self.assertEqual(ENTRY['wiki'],{'enwiki':'Parsley'});self.assertEqual(mapped_entry(ENTRY,value)['wiki']['zhwiki'],'歐芹');self.assertEqual(again,value)
    async def test_unlinked_chinese_search_checks_identity_and_rejects_unrelated_hit(self):
        async def query(lang,params):
            if lang=='en':return {'query':{'pages':[{'pageid':1,'title':'Parsley'}]}}
            if params.get('list')=='search':return {'query':{'search':[{'pageid':10},{'pageid':11}]}}
            return {'query':{'pages':[{'pageid':10,'title':'Not parsley','extract':'A different plant'},{'pageid':11,'title':'歐芹','extract':'Petroselinum crispum is the selected species.'}]}}
        with patch('atlas.wiki_languages.query',side_effect=query) as remote:value=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹');self.assertEqual(value['methods']['zh'],'independent_search_identity_checked');self.assertEqual(remote.await_count,4)
    async def test_unmatched_chinese_is_not_claimed_from_search_rank(self):
        async def query(lang,params):
            if lang=='en':return {'query':{'pages':[{'pageid':1,'title':'Parsley'}]}}
            if params.get('list')=='search':return {'query':{'search':[{'pageid':10}]}}
            return {'query':{'pages':[{'pageid':10,'title':'石香薷','extract':'Unrelated botanical species'}]}}
        with patch('atlas.wiki_languages.query',side_effect=query):value=await resolve_languages(ENTRY,self.store)
        self.assertNotIn('zh',value['mapping']);self.assertEqual(value['state'],'resolved')
    async def test_transient_failure_preserves_known_mapping_and_marks_unconfirmed(self):
        with patch('atlas.wiki_languages.query',new_callable=AsyncMock,side_effect=SourceFailure('timeout',code='timeout')):value=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['en'],'Parsley');self.assertEqual(value['state'],'unconfirmed');self.assertEqual(value['diagnostics'][0]['code'],'timeout')

class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_gbif_v2_standard_usage_and_classification_are_rendered(self):
        data={'usage':{'key':'7828157','name':'Petroselinum crispum (Mill.) Fuss','canonicalName':'Petroselinum crispum','rank':'SPECIES','status':'ACCEPTED'},'classification':[{'rank':'FAMILY','name':'Apiaceae'}],'diagnostics':{'matchType':'EXACT','confidence':97}}
        with patch('atlas.other_sources.fetch_json',new_callable=AsyncMock,return_value=data) as remote:card=await gbif_card(ENTRY)
        self.assertEqual(card['api_version'],'v2');self.assertIn('Apiaceae',card['html']);self.assertTrue(remote.call_args.args[0].endswith('/v2/species/match'))
    async def test_gbif_v1_is_a_real_compatible_fallback(self):
        raw={'usageKey':7828157,'scientificName':'Petroselinum crispum','canonicalName':'Petroselinum crispum','matchType':'EXACT'}
        with patch('atlas.other_sources.fetch_json',new_callable=AsyncMock,side_effect=[SourceFailure('unsupported',code='http_error'),raw]) as remote:card=await gbif_card(ENTRY)
        self.assertEqual(remote.await_count,2);self.assertEqual(card['api_version'],'v1 compatible')
    async def test_proxy_owned_dns_does_not_reject_reviewed_host_before_http(self):
        with patch('atlas.other_sources.asyncio.get_running_loop') as loop,patch('atlas.preferences.preferences.values',return_value={'proxy_url':'http://127.0.0.1:8888','trust_env':False}):
            loop.return_value.getaddrinfo=AsyncMock(side_effect=OSError('local DNS unavailable'));await public_host('https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944')
        with self.assertRaises(SourceFailure):await public_host('https://127.0.0.1/private')
    async def test_private_dns_address_is_still_rejected_even_with_proxy(self):
        with patch('atlas.other_sources.asyncio.get_running_loop') as loop:
            loop.return_value.getaddrinfo=AsyncMock(return_value=[(2,1,6,'',('127.0.0.1',443))])
            with self.assertRaisesRegex(SourceFailure,'Non-public'):await public_host('https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944')
    async def test_plantnet_taxon_line_is_not_replaced_by_generic_site_title(self):
        entry={**ENTRY,'scientific':'Coriandrum sativum','name_en':'Coriander'}
        body='<html><title>PlantNET - FloraOnline</title><body><i>Coriandrum sativum L.</i><p>Description : '+('A botanical source description. '*10)+'</p></body></html>'
        card=extract_article(body,'https://plantnet.rbgsyd.nsw.gov.au/cgi-bin/NSWfl.pl?lvl=sp&name=Coriandrum~sativum&page=nswfl',entry)
        self.assertEqual(card['title'],'Coriandrum sativum L.')
        for url in ['https://plantnet.rbgsyd.nsw.gov.au/floraonline.htm','https://plantnet.rbgsyd.nsw.gov.au/cgi-bin/NSWfl.pl?lvl=sp&name=Wrong~species&page=nswfl']:
            with self.assertRaises(SourceFailure):extract_article(body,url,entry)
    async def test_google_and_baidu_frames_are_tested_instead_of_hardcoded_off(self):
        from atlas.providers import frame_capability
        with patch('atlas.web_sources.public_search_page',new_callable=AsyncMock,return_value={'url':'https://www.google.com/search?q=parsley','can_try':True,'markup':'not returned'}) as remote:
            self.assertTrue((await frame_capability(ENTRY,'google',url='https://www.google.com/search?q=parsley'))['can_try']);self.assertTrue((await frame_capability(ENTRY,'baidu',url='https://image.baidu.com/search/index?word=parsley'))['can_try'])
        self.assertEqual(remote.await_count,2)
    async def test_verification_redirect_stops_without_fetching_challenge(self):
        from atlas.web_sources import public_search_page
        transport=httpx.MockTransport(lambda request:httpx.Response(302,headers={'location':'https://wappass.baidu.com/static/captcha/tuxing_v2.html?private=not-exported'}))
        client=httpx.AsyncClient(transport=transport)
        with patch('atlas.web_sources.httpx.AsyncClient',return_value=client):
            with self.assertRaises(SourceFailure) as error:await public_search_page('https://image.baidu.com/search/index?word=parsley')
        self.assertEqual(error.exception.code,'verification_required');self.assertNotIn('not-exported',str(error.exception))
    async def test_real_frame_policy_and_safe_image_metadata(self):
        self.assertFalse(frame_headers({'x-frame-options':'SAMEORIGIN'})[0]);self.assertTrue(frame_headers({'content-security-policy':'script-src https:; frame-ancestors *'})[0]);self.assertFalse(frame_headers({'content-security-policy':"frame-ancestors 'self'"})[0])
        markup='<a m=\''+json.dumps({'murl':'https://images.example.org/leaf.jpg','purl':'https://example.org/parsley','t':'Parsley'})+'\'></a>'
        rows=image_results(markup,'bing');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['license'],'Check original source terms')
        self.assertEqual(image_results('<a href="/imgres?imgurl=http://127.0.0.1/secret&imgrefurl=https://example.org">bad</a>','google'),[])

class IntegrationTests(RevisedFixture,unittest.TestCase):
    def test_auto_cache_cannot_mask_a_mapped_primary_with_secondary_english(self):
        manager=Anticipation(Reader(Store()));item=catalogue.get('basil')
        manager.store.put('article:basil:enwiki:en',ARTICLE)
        result=manager.lookup({'kind':'article','entry':'basil','source':'auto','preferred':'zh','variant':'zh-hans'},track=False)
        self.assertFalse(result['hit'])
    def test_explicit_gbif_reads_structured_body_in_main_reader(self):
        item=catalogue.get('basil');item['references']={'gbif':{'name':'GBIF','url':'https://www.gbif.org/species/2927096','summary':'Original catalogue note'}};catalogue.upsert(item)
        card={'title':'Ocimum basilicum','html':'<table><tr><th>Family</th><td>Lamiaceae</td></tr></table>','toc':[],'source_url':item['references']['gbif']['url'],'language':'en','license':'Source dataset terms'}
        with patch('atlas.web_sources.gbif_card',new_callable=AsyncMock,return_value=card) as api:
            result=self.client.get('/api/article/basil?source=gbif:en').json()
        self.assertEqual(result['mode'],'article');self.assertIn('<table>',result['html']);api.assert_awaited_once();self.assertFalse(result['translation_supported'])
    def test_wiki_browser_plan_uses_verified_runtime_link(self):
        item=catalogue.get('basil');item['wiki']={'enwiki':'Basil'};catalogue.upsert(item)
        with patch('atlas.wiki_languages.resolve_languages',new_callable=AsyncMock,return_value={'mapping':{'en':'Basil','zh':'羅勒'}}):
            result=self.client.get('/api/browser-plan/article/basil?source=zhwiki&variant=zh-hant').json()
        self.assertEqual(result['params']['page'],'羅勒');self.assertEqual(result['params']['variant'],'zh-hant')
    def test_reviewed_article_packet_uses_the_same_reader_cache_and_retention(self):
        manager=Anticipation(Reader(Store()));url='https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944'
        desc=manager.descriptor({'kind':'web_article','entry':'basil','url':url});manager.observe(desc,'first-click')
        manager.store.put(manager.keys(desc)[0],{**ARTICLE,'source':'nparks'})
        hit=manager.lookup(desc,track=False,protected_only=True)
        self.assertTrue(hit['hit']);self.assertEqual(hit['tier'],'retained');self.assertEqual(hit['value']['source'],'nparks')
    def test_unreviewed_detail_url_is_rejected_before_network_access(self):
        with patch('atlas.web_sources.read_reference') as network:
            response=self.client.get('/api/source-read/basil?url=http://127.0.0.1/private')
        self.assertEqual(response.status_code,400);network.assert_not_called()
        with self.assertRaises(ValueError):self.manager.descriptor({'kind':'web_article','entry':'basil','url':'https://unreviewed.example.org/'})
    def test_search_reader_returns_real_result_shape_and_reviewed_link_capability(self):
        raw={'status':'ok','search_url':'https://www.bing.com/search?q=Basil','results':[{'title':'Basil source','url':'https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944','summary':'Source snippet','rank':1}]}
        with patch('atlas.web_sources.first_page',new_callable=AsyncMock,return_value=raw):result=self.client.get('/api/article/basil?source=bing:en').json()
        self.assertEqual(result['mode'],'search_results');self.assertEqual(result['results'][0]['summary'],'Source snippet');self.assertTrue(result['results'][0]['readable'])

class SearchTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_engine_redirect_keeps_html_results_and_blocks_private_target(self):
        from atlas.search_pages import first_page
        urls=[]
        def respond(request):
            urls.append(str(request.url))
            if request.url.host=='cn.bing.com':return httpx.Response(301,headers={'location':'https://www.bing.com/search?q=parsley'})
            return httpx.Response(200,text='<div id="b_results"><div class="b_algo"><h2><a href="https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944">Parsley</a></h2><div class="b_caption"><p>Botanical snippet</p></div></div></div>')
        with patch('atlas.search_pages.httpx.AsyncClient',return_value=httpx.AsyncClient(transport=httpx.MockTransport(respond))):result=await first_page('bing_cn','parsley')
        self.assertEqual(result['status'],'ok');self.assertEqual(len(urls),2);self.assertEqual(result['results'][0]['summary'],'Botanical snippet')
        urls=[]
        def unsafe(request):urls.append(str(request.url));return httpx.Response(302,headers={'location':'https://127.0.0.1/private'})
        with patch('atlas.search_pages.httpx.AsyncClient',return_value=httpx.AsyncClient(transport=httpx.MockTransport(unsafe))):result=await first_page('bing','parsley')
        self.assertEqual(result['status'],'blocked_redirect');self.assertEqual(len(urls),1)
    async def test_empty_html_can_offer_only_a_provider_permitted_frame(self):
        from atlas.web_sources import search_articles
        raw={'status':'no_extractable_results','http_status':200,'results':[],'search_url':'https://www.bing.com/search?q=parsley','embed_headers':{}}
        with patch('atlas.web_sources.first_page',new_callable=AsyncMock,return_value=raw):result=await search_articles(ENTRY,'bing','parsley')
        self.assertTrue(result['embed_can_try'])
        raw={**raw,'embed_headers':{'x-frame-options':'SAMEORIGIN'}}
        with patch('atlas.web_sources.first_page',new_callable=AsyncMock,return_value=raw):result=await search_articles(ENTRY,'google','parsley')
        self.assertFalse(result['embed_can_try'])

class BrowserTests(unittest.TestCase):
    def test_windowed_windows_open_uses_default_shell_without_console(self):
        with patch('desktop.browser.os.name','nt'),patch('desktop.browser.os.startfile',create=True) as start,patch('desktop.browser.webbrowser.open') as fallback:
            self.assertTrue(open_url('http://127.0.0.1:8765'));start.assert_called_once();fallback.assert_not_called()
    def test_shell_failure_falls_back_and_unowned_external_url_is_refused(self):
        with patch('desktop.browser.os.name','nt'),patch('desktop.browser.os.startfile',create=True,side_effect=OSError()),patch('desktop.browser.webbrowser.open',return_value=True) as fallback:
            self.assertTrue(open_url('http://127.0.0.1:8766'));self.assertFalse(open_url('https://unrelated.example.org'));fallback.assert_called_once()
    def test_browser_opens_after_readiness_and_cancel_stops_waiting(self):
        status=Mock(side_effect=[False,False,True]);opener=Mock(return_value=True)
        self.assertTrue(wait_and_open('http://127.0.0.1:8765',status,opener,poll=.001));opener.assert_called_once();self.assertEqual(status.call_count,3)
        cancelled=threading.Event();cancelled.set();status.reset_mock();self.assertFalse(wait_and_open('http://127.0.0.1:8765',status,opener,cancelled=cancelled));status.assert_not_called()
