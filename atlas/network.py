"""Public-source networking with useful diagnostics and no credential leakage."""
from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from .preferences import preferences
from .storage import now_iso

GATE = asyncio.Semaphore(1)
EVENTS = deque(maxlen=80)


class SourceFailure(Exception):
    def __init__(self, message, *, code="source_error", status=None, host=None, excerpt=""):
        super().__init__(message)
        self.code, self.status, self.host, self.excerpt = code, status, host, excerpt

    def public(self):
        return {"message": str(self), "code": self.code, "http_status": self.status, "host": self.host, "response_excerpt": self.excerpt}


def client_options(timeout=None):
    p = preferences.values()
    options = {"timeout": timeout or p["timeout_seconds"], "follow_redirects": False,
               "trust_env": p["trust_env"], "headers": {"User-Agent": p["user_agent"], "Accept": "application/json"}}
    if p["proxy_url"]:
        options["proxy"] = p["proxy_url"]
    return options


async def fetch_json(url, params=None, *, timeout=None, headers=None, gate=None):
    host = urlsplit(url).hostname
    options = client_options(timeout)
    if headers:
        options["headers"].update(headers)
    try:
        async with httpx.AsyncClient(**options) as client:
            async with (gate or GATE):
                response = await client.get(url, params=params)
                if response.status_code in (429, 503):
                    await asyncio.sleep(2)
                    response = await client.get(url, params=params)
        EVENTS.append({"at": now_iso(), "host": host, "status": response.status_code})
        if response.status_code >= 400:
            excerpt = BeautifulSoup(response.text[:4000], "html.parser").get_text(" ", strip=True)[:240]
            code = {403:"forbidden",404:"not_found",429:"rate_limited",503:"busy"}.get(response.status_code,"http_error")
            raise SourceFailure(f"来源请求被拒绝或未完成（HTTP {response.status_code}）。", code=code, status=response.status_code, host=host, excerpt=excerpt)
        if len(response.content) > 16_000_000:
            raise SourceFailure("Source response is too large", code="too_large", host=host)
        try:
            data = response.json()
        except ValueError:
            excerpt = BeautifulSoup(response.text[:2000], "html.parser").get_text(" ", strip=True)[:160]
            raise SourceFailure("来源返回了网页而不是 API 数据，可能存在网络拦截或验证页面。", code="not_json", host=host, excerpt=excerpt) from None
        if isinstance(data, dict) and "error" in data:
            error = data["error"]
            code = error.get("code", "source_error")
            raise SourceFailure(error.get("info", "Source API error"), code=code, host=host)
        return data
    except SourceFailure:
        raise
    except httpx.TimeoutException:
        raise SourceFailure("来源连接超时。", code="timeout", host=host) from None
    except (httpx.HTTPError, ImportError, ValueError):
        raise SourceFailure("无法连接来源，请检查网络、代理和 TLS 配置。", code="network_error", host=host) from None


async def diagnostics():
    probes = [
        ("zhwiki","https://zh.wikipedia.org/w/api.php",{"action":"parse","page":"歐芹","redirects":1,"prop":"revid","format":"json"}),
        ("enwiki","https://en.wikipedia.org/w/api.php",{"action":"parse","page":"Parsley","redirects":1,"prop":"revid","format":"json"}),
        ("commons","https://commons.wikimedia.org/w/api.php",{"action":"query","generator":"search","gsrnamespace":6,"gsrsearch":"parsley","gsrlimit":1,"prop":"imageinfo","iiprop":"url","format":"json"}),
        ("wikidata","https://www.wikidata.org/w/api.php",{"action":"wbsearchentities","search":"parsley","language":"en","limit":1,"format":"json"}),
        ("gbif","https://api.gbif.org/v1/species/match",{"name":"Lamiaceae","rank":"FAMILY"}),
    ]
    output = []
    for provider,url,params in probes:
        try:
            await fetch_json(url, params, timeout=10)
            output.append({"provider":provider,"ok":True,"host":urlsplit(url).hostname,"http_status":200})
        except SourceFailure as exc:
            output.append({"provider":provider,"ok":False,**exc.public()})
    p = preferences.public()
    return {"checked_at":now_iso(),"results":output,"proxy_configured":bool(p["proxy_url"]),"environment_proxy_enabled":p["trust_env"],"user_agent":p["user_agent"],
            "note":"HTTP 403 不等于 API 不开放。请结合响应说明、请求标识、网络与代理检查。报告不包含密钥。"}
