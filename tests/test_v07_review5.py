import json,unittest
from unittest.mock import patch
import httpx
from atlas.web_sources import image_results,public_search_page
from atlas.network import SourceFailure
from test_v07_revision import RevisedFixture

class PublicImageTests(unittest.TestCase):
    def test_google_result_retains_thumbnail_title_and_source_page(self):
        markup='<a href="/imgres?imgurl=https%3A%2F%2Fimages.example.org%2Fparsley.jpg&amp;imgrefurl=https%3A%2F%2Fexample.org%2Fplants%2Fparsley"><img src="https://thumbs.example.org/p.jpg" alt="Parsley leaves"></a>'
        rows=image_results(markup,'google');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['display_url'],'https://thumbs.example.org/p.jpg');self.assertEqual(rows[0]['title'],'Parsley leaves');self.assertEqual(rows[0]['source_url'],'https://example.org/plants/parsley')
    def test_baidu_unreadable_original_uses_a_public_middle_image(self):
        raw={'objURL':'encoded:not-an-open-image','middleURL':'https://images.example.org/middle.jpg','thumbURL':'https://images.example.org/thumb.jpg','fromURL':'https://example.org/plants/parsley','fromPageTitleEnc':'<b>欧芹</b> 与叶片'}
        rows=image_results('var publicData='+json.dumps(raw,ensure_ascii=False)+';','baidu');self.assertEqual(rows[0]['original_url'],raw['middleURL']);self.assertEqual(rows[0]['title'],'欧芹 与叶片')
    def test_public_json_ld_can_form_a_gallery_without_executing_scripts(self):
        raw={'@type':'ItemList','itemListElement':[{'@type':'ImageObject','contentUrl':'https://images.example.org/photo.jpg','thumbnailUrl':['https://images.example.org/small.jpg'],'mainEntityOfPage':{'@id':'https://example.org/parsley'},'caption':'Fresh parsley'}]}
        rows=image_results('<script>throw new Error("must not execute")</script><script type="application/ld+json">'+json.dumps(raw)+'</script>','google');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source_url'],'https://example.org/parsley');self.assertIn('original source terms',rows[0]['license'])
    def test_result_budget_and_unsafe_image_urls_are_enforced(self):
        markup=''.join('<div m=\''+json.dumps({'murl':'https://images.example.org/'+str(i)+'.jpg','purl':'https://example.org/photo/'+str(i)})+'\'></div>' for i in range(50))
        self.assertEqual(len(image_results(markup,'bing')),20)
        self.assertEqual(image_results('<div data-ou="https://127.0.0.1/private" data-ru="https://example.org/p"></div>','google'),[])

class RedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_metadata_never_follows_insecure_or_credentialed_redirect(self):
        for target in ['http://www.google.com/search?q=x','https://user@www.google.com/search?q=x','https://www.google.com:8443/search?q=x']:
            requests=[]
            def reply(request):requests.append(request);return httpx.Response(302,headers={'location':target})
            with self.subTest(target=target),patch('atlas.web_sources.httpx.AsyncClient',return_value=httpx.AsyncClient(transport=httpx.MockTransport(reply))):
                with self.assertRaises(SourceFailure) as error:await public_search_page('https://www.google.com/search?tbm=isch&q=parsley')
                self.assertEqual(error.exception.code,'blocked_redirect');self.assertEqual(len(requests),1)

class NameplateSettingsTests(RevisedFixture,unittest.TestCase):
    def test_nameplate_defaults_are_version_local(self):
        from atlas.workspaces import workspaces
        first=workspaces.current_id
        self.assertEqual(self.client.post('/api/settings',json={'name_chinese_style':'scroll','name_western_style':'inscription'}).status_code,200)
        other=workspaces.create('Fresh defaults','default');workspaces.switch(other['id'])
        self.assertEqual(self.client.get('/api/settings').json()['name_chinese_style'],'botanical');self.assertEqual(self.client.get('/api/settings').json()['name_western_style'],'book')
        workspaces.switch(first);self.assertEqual(self.client.get('/api/settings').json()['name_chinese_style'],'scroll')
    def test_invalid_style_does_not_enter_saved_configuration(self):
        self.assertEqual(self.client.post('/api/settings',json={'name_chinese_style':'unknown'}).status_code,400)
        self.assertEqual(self.client.get('/api/settings').json()['name_chinese_style'],'botanical')
    def test_nameplate_view_choices_are_safe_persisted_fields(self):
        self.assertEqual(self.client.post('/api/view-state',json={'entry':'basil','nameChineseStyle':'scroll','nameWesternStyle':'inscription','api_key':'must not persist'}).status_code,200)
        state=self.client.get('/api/view-state').json();self.assertEqual(state['nameChineseStyle'],'scroll');self.assertEqual(state['nameWesternStyle'],'inscription');self.assertNotIn('api_key',state)
