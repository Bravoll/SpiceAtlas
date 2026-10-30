"""Reviewed public hosts and per-entry candidates, separate from article bodies."""
import json
from functools import lru_cache
from urllib.parse import urlsplit
from .storage import ROOT

@lru_cache(maxsize=1)
def registry():return json.loads((ROOT/'data/other_sources.json').read_text('utf-8'))

def provider_for(url):
    try:p=urlsplit(url);port=p.port
    except ValueError:return None
    if p.scheme!='https' or p.username or p.password or port not in (None,443):return None
    if not p.hostname or any(word in p.hostname for word in ['stage.','staging.','test.']):return None
    return next((row for row in registry()['providers'] if p.hostname.lower() in row['hosts']),None)
