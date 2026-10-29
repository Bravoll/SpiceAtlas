"""Source-backed English IPA/audio and local, explicitly automatic Mandarin pinyin."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlsplit

from pypinyin import Style, lazy_pinyin
from opencc import OpenCC

from .network import SourceFailure, fetch_json
from .storage import Store, now_iso

DICTIONARY = 'https://api.dictionaryapi.dev/api/v2/entries/en/'
DICTIONARY_GATE = asyncio.Semaphore(2)
_simplify = OpenCC('t2s')


def name_metadata(item):
    chinese = item.get('name_zh') or ''
    english = (item.get('name_en') or item.get('english') or '').strip()
    scientific = (item.get('scientific') or '').strip()
    # A taxon is not an English common name. Do not synthesize Latin labels.
    if english.casefold() == scientific.casefold() or not re.search('[a-zA-Z]', english):
        english = ''
    return {
        'pinyin': ' '.join(lazy_pinyin(_simplify.convert(chinese), style=Style.TONE)) if chinese else '',
        'pinyin_automatic': True,
        'spoken_english': english[:120],
    }


def safe_audio(url):
    if url.startswith('//'):
        url = 'https:' + url
    parsed = urlsplit(url)
    allowed = {
        'api.dictionaryapi.dev': '/media/pronunciations/',
        'upload.wikimedia.org': '/wikipedia/',
        'ssl.gstatic.com': '/dictionary/static/sounds/',
    }
    return url if parsed.scheme == 'https' and not parsed.username and parsed.hostname in allowed and parsed.path.startswith(allowed[parsed.hostname]) else ''


def parse_phonetics(data, word):
    if not isinstance(data, list):
        raise ValueError('Invalid dictionary response')
    variants = []
    for entry in data[:6]:
        if not isinstance(entry, dict) or str(entry.get('word', '')).casefold() != word.casefold():
            continue
        for sound in entry.get('phonetics', [])[:16]:
            ipa = str(sound.get('text') or '').strip()[:180]
            audio = safe_audio(str(sound.get('audio') or ''))
            if not ipa and not audio:
                continue
            region = 'UK' if re.search(r'(?:[-_]uk|[-_]gb)(?:[-_.]|$)', audio, re.I) else 'US' if re.search(r'[-_]us(?:[-_.]|$)', audio, re.I) else ''
            source = str(sound.get('sourceUrl') or '')
            source = source if urlsplit(source).scheme == 'https' else 'https://en.wiktionary.org/wiki/' + quote(word)
            license_data = sound.get('license') or entry.get('license') or {}
            license_url = str(license_data.get('url') or '')
            variants.append({'ipa': ipa, 'audio_url': audio, 'region': region, 'source_url': source,
                             'license': str(license_data.get('name') or ''),
                             'license_url': license_url if urlsplit(license_url).scheme == 'https' else ''})
    variants = list({(v['ipa'], v['audio_url']): v for v in variants}.values())
    variants.sort(key=lambda row: {'UK': 0, '': 1, 'US': 2}[row['region']])
    return {'word': word, 'variants': variants[:8], 'source_url': 'https://en.wiktionary.org/wiki/' + quote(word),
            'provider': 'Free Dictionary API / Wiktionary', 'fetched_at': now_iso()}


class Pronunciations:
    def __init__(self, store=None):
        self.store = store or Store()
        self.locks = {}

    async def for_entry(self, item, online=True):
        meta = name_metadata(item)
        word = meta['spoken_english'].lower()
        base = {**meta, 'word': meta['spoken_english'], 'variants': [], 'source_url': '', 'provider': ''}
        if not word:
            return base
        key = 'pronunciation:v1:' + word
        cached = self.store.get(key)
        if cached and (not cached['stale'] or not online):
            return {**base, **cached['value'], 'delivery': 'cache'}
        if not online:
            return {**base, 'unavailable': True}
        # Same-word requests share work; the lock key includes the version-local cache.
        async with self.locks.setdefault((str(self.store.path), word), asyncio.Lock()):
            cached = self.store.get(key)
            if cached and not cached['stale']:
                return {**base, **cached['value'], 'delivery': 'cache'}
            try:
                data = await fetch_json(DICTIONARY + quote(word, safe=''), timeout=8, gate=DICTIONARY_GATE)
                result = parse_phonetics(data, word)
                self.store.put(key, result, 30*86400 if result['variants'] else 21600)
                return {**base, **result, 'delivery': 'live'}
            except (SourceFailure, ValueError, TypeError, AttributeError):
                if cached:
                    return {**base, **cached['value'], 'delivery': 'stale_cache'}
                self.store.put(key, {**base, 'unavailable': True}, 600)
                return {**base, 'unavailable': True}


pronunciations = Pronunciations()
