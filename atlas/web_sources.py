"""Public search results and real frame capability; no active-page proxying."""
from __future__ import annotations
import asyncio,hashlib,html,json,re
from urllib.parse import urljoin,urlsplit,parse_qs,unquote
from bs4 import BeautifulSoup
import httpx
from .network import client_options,SourceFailure
from .storage import Store,now_iso
from .other_sources import fetch_html,extract_article,gbif_card
from .source_registry import provider_for
from .search_pages import first_page

SEARCH_HOSTS={'www.google.com','google.com','www.bing.com','cn.bing.com','image.baidu.com'}

def safe_image_url(value):
    if not isinstance(value,str):return ''
    try:
        p=urlsplit(value)
        return value if p.scheme=='https' and p.hostname and '.' in p.hostname and not p.username and not p.password and not re.fullmatch(r'[\d.]+',p.hostname) and not p.hostname.endswith(('.local','.localhost')) else ''
    except ValueError:return ''

def frame_headers(headers):
    xfo=headers.get('x-frame-options','').strip().upper()
    directive=next((x.strip() for x in headers.get('content-security-policy','').split(';') if x.strip().lower().startswith('frame-ancestors ')),None)
    if directive:
        sources=directive.split()[1:]
        allowed='*' in sources or 'http:' in sources or any(x in sources for x in ['http://127.0.0.1:8765','http://localhost:8765'])
        return allowed,{'x_frame_options':xfo,'frame_ancestors':directive}
    return xfo not in {'DENY','SAMEORIGIN'},{'x_frame_options':xfo,'frame_ancestors':None}

async def public_search_page(url,timeout=12):
    original=url;options=client_options(timeout);options['headers']['Accept']='text/html'
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(**options) as client:
            for _ in range(4):
                target=urlsplit(url);host=target.hostname
                if target.scheme!='https' or target.username or target.password or target.port not in (None,443) or host not in SEARCH_HOSTS:raise SourceFailure('Search redirected outside the public result page',code='verification_required' if host=='wappass.baidu.com' else 'blocked_redirect')
                async with client.stream('GET',url) as response:
                    if response.status_code in {301,302,303,307,308}:
                        url=urljoin(url,response.headers.get('location',''));continue
                    if response.status_code!=200:raise SourceFailure('Search returned HTTP '+str(response.status_code),code='http_error',status=response.status_code)
                    data=bytearray()
                    async for part in response.aiter_bytes():
                        data.extend(part)
                        if len(data)>2_000_000:raise SourceFailure('Search page exceeds response limit',code='too_large')
                    markup=bytes(data).decode(response.encoding or 'utf-8',errors='replace')
                    title=BeautifulSoup(markup[:200000],'html.parser').title
                    title=title.get_text(' ',strip=True) if title else ''
                    if re.search(r'captcha|verify you are human|unusual traffic|安全验证|验证页面|just a moment',title+' '+markup[:6000],re.I):raise SourceFailure('The provider requires verification in its own site',code='verification_required')
                    can_try,evidence=frame_headers(response.headers)
                    return {'url':url,'requested_url':original,'can_try':can_try,'code':'allowed' if can_try else 'frame_denied','http_status':200,**evidence,'markup':markup}
    raise SourceFailure('Search redirect limit reached',code='redirects')

async def frame_check(url):
    try:
        result=await public_search_page(url)
        return {k:v for k,v in result.items() if k!='markup'}
    except (SourceFailure,httpx.HTTPError,TimeoutError) as exc:
        return {'url':url,'can_try':False,'code':getattr(exc,'code','network_error'),'http_status':getattr(exc,'status',None),'reason':str(exc)[:220]}

def image_results(markup,provider):
    soup=BeautifulSoup(markup,'html.parser');rows=[];seen=set()
    def add(image,source,title='',thumb=''):
        image=safe_image_url(image);source=safe_image_url(source);thumb=safe_image_url(thumb) or image
        if not image or not source or image in seen or len(rows)>=20:return
        title=BeautifulSoup(html.unescape(str(title)),'html.parser').get_text(' ',strip=True)
        seen.add(image);rows.append({'id':'web-'+hashlib.sha256(image.encode()).hexdigest()[:18],'title':title[:180] or provider+' image result','description':'','original_url':image,'thumbnail_url':thumb,'display_url':thumb,'source_url':source,'author':'See original file page','license':'Check original source terms','license_url':''})
    for node in soup.select('[m]'):
        try:
            row=json.loads(node.get('m',''));add(row.get('murl',''),row.get('purl',''),row.get('t',''),row.get('turl',''))
        except (ValueError,TypeError):pass
    for anchor in soup.select('a[href]'):
        href=urljoin('https://www.google.com',anchor['href']);q=parse_qs(urlsplit(href).query)
        if q.get('imgurl'):
            image=anchor.find('img');add(q['imgurl'][0],q.get('imgrefurl',[''])[0],image.get('alt','') if image else '',image.get('src','') if image else '')
    for node in soup.select('[data-ou],[data-iurl],.rg_meta'):
        if node.has_attr('data-ou') or node.has_attr('data-iurl'):
            image=node.find('img');add(node.get('data-ou') or node.get('data-iurl',''),node.get('data-ru') or node.get('data-ref-url',''),node.get('data-title','') or (image.get('alt','') if image else ''),image.get('src','') if image else '')
        else:
            try:
                row=json.loads(node.get_text());add(row.get('ou',''),row.get('ru',''),row.get('pt',''),row.get('tu',''))
            except (ValueError,TypeError):pass
    # Baidu publicly rendered result metadata; verification pages are rejected first.
    for match in re.finditer(r'\{[^{}]{0,5000}"(?:objURL|middleURL)"\s*:[^{}]{0,5000}\}',markup):
        try:
            row=json.loads(match[0]);image=next((safe_image_url(row.get(k,'')) for k in ['objURL','middleURL','thumbURL'] if safe_image_url(row.get(k,''))),'');add(image,row.get('fromURL') or row.get('fromPageUrl',''),row.get('fromPageTitleEnc',''),row.get('thumbURL',''))
        except (ValueError,TypeError):pass
    # Public JSON-LD is data, not executable JavaScript. Never eval page scripts.
    budget=[800]
    def visit(value,depth=0):
        if depth>8 or budget[0]<=0:return
        budget[0]-=1
        if isinstance(value,dict):
            if value.get('@type')=='ImageObject':
                main=value.get('mainEntityOfPage') or value.get('url','');main=main.get('@id','') if isinstance(main,dict) else main
                thumb=value.get('thumbnailUrl','');thumb=thumb[0] if isinstance(thumb,list) and thumb else thumb
                add(value.get('contentUrl',''),main,value.get('name') or value.get('caption',''),thumb)
            for item in value.values():visit(item,depth+1)
        elif isinstance(value,list):
            for item in value[:100]:visit(item,depth+1)
    for script in soup.select('script[type="application/ld+json"]')[:15]:
        try:visit(json.loads(script.get_text()))
        except (ValueError,TypeError):pass
    return rows

async def search_images(url,provider,store=None,refresh=False):
    store=store or Store();key='web-images:v1:'+hashlib.sha256(url.encode()).hexdigest();cached=store.get(key)
    if cached and not cached['stale'] and not refresh:return {**cached['value'],'delivery':'cache'}
    try:
        page=await public_search_page(url);images=await asyncio.to_thread(image_results,page['markup'],provider)
        value={'mode':'images' if images else 'external','provider':provider,'images':images,'source_url':url,'fetched_at':now_iso(),'delivery':'live','frame_check':{k:v for k,v in page.items() if k!='markup'}}
        if images:store.put(key,value,900)
        return value
    except (SourceFailure,httpx.HTTPError,TimeoutError) as exc:
        return {'mode':'external','provider':provider,'images':[],'source_url':url,'diagnostic':{'code':getattr(exc,'code','network_error'),'message':str(exc)[:180]},'frame_check':{'url':url,'can_try':False,'code':getattr(exc,'code','network_error')}}

def article_from_card(card,source,entry):
    return {**card,'mode':'article','entry_id':entry['id'],'source':source,'focus_html':card['html'],'focus_toc':card.get('toc',[]),'fetched_at':now_iso(),'delivery':'live','translation_supported':False}

async def read_reference(entry,source,url,store=None,refresh=False):
    store=store or Store();key='reference-article:v2:'+hashlib.sha256((entry['id']+url).encode()).hexdigest();old=store.get(key)
    if old and not old['stale'] and not refresh:return {**old['value'],'delivery':'cache'}
    async with asyncio.timeout(25):
        if source=='gbif':card=await gbif_card(entry)
        elif source=='wikidata':
            from .network import fetch_json
            qid=entry.get('wikidata_id','')
            if not re.fullmatch(r'Q\d+',qid):raise SourceFailure('No recorded Wikidata identity',code='not_found')
            raw=await fetch_json('https://www.wikidata.org/w/api.php',{'action':'wbgetentities','ids':qid,'props':'labels|aliases|descriptions','languages':'en|zh|zh-hans|zh-hant','format':'json'},timeout=15,gate=asyncio.Semaphore(1))
            entity=raw.get('entities',{}).get(qid,{})
            if entity.get('missing') is not None or not entity.get('id'):raise SourceFailure('Wikidata entity is missing',code='not_found')
            rows=[]
            for kind in ['labels','descriptions','aliases']:
                for lang,value in entity.get(kind,{}).items():
                    text=', '.join(x.get('value','') for x in value) if isinstance(value,list) else value.get('value','')
                    rows.append('<tr><th>'+html.escape(kind+' · '+lang)+'</th><td>'+html.escape(text)+'</td></tr>')
            card={'title':'Wikidata · '+qid,'html':'<table><tbody>'+''.join(rows)+'</tbody></table>','toc':[],'source_url':'https://www.wikidata.org/wiki/'+qid,'language':'multi','license':'CC0 · Wikidata structured data','license_url':'https://creativecommons.org/publicdomain/zero/1.0/'}
        else:
            if not provider_for(url):raise SourceFailure('This provider currently has an original-site link only',code='link_only')
            markup,final=await fetch_html(url,24);card=await asyncio.to_thread(extract_article,markup,final,entry)
        result=article_from_card(card,source,entry);store.put(key,result,900);return result

async def search_articles(entry,engine,query,language='en'):
    from .preferences import preferences
    p=preferences.values();result=None
    if engine=='google' and p.get('google_api_key') and p.get('google_cse_id'):
        from .network import fetch_json
        try:
            raw=await fetch_json('https://www.googleapis.com/customsearch/v1',{'key':p['google_api_key'],'cx':p['google_cse_id'],'q':query,'lr':'lang_'+language},timeout=15,gate=asyncio.Semaphore(1))
            rows=[{'rank':i+1,'title':row.get('title',''),'url':row['link'],'summary':row.get('snippet',''),'domain':urlsplit(row['link']).hostname} for i,row in enumerate(raw.get('items',[])) if safe_image_url(row.get('link',''))]
            from urllib.parse import urlencode
            result={'status':'ok' if rows else 'no_extractable_results','search_url':'https://www.google.com/search?'+urlencode({'q':query,'hl':language}),'results':rows}
        except SourceFailure as exc:
            result={'status':'http_error','search_url':'https://www.google.com/search','results':[],'diagnostic':exc.public()}
    if result is None:result=await first_page(engine,query,timeout=10)
    can_embed=result.get('http_status')==200 and result.get('status') in {'ok','no_extractable_results'} and frame_headers(result.get('embed_headers',{}))[0]
    return {'mode':'search_results','source':engine,'title':{'google':'Google','bing':'Bing International','bing_cn':'Bing China'}[engine],'source_url':result['search_url'],'language':language,'results':[{**row,'readable':bool(provider_for(row['url']))} for row in result['results']],'status':result['status'],'embed_can_try':can_embed,'embed_url':result.get('final_url',result['search_url']),'fetched_at':now_iso(),'delivery':'live'}
