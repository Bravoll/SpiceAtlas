"""Partial connectivity must not erase verified links or cancel independent discovery."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from atlas.network import SourceFailure
from atlas.storage import Store
from atlas.wiki_languages import cache_key, resolve_languages, same_identity

ENTRY={'id':'parsley','scientific':'Petroselinum crispum','name_en':'Parsley','name_zh':'欧芹','wiki':{'enwiki':'Parsley'},'wikidata_id':'Q25284'}

class IndependentLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'cache.sqlite3')
    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_chinese_discovery_continues_after_english_failure(self):
        async def query(lang,params):
            if lang=='en':raise SourceFailure('English timed out',code='timeout')
            if params.get('list')=='search':return {'query':{'search':[{'pageid':11}]}}
            return {'query':{'pages':[{'title':'歐芹','pageprops':{'wikibase_item':'Q25284'}}]}}
        with patch('atlas.wiki_languages.query',side_effect=query):value=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹');self.assertEqual(value['state'],'unconfirmed')
        self.assertTrue(value['diagnostics'])

    async def test_one_failed_chinese_query_does_not_discard_a_successful_query(self):
        async def query(lang,params):
            if lang=='en':return {'query':{'pages':[{'title':'Parsley','pageid':1}]}}
            if params.get('list')=='search':
                if params['srsearch']=='欧芹':raise SourceFailure('Chinese name timed out',code='timeout')
                return {'query':{'search':[{'pageid':11}]}}
            return {'query':{'pages':[{'title':'歐芹','pageprops':{'wikibase_item':'Q25284'}}]}}
        with patch('atlas.wiki_languages.query',side_effect=query):value=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹');self.assertEqual(value['state'],'unconfirmed')

    async def test_failed_refresh_preserves_previously_discovered_languages(self):
        self.store.put(cache_key(ENTRY),{'mapping':{'en':'Parsley','zh':'歐芹','fr':'Persil'},'methods':{'en':'english_anchor','zh':'english_langlink','fr':'english_langlink'},'state':'resolved'})
        with patch('atlas.wiki_languages.query',side_effect=SourceFailure('Offline',code='network_error')):
            value=await resolve_languages(ENTRY,self.store,refresh=True)
        self.assertEqual(value['mapping']['fr'],'Persil');self.assertEqual(value['mapping']['zh'],'歐芹')
        self.assertEqual(value['state'],'unconfirmed');self.assertIn('zh',value['cached_fallback_languages'])

    async def test_expired_mapping_is_still_available_on_network_failure(self):
        self.store.put(cache_key(ENTRY),{'mapping':{'en':'Parsley','zh':'歐芹'},'methods':{'zh':'english_langlink'},'state':'resolved'},ttl=-1)
        with patch('atlas.wiki_languages.query',side_effect=SourceFailure('Offline',code='network_error')):
            value=await resolve_languages(ENTRY,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹');self.assertEqual(value['state'],'unconfirmed')

    def test_conflicting_wikidata_identity_rejects_related_species_mention(self):
        page={'title':'A related plant','pageprops':{'wikibase_item':'Q99999'},'extract':'This plant is often confused with Petroselinum crispum.'}
        self.assertFalse(same_identity(page,ENTRY))

    async def test_english_anchor_identity_guides_unlinked_chinese_search(self):
        entry={**ENTRY,'wikidata_id':None}
        async def query(lang,params):
            if lang=='en':return {'query':{'pages':[{'title':'Parsley','pageid':1,'pageprops':{'wikibase_item':'Q25284'}}]}}
            if params.get('list')=='search':return {'query':{'search':[{'pageid':10},{'pageid':11}]}}
            return {'query':{'pages':[{'title':'Wrong species','pageprops':{'wikibase_item':'Q99999'},'extract':'Related to Petroselinum crispum.'},{'title':'歐芹','pageprops':{'wikibase_item':'Q25284'}}]}}
        with patch('atlas.wiki_languages.query',side_effect=query):value=await resolve_languages(entry,self.store)
        self.assertEqual(value['mapping']['zh'],'歐芹')
