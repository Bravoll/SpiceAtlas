"""Parallel public knowledge reader, completion-ordered cards and bounded work."""
from __future__ import annotations
import asyncio,hashlib,html,ipaddress,json,re,socket,time,unicodedata
from datetime import datetime,timezone
from urllib.parse import quote,urljoin,urlsplit,parse_qs
from urllib.request import getproxies,proxy_bypass
import bleach,httpx
from bs4 import BeautifulSoup
from .network import client_options,fetch_json,SourceFailure
from .runtime import runtime,event
from .source_registry import registry,provider_for
from .search_pages import first_page

TAGS={'p','h1','h2','h3','h4','h5','h6','ul','ol','li','dl','dt','dd','table','thead','tbody','tr','th','td','blockquote','strong','em','small','sup','sub','abbr','br','a','code'}
SEARCH_COOLDOWN={}

def scientific_query(entry):return (entry.get('scientific') or entry.get('name_en') or entry.get('english') or entry.get('name','')).split('（')[0].split('(')[0].strip()

def normalize(value):return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',value).casefold()).strip()

def identity_matches(text,entry,title=''):
    haystack=' '+normalize(text)+' ';science=scientific_query(entry)
    parts=science.split()
    name=' '.join(parts[:2]) if len(parts)>=2 else science
    if name and (' '+normalize(name)+' ') in haystack:return True
    if entry.get('scientific'):
        name=entry.get('name_en') or entry.get('english') or ''
        return bool(entry.get('scope')=='culinary' and len(name)>2 and (' '+normalize(name)+' ') in (' '+normalize(title)+' '))
    return any(name and len(name)>2 and (' '+normalize(name)+' ') in haystack for name in [entry.get('name_en'),entry.get('name_zh'),entry.get('name')])

async def public_host(url):
    if not provider_for(url):raise SourceFailure('Source host is not in the reviewed registry',code='unapproved_host')
    host=urlsplit(url).hostname
    try:addresses=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM),timeout=1.5)
    except (OSError,asyncio.TimeoutError):
        # An explicitly configured proxy may own DNS. The exact reviewed host
        # allowlist and HTTPS/port checks still apply at every redirect.
        from .preferences import preferences
        p=preferences.values();proxy=p.get('proxy_url') or (p.get('trust_env') and not proxy_bypass(host) and (getproxies().get('https') or getproxies().get('all')))
        if proxy:return
        raise SourceFailure('Source DNS lookup failed',code='dns') from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):raise SourceFailure('Non-public source address rejected',code='private_address')

async def fetch_html(url,timeout):
    options=client_options(timeout);options['headers']['Accept']='text/html,application/xhtml+xml'
    async with httpx.AsyncClient(**options) as client:
        for _ in range(4):
            if runtime.paused:raise SourceFailure('Service paused',code='paused')
            await public_host(url)
            event('other.request',host=urlsplit(url).hostname,path=urlsplit(url).path)
            async with client.stream('GET',url) as response:
                if response.status_code in {301,302,303,307,308}:
                    url=urljoin(url,response.headers.get('location',''));continue
                if response.status_code!=200:raise SourceFailure('HTTP '+str(response.status_code),code='http_error',status=response.status_code)
                if 'html' not in response.headers.get('content-type','').lower():raise SourceFailure('Not an HTML article',code='not_html')
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    if runtime.paused:raise SourceFailure('Service paused',code='paused')
                    data.extend(chunk)
                    if len(data)>2_000_000:raise SourceFailure('Source exceeds the two-megabyte response limit',code='too_large')
                return bytes(data).decode(response.encoding or 'utf-8',errors='replace'),url
    raise SourceFailure('Too many source redirects',code='redirects')

def extract_article(markup,url,entry):
    soup=BeautifulSoup(markup,'html.parser')
    title=(soup.find('h1') or soup.find('title'))
    title=title.get_text(' ',strip=True)[:250] if title else urlsplit(url).hostname
    for node in soup.select('script,style,noscript,iframe,object,embed,form,nav,footer,header,aside,button,svg,img,video,audio,[hidden],[aria-hidden="true"],.cookie-banner,.advertisement,.social-share'):
        node.decompose()
    roots=soup.select('article,main,[role="main"],#mw-content-text,#content,.entry-content')
    root=max(roots,key=lambda n:len(n.get_text(' ',strip=True)),default=soup.body or soup)
    if root.find('h1'):title=root.find('h1').get_text(' ',strip=True)[:250]
    # Generic site headings are not article identity. PlantNET's taxon name
    # lives in a bold/italic line rather than an h1; keep that specific title.
    specific=next((n for n in root.select('h1,h2,h3,h4,b,strong,i,em,[itemprop="scientificName"]') if len(n.get_text(' ',strip=True))<180 and identity_matches(n.get_text(' ',strip=True),entry,title=n.get_text(' ',strip=True))),None)
    if specific:title=specific.get_text(' ',strip=True)[:250]
    path=urlsplit(url).path.rstrip('/')
    generic=not path or path in {'/floraonline.htm','/florafaunaweb','/spices-and-plant-varieties'}
    if generic:raise SourceFailure('A source home or index page is not a selected article',code='index_page')
    text=root.get_text(' ',strip=True)
    if not identity_matches(title+' '+text[:2500],entry,title=title):raise SourceFailure('The returned article does not match the selected name near its title or introduction',code='identity_mismatch')
    if provider_for(url) and provider_for(url)['id']=='plantnet':
        params=parse_qs(urlsplit(url).query);requested=params.get('name',[''])[0].replace('~',' ')
        if specific is None or params.get('lvl',[''])[0] not in {'sp','gn','fam'} or normalize(requested)!=normalize(scientific_query(entry)) or not re.search(r'description\s*:',text,re.I):
            raise SourceFailure('PlantNET returned no matching taxon description',code='identity_mismatch')
    if len(text)<180:raise SourceFailure('No substantial readable article returned',code='empty_article')
    lower=(title+' '+text[:2000]).lower()
    if any(x in lower for x in ['verify you are human','just a moment','access denied','checking your browser','unusual traffic']):raise SourceFailure('Source requires verification',code='verification')
    if len(text)>160000:raise SourceFailure('Article exceeds the reader text limit; open the original',code='too_large')
    prefix='other-'+hashlib.sha256(url.encode()).hexdigest()[:12];ids={};toc=[]
    for i,node in enumerate(root.select('[id]')):
        old=node['id'];node['id']=prefix+'-node-'+str(i);ids[old]=node['id']
    for i,heading in enumerate(root.select('h1,h2,h3,h4,h5,h6')):
        new=heading.get('id') or prefix+'-'+str(i)
        heading['id']=new;toc.append({'id':new,'title':heading.get_text(' ',strip=True)[:150],'level':int(heading.name[1])})
    for anchor in root.select('a'):
        href=anchor.get('href','')
        if href.startswith('#') and href[1:] in ids:anchor['href']='#'+ids[href[1:]]
        else:anchor['href']=urljoin(url,href)
        anchor['rel']='noopener noreferrer'
        if not anchor['href'].startswith('#'):anchor['target']='_blank'
    cleaned=bleach.clean(str(root),tags=TAGS,attributes={'a':['href','title','target','rel'],'*':['id','lang'],'td':['colspan','rowspan'],'th':['colspan','rowspan']},protocols=['http','https'],strip=True)
    return {'title':title,'html':cleaned,'toc':toc,'source_url':url,'language':soup.html.get('lang','und') if soup.html else 'und','license':'Original source terms apply','identity_note':'Name matched in source text; this is not verification of edible use or accepted taxonomy.'}

def known_candidates(entry):
    rows=[]
    for ref in entry.get('references',{}).values():
        if provider_for(ref.get('url','')):rows.append({'url':ref['url'],'discovery':'catalogue_reference'})
    rows.extend({**row,'discovery':'sampled_source_index'} for row in registry()['entry_candidates'].get(entry['id'],[]))
    science=scientific_query(entry);parts=science.split()
    if len(parts)>=2:
        slug='-'.join(parts[:2]).lower();rows.extend([
            {'url':'https://plants.ces.ncsu.edu/plants/'+quote(slug)+'/', 'discovery':'name_slug_candidate'},
            {'url':'https://plantnet.rbgsyd.nsw.gov.au/cgi-bin/NSWfl.pl?lvl=sp&name='+quote('~'.join(parts[:2]))+'&page=nswfl','discovery':'name_query_candidate'},
            {'url':'https://floranorthamerica.org/'+quote('_'.join(parts[:2])),'discovery':'name_title_candidate'},
        ])
    return rows

async def wiki_card(entry,kind):
    science=scientific_query(entry)
    if kind=='wikispecies':host='https://species.wikimedia.org';page=science.replace(' ','_')
    else:host='https://en.wikibooks.org';page='Cookbook:'+(entry.get('name_en') or entry.get('english') or science)
    data=await fetch_json(host+'/w/api.php',{'action':'parse','page':page,'redirects':1,'prop':'text|sections|revid','format':'json'},timeout=5,gate=asyncio.Semaphore(1))
    parsed=data['parse'];markup=parsed.get('text','');markup=markup.get('*','') if isinstance(markup,dict) else markup
    url=host+'/wiki/'+quote(parsed['title'].replace(' ','_'));card=extract_article('<h1>'+html.escape(parsed['title'])+'</h1>'+markup,url,entry)
    card.update(license='CC BY-SA · see source and revision',revision_url=host+'/w/index.php?oldid='+str(parsed.get('revid','')),license_url='https://creativecommons.org/licenses/by-sa/4.0/')
    return card

async def gbif_card(entry):
    failures=[];data=None
    try:
        raw=await fetch_json('https://api.gbif.org/v2/species/match',{'scientificName':scientific_query(entry)},timeout=10,gate=asyncio.Semaphore(1))
        usage=raw.get('usage',{});diagnostics=raw.get('diagnostics',{})
        if usage.get('key') and diagnostics.get('matchType') in {'EXACT','FUZZY'} and identity_matches(usage.get('canonicalName','') or usage.get('name',''),entry):
            data={'usageKey':usage['key'],'scientificName':usage.get('name'),'canonicalName':usage.get('canonicalName'),'rank':usage.get('rank'),'status':usage.get('status'),'matchType':diagnostics.get('matchType'),'confidence':diagnostics.get('confidence'),'apiVersion':'v2'}
            data.update({row['rank'].lower():row['name'] for row in raw.get('classification',[]) if row.get('rank') and row.get('name')})
    except SourceFailure as exc:failures.append(exc.public())
    if data is None:
        raw=await fetch_json('https://api.gbif.org/v1/species/match',{'name':scientific_query(entry)},timeout=10,gate=asyncio.Semaphore(1))
        if raw.get('usageKey') and raw.get('matchType') in {'EXACT','FUZZY'} and identity_matches(raw.get('canonicalName','') or raw.get('scientificName',''),entry):data={**raw,'apiVersion':'v1 compatible'}
    if not data:raise SourceFailure('No matching GBIF taxonomic record returned',code='identity_mismatch')
    fields=['scientificName','canonicalName','kingdom','phylum','class','order','family','genus','rank','status','matchType','confidence','apiVersion']
    body='<p>GBIF taxonomic name reference. Name matching is not evidence of culinary use.</p><table><tbody>'+''.join('<tr><th>'+html.escape(key)+'</th><td>'+html.escape(str(data[key]))+'</td></tr>' for key in fields if data.get(key) is not None)+'</tbody></table>'
    return {'title':data['scientificName'],'html':body,'toc':[],'source_url':'https://www.gbif.org/'+('species/' if str(data['usageKey']).isdigit() else 'taxon/')+quote(str(data['usageKey'])),'language':'en','license':'GBIF source dataset terms apply','identity_note':'Taxonomic name match, not an edibility determination.','api_version':data['apiVersion']}

async def stream_cards(entry,prefs,report):
    start=time.monotonic();deadline=start+prefs['other_total_timeout'];queue=asyncio.Queue();tasks=set();pending=0;seen=set();domains={};cards=0;attempted=0;failed=0
    gate=asyncio.Semaphore(5);search_gate=asyncio.Semaphore(3);rendered_hosts=set()
    def spawn(kind,provider,operation,url=''):
        nonlocal pending,attempted
        pending+=1;attempted+=kind=='article'
        async def run():
            try:
                async with asyncio.timeout(max(.001,deadline-time.monotonic())):
                    async with (gate if kind=='article' else search_gate):
                        async with asyncio.timeout(prefs['other_source_timeout'] if kind=='article' else min(10,prefs['other_source_timeout'])):
                            if runtime.paused:raise SourceFailure('Service paused',code='paused')
                            value=await operation()
                await queue.put({'type':'card' if kind=='article' else 'discovery','provider':provider,'value':value,'url':url})
            except asyncio.CancelledError:raise
            except Exception as error:
                await queue.put({'type':'error','provider':provider,'url':url,'code':getattr(error,'code','timeout' if isinstance(error,TimeoutError) else 'unavailable'),'message':str(error)[:240]})
        task=asyncio.create_task(run());tasks.add(task);task.add_done_callback(tasks.discard)
    def enqueue(url,discovery):
        profile=provider_for(url)
        if not profile or url in seen or len(seen)>=18:return
        host=urlsplit(url).hostname
        if domains.get(host,0)>=2:return
        if report.get('services',{}).get('other_'+profile['id'],{}).get('ok') is False:return
        seen.add(url);domains[host]=domains.get(host,0)+1
        async def read():
            markup,final=await fetch_html(url,prefs['other_source_timeout'])
            card=await asyncio.to_thread(extract_article,markup,final,entry);card['discovery']=discovery;return card
        spawn('article',profile['id'],read,url)
    try:
        yield {'type':'start','entry_id':entry['id'],'total_timeout':prefs['other_total_timeout'],'source_timeout':prefs['other_source_timeout']}
        for profile,operation in [('gbif',lambda:gbif_card(entry)),('wikispecies',lambda:wiki_card(entry,'wikispecies')),('wikibooks',lambda:wiki_card(entry,'wikibooks'))]:
            if report.get('services',{}).get('other_'+profile,{}).get('ok') is not False:spawn('article',profile,operation)
        for row in known_candidates(entry):enqueue(row['url'],row.get('discovery',row.get('provenance','indexed_candidate')))
        if prefs.get('other_search_enabled',True):
            for engine in ('google','bing','bing_cn'):
                if SEARCH_COOLDOWN.get(engine,0)>time.monotonic():continue
                query=scientific_query(entry)+' plant herb' if engine!='bing_cn' else (entry.get('name_zh') or scientific_query(entry))+' 植物 香料'
                spawn('search',engine,lambda engine=engine,query=query:first_page(engine,query,timeout=8))
        while pending and cards<prefs['other_max_cards'] and time.monotonic()<deadline:
            if runtime.paused:break
            try:item=await asyncio.wait_for(queue.get(),timeout=min(.6,max(.001,deadline-time.monotonic())))
            except asyncio.TimeoutError:
                yield {'type':'progress','pending':pending,'completed':cards,'elapsed_ms':round((time.monotonic()-start)*1000)};continue
            pending-=1
            if item['type']=='discovery':
                result=item['value']
                if result['status']=='verification_required':SEARCH_COOLDOWN[item['provider']]=time.monotonic()+600
                elif result['status']!='ok':SEARCH_COOLDOWN[item['provider']]=time.monotonic()+60
                for row in result.get('results',[]):enqueue(row['url'],'live_'+item['provider']+'_page_1')
                yield {'type':'search','provider':item['provider'],'status':result['status'],'results':len(result.get('results',[])),'url':result.get('search_url','')}
            elif item['type']=='card':
                host=urlsplit(item['value']['source_url']).hostname
                if host in rendered_hosts:continue
                rendered_hosts.add(host)
                cards+=1;profile=next((p for p in registry()['providers'] if p['id']==item['provider']),{})
                card={**item['value'],'provider':item['provider'],'provider_name':profile.get('name_en',item['provider']),'provider_name_zh':profile.get('name_zh',item['provider']),'completed_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),'order':cards,'elapsed_ms':round((time.monotonic()-start)*1000)}
                event('other.article.ready',entry=entry['id'],provider=item['provider'],order=cards)
                yield {'type':'card','card':card}
            else:
                failed+=1;yield item
        reason='paused' if runtime.paused else 'card_limit' if cards>=prefs['other_max_cards'] else 'timeout' if pending else 'complete'
        yield {'type':'done','cards':cards,'attempted':attempted,'failed':failed,'pending_cancelled':pending,'reason':reason,'elapsed_ms':round((time.monotonic()-start)*1000)}
    finally:
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
