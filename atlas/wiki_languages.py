"""English-anchored interlanguage discovery; runtime mappings never rename catalogue records."""
from __future__ import annotations
import asyncio,hashlib,json,re
from urllib.parse import quote
from .network import fetch_json,SourceFailure
from .storage import Store,now_iso

WIKI_GATE=asyncio.Semaphore(2)

def cache_key(entry):
    identity={k:entry.get(k) for k in ('id','wiki','scientific','name_en','name_zh','wikidata_id')}
    return 'wiki-languages:v1:'+hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def known_languages(entry):
    return {site[:-4]:title for site,title in entry.get('wiki',{}).items() if site in {'enwiki','zhwiki'} and title}

def choices(mapping):
    return [dict(code=lang,title=title,url='https://'+lang+'.wikipedia.org/wiki/'+quote(title.replace(' ','_'))) for lang,title in mapping.items() if re.fullmatch(r'[a-z][a-z-]{0,18}',lang)]

def cached_mapping(entry,store=None):
    row=(store or Store()).get(cache_key(entry))
    return row['value'] if row and not row['stale'] else None

def mapped_entry(entry,info):
    return {**entry,'wiki':{**entry.get('wiki',{}),**{lang+'wiki':title for lang,title in info.get('mapping',{}).items() if lang in {'en','zh'}}}}

def same_identity(page,entry):
    expected=entry.get('wikidata_id');actual=page.get('pageprops',{}).get('wikibase_item')
    if expected and actual:return actual==expected
    science=re.sub(r'\s*[(（].*','',entry.get('scientific','')).strip()
    if science and len(science.split())>=2:
        return bool(re.search(r'(?<!\w)'+re.escape(science)+r'(?!\w)',page.get('extract','')+' '+page.get('title',''),re.I))
    return page.get('title') in {entry.get('name_zh'),entry.get('name_en')}

async def query(lang,params):
    return await fetch_json('https://'+lang+'.wikipedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,**params},timeout=10,gate=WIKI_GATE)

async def search_chinese(entry):
    names=list(dict.fromkeys(x for x in [entry.get('name_zh'),entry.get('scientific')] if x))[:2]
    responses=await asyncio.gather(*(query('zh',{'list':'search','srsearch':name,'srnamespace':0,'srlimit':3}) for name in names),return_exceptions=True)
    errors=[];successful=[]
    for data in responses:
        if isinstance(data,(SourceFailure,TimeoutError)):errors.append(failure_info(data,'chinese_search'))
        elif isinstance(data,BaseException):raise data
        else:successful.append(data)
    ids=list(dict.fromkeys(str(row['pageid']) for data in successful for row in data.get('query',{}).get('search',[]) if row.get('pageid')))[:6]
    if not ids:return None,errors
    data=await query('zh',{'pageids':'|'.join(ids),'prop':'pageprops|extracts','exintro':1,'explaintext':1,'redirects':1})
    for page in data.get('query',{}).get('pages',[]):
        if not page.get('missing') and same_identity(page,entry):return page['title'],errors
    return None,errors

def failure_info(exc,stage):
    return {'code':getattr(exc,'code','timeout'),'message':str(exc)[:180],'stage':stage}

async def resolve_languages(entry,store=None,refresh=False):
    store=store or Store();previous=store.get(cache_key(entry));old=previous['value'] if previous else None
    if old and not previous['stale'] and not refresh:return old
    mapping=known_languages(entry);methods={lang:'catalogue' for lang in mapping};errors=[]
    identity_entry=entry
    try:
        async with asyncio.timeout(30):
            title=mapping.get('en') or entry.get('scientific') or entry.get('name_en') or entry.get('english')
            if title:
                try:
                    data=await query('en',{'titles':title,'redirects':1,'prop':'langlinks|pageprops','lllimit':500,'llprop':'url|autonym'})
                    page=next((p for p in data.get('query',{}).get('pages',[]) if not p.get('missing') and p.get('pageid')),None)
                    if page:
                        mapping['en']=page['title'];methods['en']='english_anchor'
                        identity_entry={**entry,'wikidata_id':entry.get('wikidata_id') or page.get('pageprops',{}).get('wikibase_item')}
                        for row in page.get('langlinks',[]):
                            lang=row.get('lang','');value=row.get('title',row.get('*',''))
                            if re.fullmatch(r'[a-z][a-z-]{0,18}',lang) and value:mapping[lang]=value;methods[lang]='english_langlink'
                except (SourceFailure,TimeoutError) as exc:errors.append(failure_info(exc,'english_anchor'))
            if not mapping.get('zh'):
                try:
                    title,partial_errors=await search_chinese(identity_entry);errors.extend(partial_errors)
                    if title:mapping['zh']=title;methods['zh']='independent_search_identity_checked'
                except (SourceFailure,TimeoutError) as exc:errors.append(failure_info(exc,'chinese_search'))
    except (SourceFailure,TimeoutError) as exc:
        errors.append(failure_info(exc,'discovery_budget'))
    retained=[]
    if errors and old:
        for lang,title in old.get('mapping',{}).items():
            if lang not in mapping and title:
                mapping[lang]=title;methods[lang]=old.get('methods',{}).get(lang,'cached_verified');retained.append(lang)
    value={'entry_id':entry['id'],'mapping':mapping,'languages':choices(mapping),'methods':methods,'checked_at':now_iso(),'state':'unconfirmed' if errors else 'resolved','diagnostics':errors,'cached_fallback_languages':retained}
    store.put(cache_key(entry),value,60 if errors else 86400)
    return value
