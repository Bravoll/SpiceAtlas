"""v0.5 regression: optimistic startup, safe phonetics and local random selection."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from atlas.catalogue import Catalogue
from atlas.health import Health
from atlas.preferences import Preferences
from atlas.pronunciation import Pronunciations, name_metadata, parse_phonetics, safe_audio
from atlas.resources import available, resource_plan
from atlas.storage import Store
from atlas.network import SourceFailure
from main import app


class ReadingSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.p = Preferences(Path(self.temp.name)/'settings.json')
        self.env = patch('atlas.preferences.ENV', {})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_reader_and_startup_preferences_roundtrip(self):
        self.p.save({'reader_font_size':24,'reader_line_height':2.1,'reader_font':'kai',
                     'animation_level':3,'startup_mode':'random','random_scope':'culinary'})
        out = Preferences(self.p.path).public()
        self.assertEqual(out['reader_font_size'],24)
        self.assertEqual(out['startup_mode'],'random')
        self.assertEqual(out['animation_level'],3)
        self.assertNotIn('lm_api_key',out)

    def test_invalid_reading_values_are_rejected_without_partial_save(self):
        for patch_value in ({'reader_font_size':400},{'reader_font_size':17.5},{'reader_font_size':True},
                            {'reader_line_height':0.8},{'reader_font':'<script>'},
                            {'animation_level':4},{'animation_level':1.1},{'startup_mode':'unknown'}):
            with self.subTest(value=patch_value),self.assertRaises(ValueError):
                self.p.save(patch_value)
        self.assertEqual(self.p.values()['reader_font_size'],17)

    def test_checking_is_optimistic_even_if_partial_results_contain_failures(self):
        report={'phase':'checking','services':{'google':{'ok':False}}}
        self.assertTrue(available('google',report))
        self.assertFalse(available('google',{**report,'phase':'ready'}))
        health=Health()
        self.assertEqual(health.report()['phase'],'checking')
        self.assertEqual(health.report()['services'],{})

    def test_browser_probe_does_not_disable_services_before_complete_pass(self):
        health=Health()
        with patch('atlas.health.activity.notify') as notify:
            report=health.browser_results([{'id':'commons','ok':False}])
            self.assertEqual(report['phase'],'checking')
            self.assertTrue(available('commons',report))
            notify.assert_not_called()


class RandomSelectionTests(unittest.TestCase):
    def test_only_admitted_records_in_requested_scope_are_sampled(self):
        with tempfile.TemporaryDirectory() as td:
            cat=Catalogue(Path(td)/'catalogue.sqlite3',seed=False)
            for key,scope in [('a','culinary'),('b','culinary'),('x','botanical')]:
                cat.upsert({'id':key,'name_en':key,'scope':scope})
            self.assertEqual(cat.random_entry('culinary','a')['id'],'b')
            self.assertEqual(cat.random_entry('botanical')['id'],'x')
            self.assertEqual(cat.random_entry('all','a')['eligible_count'],2)
            self.assertIsNone(cat.random_entry('botanical','x'))

    def test_random_api_is_local_and_excludes_current_entry(self):
        with patch('atlas.network.fetch_json',new_callable=AsyncMock) as remote:
            response=TestClient(app).get('/api/catalog/random?scope=culinary&exclude=parsley')
            self.assertEqual(response.status_code,200)
            self.assertNotEqual(response.json()['id'],'parsley')
            remote.assert_not_called()
        self.assertEqual(TestClient(app).get('/api/catalog/random?scope=invalid').status_code,422)


class PhoneticsTests(unittest.TestCase):
    def test_chinese_pinyin_and_common_english_name_are_separate_from_latin(self):
        value=name_metadata({'name_zh':'欧芹','name_en':'Parsley','scientific':'Petroselinum crispum'})
        self.assertEqual(value['pinyin'],'ōu qín')
        self.assertEqual(value['spoken_english'],'Parsley')
        self.assertEqual(name_metadata({'name_en':'Petroselinum crispum','scientific':'Petroselinum crispum'})['spoken_english'],'')
        self.assertTrue(value['pinyin_automatic'])

    def test_uk_is_prioritized_and_audio_keeps_licensing(self):
        out=parse_phonetics([{'word':'parsley','phonetics':[
            {'text':'/us/','audio':'https://api.dictionaryapi.dev/media/pronunciations/en/parsley-us.mp3'},
            {'text':'/uk/','audio':'https://api.dictionaryapi.dev/media/pronunciations/en/parsley-uk.mp3',
             'sourceUrl':'https://commons.wikimedia.org/wiki/File:Sound.ogg','license':{'name':'CC BY-SA','url':'https://creativecommons.org/licenses/by-sa/4.0/'}}
        ]}],'parsley')
        self.assertEqual(out['variants'][0]['region'],'UK')
        self.assertEqual(out['variants'][0]['license'],'CC BY-SA')
        self.assertIn('wiktionary.org',out['source_url'])

    def test_wrong_word_and_unsafe_audio_are_not_played(self):
        self.assertEqual(parse_phonetics([{'word':'other','phonetics':[{'text':'/bad/'}]}],'parsley')['variants'],[])
        for url in ('javascript:alert(1)','https://evil.example/sound.mp3','https://api.dictionaryapi.dev.evil.example/media/pronunciations/a.mp3','http://upload.wikimedia.org/a.mp3'):
            self.assertEqual(safe_audio(url),'')

    def test_absent_ipa_is_not_fabricated(self):
        self.assertEqual(parse_phonetics([{'word':'parsley','phonetics':[]}],'parsley')['variants'],[])


class PronunciationCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_dictionary_lookup_does_not_wait_for_wikipedia_request_gate(self):
        import atlas.network as network
        gate=asyncio.Semaphore(1)
        fake=AsyncMock();fake.__aenter__.return_value=fake
        fake.get.return_value=httpx.Response(200,json=[{'word':'parsley','phonetics':[{'text':'/ipa/'}]}],request=httpx.Request('GET','https://api.dictionaryapi.dev/api/v2/entries/en/parsley'))
        with tempfile.TemporaryDirectory() as td,patch.object(network,'GATE',gate),patch('atlas.network.httpx.AsyncClient',return_value=fake):
            service=Pronunciations(Store(Path(td)/'cache.sqlite3'))
            async with gate:
                value=await asyncio.wait_for(service.for_entry({'name_en':'Parsley','scientific':'Petroselinum crispum'}),timeout=1)
            self.assertEqual(value['delivery'],'live')

    async def test_failed_dictionary_request_is_not_missing_ipa_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            service=Pronunciations(Store(Path(td)/'cache.sqlite3'))
            entry={'name_en':'Cumin','scientific':'Cuminum cyminum'}
            with patch('atlas.pronunciation.fetch_json',new_callable=AsyncMock,side_effect=SourceFailure('Timeout',code='timeout')) as fetch:
                value=await service.for_entry(entry)
                self.assertTrue(value['unavailable'])
                self.assertEqual(value['spoken_english'],'Cumin')
                self.assertEqual(value['variants'],[])
                await service.for_entry(entry)
                self.assertEqual(fetch.await_count,1)

    async def test_cache_and_network_failure_keep_browser_fallback_available(self):
        with tempfile.TemporaryDirectory() as td:
            service=Pronunciations(Store(Path(td)/'cache.sqlite3'))
            entry={'name_en':'Parsley','name_zh':'欧芹','scientific':'Petroselinum crispum'}
            with patch('atlas.pronunciation.fetch_json',new_callable=AsyncMock,return_value=[{'word':'parsley','phonetics':[{'text':'/ipa/'}]}]) as fetch:
                first=await service.for_entry(entry)
                second=await service.for_entry(entry)
                self.assertEqual(first['delivery'],'live')
                self.assertEqual(second['delivery'],'cache')
                self.assertEqual(fetch.await_count,1)
            with patch('atlas.pronunciation.fetch_json',new_callable=AsyncMock) as fetch:
                disabled=await service.for_entry({'name_en':'Basil','scientific':'Ocimum basilicum'},online=False)
                self.assertEqual(disabled['spoken_english'],'Basil')
                self.assertEqual(disabled['variants'],[])
                fetch.assert_not_called()

    async def test_latin_name_never_requests_dictionary(self):
        with tempfile.TemporaryDirectory() as td:
            service=Pronunciations(Store(Path(td)/'cache.sqlite3'))
            with patch('atlas.pronunciation.fetch_json',new_callable=AsyncMock) as fetch:
                value=await service.for_entry({'name_en':'Ocimum basilicum','scientific':'Ocimum basilicum'})
                self.assertEqual(value['spoken_english'],'')
                fetch.assert_not_called()


if __name__=='__main__':
    unittest.main()
