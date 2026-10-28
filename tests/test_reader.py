import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from atlas.content import article_content, translation_blocks, translated_html
from atlas.providers import Reader, SourceError, select_images
from atlas.catalogue import catalogue
ENTRIES={"parsley":catalogue.get("parsley")}
from atlas.storage import Store
from main import app


SOURCE = "https://en.wikipedia.org/wiki/Parsley"
RAW = """<div class="mw-parser-output"><p>Parsley is a culinary plant. See <a href="/wiki/Herb">herbs</a> and a note <sup><a href="#cite_note-1" id="cite_ref-1">[1]</a></sup>.</p><div class="mw-heading"><h2 id="Culinary">Culinary uses</h2></div><p>A complete paragraph about culinary uses and fresh leaves.</p><h2 id="Other">Other information</h2><p>Additional text.</p><h2 id="References">References</h2><ol><li id="cite_note-1">Reference <a href="https://example.org/paper">paper</a> <a href="#cite_ref-1">back</a></li></ol><script>window.stolen=1</script><p onclick="alert(1)"><a href="javascript:alert(1)">Unsafe link</a></p></div>"""


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.article = article_content(RAW, SOURCE, "parsley-en-42")

    def test_source_links_are_absolute(self):
        doc = BeautifulSoup(self.article["html"], "html.parser")
        link = doc.find("a", string="herbs")
        self.assertEqual(link["href"], "https://en.wikipedia.org/wiki/Herb")
        self.assertEqual(link["target"], "_blank")
        self.assertIn("noopener", link["rel"])

    def test_reference_and_backlink_work_in_full_view(self):
        doc = BeautifulSoup(self.article["html"], "html.parser")
        for link in doc.select('a[href^="#"]'):
            self.assertIsNotNone(doc.find(id=link["href"][1:]))

    def test_omitted_focus_reference_opens_original_anchor(self):
        doc = BeautifulSoup(self.article["focus_html"], "html.parser")
        note = doc.find("a", string="[1]")
        self.assertEqual(note["href"], SOURCE + "#cite_note-1")
        self.assertNotIn("Other information", self.article["focus_html"])
        self.assertIn("Culinary uses", self.article["focus_html"])
        self.assertEqual(self.article["focus_section_count"], 1)

    def test_sources_cannot_run_scripts_or_event_handlers(self):
        doc = BeautifulSoup(self.article["html"], "html.parser")
        self.assertFalse(doc.find("script"))
        self.assertFalse(doc.find(onclick=True))
        self.assertFalse(doc.find("a", href=lambda s:s and s.startswith("javascript:")))

    def test_namespaces_prevent_source_collisions(self):
        first = set(rev["id"] for rev in BeautifulSoup(self.article["html"], "html.parser").find_all(id=True))
        second = article_content(RAW, SOURCE, "another-source")
        second = set(rev["id"] for rev in BeautifulSoup(second["html"], "html.parser").find_all(id=True))
        self.assertFalse(first & second)

    def test_translation_keeps_links_and_escapes_model_html(self):
        block = translation_blocks(self.article["html"])[0]
        result = translated_html("<script>bad()</script> " + block["text"], block["links"])
        doc = BeautifulSoup(result, "html.parser")
        self.assertFalse(doc.find("script"))
        self.assertEqual(len(doc.find_all("a")), 2)
        self.assertFalse(doc.find(id=True))

    def test_missing_translation_link_is_rejected(self):
        with self.assertRaises(ValueError):
            translated_html("丢失了链接", {"⟪LINK_0⟫": '<a href="https://example.org">原名</a>'})

    def test_image_relevance_excludes_similar_but_different_materials(self):
        candidates = [{"title":"Parsley Dried.JPG"},{"title":"Cow Parsley - geograph.jpg"},{"title":"Lorry near Parsley Hay.jpg"}]
        selected = select_images(ENTRIES["parsley"], "flakes", candidates)
        self.assertEqual([x["title"] for x in selected], ["Parsley Dried.JPG"])


class CacheAndProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.reader = Reader(Store(Path(self.temp.name) / "cache.sqlite"))

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_cache_does_not_request_remote_content(self):
        cached = {"mode":"article","title":"cached","revision_id":42}
        self.reader.store.put("article:parsley:zhwiki:zh-hans", cached)
        with patch("atlas.providers.request_json", new_callable=AsyncMock) as remote:
            result = await self.reader.article("parsley")
            self.assertEqual(result["delivery"], "cache")
            remote.assert_not_called()

    async def test_network_failure_preserves_previous_version(self):
        cached = {"mode":"article","title":"older","revision_id":42}
        self.reader.store.put("article:parsley:zhwiki:zh-hans", cached)
        with patch("atlas.providers.request_json", new_callable=AsyncMock, side_effect=SourceError("网络暂不可用")):
            result = await self.reader.article("parsley", refresh=True)
            self.assertEqual(result["revision_id"], 42)
            self.assertEqual(result["delivery"], "stale_cache")
            self.assertIn("网络", result["warning"])

    async def test_external_providers_are_not_fake_embedded_results(self):
        with patch("atlas.providers.request_json", new_callable=AsyncMock) as remote:
            baidu = await self.reader.article("parsley", "baidu")
            bing = await self.reader.images("parsley", "bing")
            self.assertEqual(baidu["mode"], "external")
            self.assertEqual(bing["mode"], "external")
            self.assertFalse(bing["images"])
            remote.assert_not_called()

    async def test_missing_google_key_has_explicit_state(self):
        with patch("atlas.providers.setting", return_value=""):
            result = await self.reader.images("parsley", "google")
        self.assertEqual(result["mode"], "needs_key")
        self.assertIn("google", result["gateways"])

    async def test_form_is_validated(self):
        with self.assertRaises(SourceError):
            await self.reader.images("coriander", form="../../secret")

    async def test_image_identifier_cannot_be_a_file_path(self):
        with self.assertRaises(SourceError):
            await self.reader.image_file("../config.local.json")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalog_and_related_entries(self):
        data = self.client.get("/api/catalog").json()
        self.assertGreaterEqual(data["total"], 13)
        self.assertLessEqual(len(data["entries"]), data["limit"])
        item = self.client.get("/api/entry/coriander").json()
        self.assertIn("parsley", {x["id"] for x in item["related"]})
        self.assertNotIn("basil", {x["id"] for x in item["related"]})
        self.assertEqual({f["theme"] for f in item["forms"]}, {"leaf","seed"})

    def test_unknown_entry_returns_404(self):
        self.assertEqual(self.client.get("/api/entry/not-an-entry").status_code, 404)

    def test_home_and_assets(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("script-src 'self'", self.client.get("/").headers["content-security-policy"])
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_cross_origin_mutation_is_rejected(self):
        result = self.client.post("/api/translate", json={"entry_id":"parsley","source":"enwiki"}, headers={"origin":"https://unrelated.example"})
        self.assertEqual(result.status_code, 403)


if __name__ == "__main__":
    unittest.main()
