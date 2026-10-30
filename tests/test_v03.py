import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from atlas.catalogue import Catalogue
from atlas.network import SourceFailure
from atlas.preferences import Preferences,preferences
from atlas.providers import Reader,frame_capability
from atlas.storage import Store
from main import app


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Catalogue(Path(self.temp.name)/"catalog.sqlite",seed=False)
        self.db.node("root","目录","Root","root","culinary")
        self.db.node("family","科","Family","family","culinary",parent="root")
        self.db.node("genus","属","Genus","genus","culinary",parent="family")
        for i in range(95):
            key=f"fixture-{i}"
            self.db.upsert({"id":key,"name_zh":f"测试条目{i}","name_en":f"Fixture herb {i}","scientific":f"Testus fixture{i}","scope":"culinary","aliases":["芫荽","Cilantro"] if i==7 else []})
            self.db.member("genus",key)
    def tearDown(self):self.temp.cleanup()
    def test_paging_works_without_loading_the_entire_catalogue(self):
        first=self.db.page(limit=20);second=self.db.page(offset=20,limit=20)
        self.assertEqual(first["total"],95);self.assertEqual(len(first["entries"]),20)
        self.assertFalse({e["id"] for e in first["entries"]}&{e["id"] for e in second["entries"]})
    def test_chinese_and_english_aliases(self):
        self.assertEqual(self.db.page("芫荽")["entries"][0]["id"],"fixture-7")
        self.assertEqual(self.db.page("cilantro")["entries"][0]["id"],"fixture-7")
    def test_scientific_name_search(self):
        self.assertEqual(self.db.page("Testus fixture94")["total"],1)
    def test_hierarchical_membership(self):
        self.assertEqual(self.db.page(node="root")["total"],95)
        self.assertEqual(self.db.children("family")[0]["id"],"genus")
    def test_cycles_do_not_duplicate_results(self):
        self.db.node("family","科","Family","family","culinary",parent="genus")
        self.assertEqual(self.db.page(node="family")["total"],95)
    def test_no_fabricated_chinese_name(self):
        self.db.upsert({"id":"latin-only","name_en":"Testus localis","scientific":"Testus localis","scope":"botanical","review_state":"reference_only"})
        item=self.db.get("latin-only")
        self.assertEqual(item["name_zh"],"");self.assertEqual(item["forms"][0]["theme"],"neutral")
    def test_upsert_is_idempotent(self):
        item=self.db.get("fixture-7");self.db.upsert(item);self.db.upsert(item)
        self.assertEqual(self.db.page("cilantro")["total"],1)
    def test_english_alias_typo_can_match(self):
        result=self.db.page("cillantro")
        self.assertEqual(result["search_mode"],"fuzzy")
        self.assertEqual(result["entries"][0]["id"],"fixture-7")
    def test_search_expression_is_not_sql_or_fts_injection(self):
        self.assertEqual(self.db.page('" OR 1=1 --')["total"],0)


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.p=Preferences(Path(self.temp.name)/"private.json")
        self.envpatch=patch("atlas.preferences.ENV",{});self.envpatch.start()
    def tearDown(self):self.envpatch.stop();self.temp.cleanup()
    def test_base_url_normalization(self):
        out=self.p.save({"lm_base_url":"http://localhost:1234"})
        self.assertEqual(out["lm_base_url"],"http://localhost:1234/v1")
    def test_secrets_are_write_only(self):
        out=self.p.save({"lm_api_key":"fixture-secret"})
        self.assertTrue(out["has_lm_api_key"]);self.assertNotIn("lm_api_key",out)
        self.assertNotIn("fixture-secret",json.dumps(out))
    def test_blank_key_keeps_saved_secret_and_clear_is_explicit(self):
        self.p.save({"lm_api_key":"fixture-secret"});self.p.save({"lm_api_key":""})
        self.assertTrue(self.p.public()["has_lm_api_key"])
        self.p.save({"clear_lm_api_key":True});self.assertFalse(self.p.public()["has_lm_api_key"])
    def test_language_choice_persists(self):
        self.p.save({"ui_language":"en","translation_language":"zh"})
        self.assertEqual(self.p.public()["ui_language"],"en")
        self.assertEqual(self.p.public()["translation_language"],"zh-Hans")
    def test_invalid_model_url_rejected(self):
        with self.assertRaises(ValueError):self.p.save({"lm_base_url":"file:///etc/passwd"})
    def test_proxy_credentials_are_not_returned_to_the_browser(self):
        with self.assertRaises(ValueError):self.p.save({"proxy_url":"http://name:password@localhost:7890"})
    def test_model_selection_must_match_tested_available_ids(self):
        self.p.save({"lm_model":"unknown"});self.p.model_test({"ok":True,"base_url":"http://127.0.0.1:1234/v1","available_model_ids":["known"]})
        self.assertFalse(self.p.public()["model_ready"])
    def test_changed_key_requires_a_new_connection_test(self):
        self.p.model_test({"ok":True,"base_url":"http://127.0.0.1:1234/v1","available_model_ids":["known"]})
        self.assertTrue(self.p.public()["model_ready"])
        self.p.save({"lm_api_key":"new-fixture-key"})
        self.assertFalse(self.p.public()["model_ready"])


class FallbackAndImageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.reader=Reader(Store(Path(self.temp.name)/"cache.sqlite"))
        self.entry={"id":"example","name":"Example","english":"Example","review_state":"curated","wiki":{"enwiki":"Example"},"forms":[{"id":"overview","commons_query":"Example"}],"commons_query":"Example"}
    async def asyncTearDown(self):self.temp.cleanup()
    async def test_missing_chinese_uses_english_without_claiming_connection_failure(self):
        with patch("atlas.providers.entry_for",return_value=self.entry),patch("atlas.wiki_languages.resolve_languages",new_callable=AsyncMock,return_value={"mapping":{"en":"Example"},"state":"resolved"}),patch.object(self.reader,"_article_one",new_callable=AsyncMock,return_value={"source":"enwiki","mode":"article"}) as remote:
            result=await self.reader.article("example","auto",preferred="zh")
        self.assertEqual(result["source"],"enwiki");self.assertEqual(result["fallback"]["reason"],"missing_language")
        self.assertEqual(remote.await_count,1)
    async def test_403_can_fall_back_to_a_different_available_language(self):
        item={**self.entry,"wiki":{"zhwiki":"示例","enwiki":"Example"}}
        with patch("atlas.providers.entry_for",return_value=item),patch.object(self.reader,"_article_one",new_callable=AsyncMock,side_effect=[SourceFailure("403",code="forbidden",status=403),{"source":"enwiki","mode":"article"}]):
            result=await self.reader.article("example","auto")
        self.assertEqual(result["fallback"]["reason"],"connection_failure")
    async def test_missing_language_is_not_retrieved_as_a_fake_article(self):
        with patch("atlas.providers.entry_for",return_value=self.entry),patch("atlas.wiki_languages.resolve_languages",new_callable=AsyncMock,return_value={"mapping":{"en":"Example"},"state":"resolved"}):
            result=await self.reader.article("example","zhwiki")
        self.assertEqual(result["mode"],"unavailable")
    async def test_failed_metadata_lookup_is_not_evidence_of_a_missing_page(self):
        unresolved={**self.entry,"review_state":"reference_only","wiki":{},"resolution_error":{"code":"forbidden","http_status":403,"host":"en.wikipedia.org"}}
        with patch("atlas.providers.entry_for",return_value=unresolved),patch("atlas.providers.resolve_entry",new_callable=AsyncMock,return_value=unresolved):
            with self.assertRaises(SourceFailure) as error:await self.reader.article("example","auto")
        self.assertEqual(error.exception.code,"forbidden")
        self.assertEqual(error.exception.status,403)
    async def test_image_direct_mode_uses_remote_url(self):
        image={"id":"a"*24,"provider":"commons","thumbnail_url":"https://upload.wikimedia.org/example.jpg"}
        with patch("atlas.providers.preferences.values",return_value={"image_mode":"direct"}):
            result=self.reader.image_delivery({"images":[image]})
        self.assertEqual(result["images"][0]["display_url"],image["thumbnail_url"])
    async def test_proxy_mode_is_optional(self):
        image={"id":"a"*24,"provider":"commons","thumbnail_url":"https://upload.wikimedia.org/example.jpg"}
        with patch("atlas.providers.preferences.values",return_value={"image_mode":"proxy"}):
            result=self.reader.image_delivery({"images":[image]})
        self.assertEqual(result["images"][0]["display_url"],"/api/media/"+"a"*24)
    async def test_wikidata_primary_image_avoids_broad_keyword_guessing(self):
        params=self.reader.commons_params({**self.entry,"primary_image":"Example plant.jpg"},"overview")
        self.assertEqual(params["titles"],"File:Example plant.jpg");self.assertNotIn("generator",params)
    async def test_google_frame_is_not_forced_through_a_proxy(self):
        with patch("atlas.web_sources.frame_check",new_callable=AsyncMock,return_value={"can_try":False,"code":"frame_denied"}):
            result=await frame_capability({**self.entry,"forms":[{"id":"overview","image_query":"Example"}]},"google")
        self.assertFalse(result["can_try"])


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.pathpatch=patch.object(preferences,"path",Path(self.temp.name)/"config.json");self.pathpatch.start()
        self.envpatch=patch("atlas.preferences.ENV",{});self.envpatch.start()
        self.client=TestClient(app)
    def tearDown(self):self.pathpatch.stop();self.envpatch.stop();self.temp.cleanup()
    def test_settings_api_persists_language_and_hides_secret(self):
        response=self.client.post("/api/settings",json={"ui_language":"en","lm_base_url":"http://localhost:1234","lm_api_key":"not-a-real-token"})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()["ui_language"],"en")
        value=self.client.get("/api/settings").json();self.assertTrue(value["has_lm_api_key"]);self.assertNotIn("lm_api_key",value)
    def test_model_list_handshake_marks_the_configured_connection_ready(self):
        response=httpx.Response(200,json={"data":[{"id":"fixture-chat-model"}]},request=httpx.Request("GET","http://127.0.0.1:1234/v1/models"))
        fake=AsyncMock();fake.__aenter__.return_value=fake;fake.get.return_value=response
        with patch("atlas.providers.httpx.AsyncClient",return_value=fake):
            result=self.client.post("/api/settings/test-model")
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()["models"][0]["id"],"fixture-chat-model")
        self.assertTrue(self.client.get("/api/settings").json()["model_ready"])
    def test_empty_model_list_is_not_translation_ready(self):
        response=httpx.Response(200,json={"data":[]},request=httpx.Request("GET","http://127.0.0.1:1234/v1/models"))
        fake=AsyncMock();fake.__aenter__.return_value=fake;fake.get.return_value=response
        with patch("atlas.providers.httpx.AsyncClient",return_value=fake):self.client.post("/api/settings/test-model")
        self.assertFalse(self.client.get("/api/settings").json()["model_ready"])
    def test_browser_cors_plan_uses_official_host(self):
        response=self.client.get("/api/browser-plan/article/parsley?source=enwiki").json()
        self.assertEqual(response["url"],"https://en.wikipedia.org/w/api.php")
        self.assertEqual(response["params"]["origin"],"*")
    def test_nested_catalogue_and_pagination_endpoints(self):
        response=self.client.get("/api/catalog?scope=botanical&limit=7").json()
        self.assertGreaterEqual(response["total"],1000);self.assertEqual(len(response["entries"]),7)
        nodes=self.client.get("/api/catalog/nodes?parent=root-botanical&language=en").json()["nodes"]
        self.assertTrue(any(n["label"]=="Lamiaceae" for n in nodes))


if __name__=="__main__":unittest.main()
