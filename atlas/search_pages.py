"""Bounded first-page search adapters. No verification bypass or private endpoints."""
from __future__ import annotations
import base64,asyncio
from urllib.parse import urlsplit,parse_qs,unquote,urljoin
import httpx
from bs4 import BeautifulSoup
from .network import client_options

ENGINES={
 'google':('https://www.google.com/search',{'hl':'en','num':10}),
 'bing':('https://www.bing.com/search',{'mkt':'en-US','setlang':'en','count':10,'first':1}),
 'bing_cn':('https://cn.bing.com/search',{'mkt':'zh-CN','setlang':'zh-Hans','count':10,'first':1}),
}

def external_link(value):
    initial=urlsplit(value)
    if value.startswith('/url?') or initial.hostname in {'google.com','www.google.com'} and initial.path=='/url':
        query=parse_qs(urlsplit(value).query);value=(query.get('q') or query.get('url') or [''])[0]
    parsed=urlsplit(value)
    if parsed.hostname and parsed.hostname.endswith('bing.com') and parsed.path.startswith('/ck/'):
        encoded=parse_qs(parsed.query).get('u',[''])[0]
        if encoded.startswith('a1'):
            try:value=base64.urlsafe_b64decode(encoded[2:]+'===').decode('utf-8')
            except (ValueError,UnicodeError):return None
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:return None
    if any(parsed.hostname==x or parsed.hostname.endswith('.'+x) for x in ['google.com','bing.com','microsoft.com']):return None
    return value

def parse_results(html,engine):
    soup=BeautifulSoup(html,'html.parser');rows=[];seen=set()
    headings=soup.select('.b_algo h2,#b_results h2') if engine.startswith('bing') else soup.select('h3')
    for heading in headings:
        anchor=heading.find('a') or heading.find_parent('a')
        if not anchor:continue
        url=external_link(anchor.get('href',''))
        if not url or url in seen:continue
        seen.add(url);parent=(heading.find_parent(class_='b_algo') or heading.find_parent('li') or heading.parent) if engine.startswith('bing') else heading.parent.parent
        summary=parent.select_one('.b_caption p,.VwiC3b,.IsZvec,[data-sncf]') if parent else None
        rows.append({'rank':len(rows)+1,'title':heading.get_text(' ',strip=True)[:240],'url':url,'domain':urlsplit(url).hostname,'summary':summary.get_text(' ',strip=True)[:600] if summary else ''})
        if len(rows)==10:break
    return rows

async def first_page(engine,query,timeout=2.0):
    url,params=ENGINES[engine];params={**params,'q':query}
    options=client_options(timeout);options['headers']['Accept']='text/html'
    result={'engine':engine,'query':query,'search_url':str(httpx.URL(url,params=params)),'page':1,'results':[]}
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(**options) as client:
                target=str(httpx.URL(url,params=params))
                for _ in range(4):
                    parsed=urlsplit(target)
                    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.hostname not in {'www.google.com','google.com','www.bing.com','cn.bing.com'}:return {**result,'status':'blocked_redirect'}
                    response=await client.get(target)
                    if response.status_code in {301,302,303,307,308}:target=urljoin(target,response.headers.get('location',''));continue
                    break
        result['http_status']=response.status_code
        result['final_url']=str(response.url)
        ancestor=next((part.strip() for part in response.headers.get('content-security-policy','').split(';') if part.strip().lower().startswith('frame-ancestors ')),'')
        result['embed_headers']={'x-frame-options':response.headers.get('x-frame-options',''),'content-security-policy':ancestor}
        text=response.text[:2_000_000].lower()
        challenge=any(x in text for x in ['verify you are human','unusual traffic from your computer network','g-recaptcha','<title>just a moment']) or '/sorry/' in str(response.url)
        if challenge:return {**result,'status':'verification_required'}
        if response.status_code!=200:return {**result,'status':'http_error'}
        rows=parse_results(response.text[:2_000_000],engine)
        return {**result,'results':rows,'status':'ok' if rows else 'no_extractable_results'}
    except (httpx.TimeoutException,TimeoutError):return {**result,'status':'timeout'}
    except (httpx.HTTPError,ValueError,ImportError):return {**result,'status':'connection_error'}
