"""Bounded research asset: checkpoint official evidence and propose a cleaned DB.

Does not change the application's original catalogue.sqlite3.
"""
import argparse
import collections
import asyncio
from datetime import datetime, timezone
import html
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

import httpx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=ROOT/'data/catalogue.sqlite3'
UA='SpiceAtlas/0.4 (local botanical catalogue curation research)'
WIKIDATA='https://www.wikidata.org/w/api.php'

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def norm(value):return unicodedata.normalize('NFKC',str(value or '')).replace('_',' ').strip().casefold()
def save(path,value):
    target=HERE/path
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),'utf-8')
    temporary.replace(target)
def read(path):return json.loads((HERE/path).read_text('utf-8'))
def rows(path=SOURCE):
    con=sqlite3.connect(path);con.row_factory=sqlite3.Row
    output=[dict(r) for r in con.execute('SELECT * FROM entries')]
    con.close()
    return output
async def request(client,url,params):
    for attempt in range(6):
        try:
            response=await client.get(url,params={**params,'maxlag':10,'format':'json'},timeout=90)
            response.raise_for_status()
            value=response.json()
            if value.get('error'):
                code=value['error'].get('code')
                if code in {'maxlag','ratelimited','readonly'}:
                    await asyncio.sleep(min(5*(attempt+1),25));continue
                raise RuntimeError(value['error'])
            await asyncio.sleep(.35)
            return {'fetched_at':now(),'source_url':url,'parameters':params,'http_status':response.status_code,'response':value}
        except (httpx.HTTPError,ValueError) as exc:
            if attempt==5:raise
            save('last_network_error.json',{'at':now(),'host':httpx.URL(url).host,'kind':type(exc).__name__,'attempt':attempt+1})
            await asyncio.sleep(min(5*(attempt+1),25))
    raise RuntimeError('Source remained busy after bounded retries')
def claim_values(entity,prop):
    return [c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in entity.get('claims',{}).get(prop,[]) if c.get('mainsnak',{}).get('datavalue')]

async def fetch():
    candidates=[r for r in rows() if r['scope']=='culinary']
    pages={};resolved={}
    async with httpx.AsyncClient(headers={'User-Agent':UA,'Accept':'application/json'},follow_redirects=True) as client:
        for site in ['enwiki','zhwiki']:
            unresolved=[r for r in candidates if not r.get('wikidata_id') and r.get('wiki_en' if site=='enwiki' else 'wiki_zh')]
            for start in range(0,len(unresolved),40):
                batch=unresolved[start:start+40]
                file=f'raw/wiki_resolve_{site}_{start:04}.json'
                if (HERE/file).exists():evidence=read(file)
                else:
                    titlekey='wiki_en' if site=='enwiki' else 'wiki_zh'
                    params={'action':'query','titles':'|'.join(r[titlekey] for r in batch),'redirects':1,'prop':'pageprops','formatversion':2}
                    evidence=await request(client,'https://'+('en' if site=='enwiki' else 'zh')+'.wikipedia.org/w/api.php',params)
                    save(file,evidence)
                query=evidence['response'].get('query',{})
                redirects={norm(x['from']):x['to'] for x in [*query.get('normalized',[]),*query.get('redirects',[])]}
                by_title={norm(p['title']):p for p in query.get('pages',[])}
                for r in batch:
                    title=r['wiki_en' if site=='enwiki' else 'wiki_zh'];seen=set()
                    while norm(title) in redirects and norm(title) not in seen:
                        seen.add(norm(title));title=redirects[norm(title)]
                    page=by_title.get(norm(title),{})
                    qid=page.get('pageprops',{}).get('wikibase_item')
                    if qid:
                        resolved[r['id']]={'qid':qid,'site':site,'title':page['title'],'pageid':page.get('pageid'),'evidence_file':file,'fetched_at':evidence['fetched_at']}
                save('redirect_resolution.json',resolved)
        ids=sorted({r.get('wikidata_id') or resolved.get(r['id'],{}).get('qid') for r in candidates}-{None,''})
        for start in range(0,len(ids),40):
            batch=ids[start:start+40];file=f'raw/entities_{start:04}.json'
            if not (HERE/file).exists():
                evidence=await request(client,WIKIDATA,{'action':'wbgetentities','ids':'|'.join(batch),'props':'info|labels|descriptions|aliases|claims|sitelinks','languages':'en|zh|zh-hans|zh-hant|zh-tw','sitefilter':'enwiki|zhwiki'})
                save(file,evidence)
            save('fetch_progress.json',{'at':now(),'stage':'entities','completed':min(start+40,len(ids)),'total':len(ids)})
            print('Entities',min(start+40,len(ids)),'/',len(ids),flush=True)
        entities={}
        for f in sorted((HERE/'raw').glob('entities_*.json')):
            entities.update(json.loads(f.read_text('utf-8'))['response'].get('entities',{}))
        p31=sorted({v['id'] for e in entities.values() for v in claim_values(e,'P31') if isinstance(v,dict) and v.get('id')})
        for start in range(0,len(p31),40):
            batch=p31[start:start+40];file=f'raw/types_{start:04}.json'
            if not (HERE/file).exists():
                evidence=await request(client,WIKIDATA,{'action':'wbgetentities','ids':'|'.join(batch),'props':'info|labels|descriptions|claims','languages':'en|zh|zh-hant'})
                save(file,evidence)
            print('Types',min(start+40,len(p31)),'/',len(p31),flush=True)
    save('fetch_progress.json',{'at':now(),'stage':'completed','entities':len(entities),'p31_types':len(p31),'resolved_redirects':len(resolved),'candidates':len(candidates)})

def evidence_maps():
    entities={};types={};provenance={}
    for kind,destination in [('entities',entities),('types',types)]:
        for file in sorted((HERE/'raw').glob(kind+'_*.json')):
            evidence=json.loads(file.read_text('utf-8'))
            for key,item in evidence['response'].get('entities',{}).items():
                destination[key]=item
                if kind=='entities':provenance[key]={'fetched_at':evidence['fetched_at'],'evidence_file':str(file.relative_to(HERE))}
    return entities,types,provenance


# Reviewed finite type decisions. A taxon or cultivar is a reference, not a safety
# statement. No medicinal, perfumery or incense use is promoted to culinary use.
TYPE_REJECT={
 'Q113145171','Q47154513','Q59199015','Q79529','Q206229','Q67015883','Q17339814','Q55640599',
 'Q167270','Q431289','Q16323605','Q80359036','Q105815873','Q114392939',
 'Q4830453','Q43229','Q6881511','Q2900145','Q891723','Q1589009','Q783794','Q2659904','Q1664720','Q3918','Q1700154','Q268592','Q11707','Q50969307','Q1251750',
 'Q5','Q13406463','Q4167410','Q15623926','Q21484471','Q191067','Q6165948','Q7725634','Q15416','Q11424','Q1030329',
 'Q15275719','Q1435951','Q16675435','Q2627975','Q3241045','Q16511806','Q187588','Q838247',
 'Q167346','Q7189541','Q85883532','Q3522256','Q1107656','Q96338860','Q1165944','Q2087181','Q1595639','Q115154402','Q1343246','Q16884952','Q24699794','Q756102','Q15243209','Q879050','Q207694','Q7075','Q44234152','Q1438040',
 'Q618123','Q3957','Q56061','Q1370617','Q17524420','Q25514398','Q12866777','Q1778821','Q38695','Q5962346','Q2434238',
 'Q96952903','Q851782','Q3773693','Q63341786','Q3305213','Q33294038',
 'Q154','Q40050','Q379932','Q905870','Q56139','Q549301','Q134768','Q2536409','Q5017160','Q185583','Q11312555','Q1410920','Q1060331','Q13266','Q13377687','Q17315191','Q131419','Q27994917','Q746549','Q818674','Q41415','Q19861951',
}
TYPE_BOTANICAL={'Q16521','Q4886','Q4150646','Q1363241','Q110535774','Q39173095','Q136343650','Q7432','Q1362373','Q756','Q189393','Q201959','Q235352','Q2247340','Q55983715','Q188840'}
TYPE_CULINARY={'Q42527','Q1521067','Q4173974','Q2596997','Q3127593'}
REJECT_DESCRIPTION=re.compile(r'\b(?:brand|company|retailer|manufacturer|organisation|organization|institute|museum|garden|festival|annual event|fundraising|cultivation technique|competition|cookies?|cakes?|biscuits?|bread|pastr(?:y|ies)|pudding|dessert|desert|soup|sausage|confectionery|candy|sweetener lozenge|ice cream|ice lolly|beverage|liqueur|liquor|cocktail|vodka|anise drink|digestif|drink|beer|straw|utensil|cooking style|style of cooking|cooking method|plant disease|dermatitis|diagnostic test|chemical compound|court case|painting|folk hero|film|servant position|emulsion|royal office|trade route)\b|herbal tea|infusion created|flavo[u]?red pastille|flavored water made|juice|meatball|\bdish\b',re.I)
CULINARY_DESCRIPTION=re.compile(r'\b(?:spice(?: mix| mixture| powder| blend)?|seasoning|condiment|culinary herb|herb mixture used for|powder commonly used as|flavo[u]?ring|used in cooking)\b|ground.*(?:onion|garlic)|dehydrated.*onion|edible oilseed|dried unripe mango powder|dried form of.*chili|smoke-dried jalape',re.I)
BOTANICAL_DESCRIPTION=re.compile(r'\b(?:cultivar|variety of (?:chili|pepper|plant|flowering|sweet basil)|type of basil|strain of pepper|group of aromatic plants|variety of dark opal basil)\b',re.I)
MANUAL_CULINARY={
 'Q19571438':'Dhana jiru is a spice mixture; name reviewed in the Wikidata/Wikipedia intake.',
 'Q2007388':'Poppy seed is an edible seed ingredient; separated from the poppy taxon.',
 'Q2015681':'Amchoor is dried mango powder used as a seasoning.',
 'Q1541119':'Yuzukosho is a condiment made from citrus peel and chili.',
 'Q900450':'Rose water is a culinary flavoring with other nonculinary uses; use food-grade products.',
 'Q16530385':'Asafoetida is a culinary gum-resin spice with other medicinal uses.',
 'Q7093931':'Onion powder is a culinary seasoning.',
 'Q7080074':'Ogiri is a fermented seed seasoning.',
 'Q2827931':'Black garlic is a processed garlic ingredient.',
 'Q838835':'Pasilla is a dried chili form.',
 'Q860808':'Chipotle is a smoke-dried chili form.',
 'Q654253':'Masala is a general term for a mixture of spices.',
 'Q1432348':'Gruit is an herb mixture used to flavor beer; the mixture is distinct from the finished beverage.',
 'Q14624':'Garam masala is a mixture of spices.',
 'Q148306':'Za’atar is an herbal seasoning mixture/common name; composition varies by context.',
 'Q1072946':'Chili powder is a processed spice; blends may contain additional ingredients.',
 'Q131747661':'Amchur variety described as a spice powder.',
 'Q141758765':'Jeeravan masala is a spice mixture.',
 'Q141457618':'Nutmeg record describes the spice, distinct from plant taxon.',
}
MANUAL_PENDING={'Q358375':'Aromatic wood/resin with conflicting food-flavoring type; culinary classification requires dedicated evidence.'}
MANUAL_BOTANICAL={q:'Plant cultivar or botanical common-name reference supported by the linked Wikipedia introduction; culinary use not independently reviewed.' for q in ['Q4732091','Q24945326','Q3880492','Q1061638','Q2919092','Q15114159','Q7548286','Q7655264','Q5619501','Q5168043','Q132861424','Q6076019','Q4699993','Q141385075','Q4699992','Q5364597','Q104690561','Q141385252','Q6030056','Q7499091','Q55624537','Q48189338','Q7669301']}
MANUAL_CULINARY.update({q:reason for q,reason in {
 'Q734727':'Galangal rhizomes are explicitly described as culinary materials in the source introduction.',
 'Q460570':'Dried lime is explicitly described as a whole, sliced or ground spice.',
 'Q1587547':'Grains of Selim are explicitly described as a spice and coffee flavoring.',
 'Q2497744':'Pink peppercorn refers to dried berries used as a pepper-like seasoning; identity varies by product.',
 'Q913548':'Herbes de Provence is an herb blend, distinct from its component taxa.',
 'Q3301501':'File powder is explicitly described as an herb seasoning.',
 'Q16988115':'Jimbu is explicitly described as a dried culinary herb mixture from Allium species.',
 'Q5057832':'Celery salt is a seasoning mixture of salt and ground celery seeds.',
 'Q1572414':'Kala namak is a salt-based condiment; included as a nonbotanical seasoning.',
 'Q1790817':'Himalayan salt is a salt-based seasoning; included as nonbotanical material.',
 'Q6934259':'Mulling spice is the spice mixture, distinct from the finished spiced drink.',
 'Q318367':'Mastic resin has culinary flavoring uses; identity and food-grade status must be checked.',
 'Q24236084':'Ginger garlic masala is a crushed seasoning mixture of ginger and garlic.',
 'Q3393894':'Penja pepper is a named geographical pepper product, not a separate species.',
 'Q6933754':'Mulato pepper is a dried chili form.',
 'Q59342945':'Peperone crusco is a dried sweet pepper culinary form.',
 'Q4023625':'Zafferano dell’Aquila is a geographically designated saffron product.',
 'Q2771241':'Garlic chutney is a prepared condiment; recipe composition varies.',
 'Q1070271':'Chermoula is a culinary herb marinade and relish; recipe composition varies.',
 'Q2900348':'Garlic butter is a compound culinary flavoring; recipe composition varies.',
}.items()})
MANUAL_REJECT={
 'Q23808433':'Masala dabba is a spice storage container, not a spice material.',
 'Q141457618':'Nutmeg as a drug is a use-specific article, not a distinct spice material.',
 'Q18231093':'JDB Group is a beverage company, not a botanical or spice material.',
 'Q701395':'Wong Lo Kat is a prepared herbal tea/product, not an individual spice material.',
 'Q1501968':'Salt and pepper shaker is a container, not a spice material.',
 'Q14906':'Garlic press is a kitchen tool, not garlic.',
 'Q7336445':'Ristra is a hanging arrangement/storage method, not a botanical material.',
 'Q7229585':'Poppy seed test is a medical diagnostic procedure, not poppy seed.',
}
def labels(entity):
    values=entity.get('labels',{})
    def get(*keys):return next((values[k]['value'] for k in keys if k in values),'')
    return get('zh-hans','zh','zh-hant','zh-tw'),get('en')
def entity_types(entity):return [v['id'] for v in claim_values(entity,'P31') if isinstance(v,dict) and v.get('id')]
def classify(item,entity):
    if item.get('review_state')=='curated':return 'keep','culinary','Existing curated reference entry retained with its specific identity/scope notes.'
    qid=entity.get('id',item.get('wikidata_id',''));types=set(entity_types(entity))
    desc=entity.get('descriptions',{}).get('en',{}).get('value','')
    if qid in MANUAL_PENDING:return 'pending',None,MANUAL_PENDING[qid]
    if qid in MANUAL_BOTANICAL:return 'keep','botanical',MANUAL_BOTANICAL[qid]
    if qid in MANUAL_REJECT:return 'rejected',None,MANUAL_REJECT[qid]
    if qid in MANUAL_CULINARY:return 'keep','culinary',MANUAL_CULINARY[qid]
    if types&TYPE_CULINARY:return 'keep','culinary','Explicit Wikidata spice / spice mix / food flavoring / condiment type.'
    if types&TYPE_REJECT:return 'rejected',None,'Entity type is outside botanical/spice-material catalogue: '+','.join(sorted(types&TYPE_REJECT))
    if REJECT_DESCRIPTION.search(desc):return 'rejected',None,'Source description identifies a company, prepared dish/drink, event, object, or other non-material topic.'
    if types&TYPE_BOTANICAL or claim_values(entity,'P225') or BOTANICAL_DESCRIPTION.search(desc):return 'keep','botanical','Taxon/cultivar/common-name reference only; culinary suitability is not established.'
    if CULINARY_DESCRIPTION.search(desc):return 'keep','culinary','Source description explicitly identifies a spice, culinary seasoning, or flavoring material.'
    return 'pending',None,'Insufficient evidence to classify as a botanical reference or culinary spice material; manual review required.'

def clean():
    from opencc import OpenCC
    conv=OpenCC('t2s')
    def normalized(value):return norm(conv.convert(str(value or '')))
    entities,types,provenance=evidence_maps();resolved=read('redirect_resolution.json') if (HERE/'redirect_resolution.json').exists() else {}
    intros=read('pending_extracts.json') if (HERE/'pending_extracts.json').exists() else {}
    original=rows();raw={r['id']:r for r in original};items={r['id']:json.loads(r['payload']) for r in original}
    curated={e['id']:e for e in json.loads((ROOT/'data/catalog.json').read_text())['entries']}
    decisions={};kept={};evidence={};counts={}
    for row in original:
        key=row['id'];item=items[key];qid=item.get('wikidata_id') or resolved.get(key,{}).get('qid','');entity=entities.get(qid,{})
        ev={**provenance.get(qid,{}),'wikidata_id':qid,'p31':entity_types(entity),'scientific_name_claims':claim_values(entity,'P225'),'description_en':entity.get('descriptions',{}).get('en',{}).get('value','')}
        if key in resolved:ev['redirect']=resolved[key]
        if key in intros:ev['wikipedia_intro']={k:v for k,v in intros[key].items() if k!='extract'}
        if row['scope']=='botanical':status,scope,reason='keep','botanical','Existing GBIF accepted species reference; no culinary use inferred.'
        else:status,scope,reason=classify(item,entity)
        if status=='pending' and qid not in MANUAL_PENDING and key in intros:
            lead=intros[key]['extract'].split('\n')[0][:400]
            if REJECT_DESCRIPTION.search(lead):status,scope,reason='rejected',None,'Linked Wikipedia introduction identifies a non-material topic (prepared dish/drink, object, event, medical preparation or activity). Review remains reversible in quarantine.'
            elif BOTANICAL_DESCRIPTION.search(lead):status,scope,reason='keep','botanical','Linked Wikipedia introduction identifies a cultivar or botanical common name; retained as reference only.'
        if qid:item['wikidata_id']=qid
        if key in resolved:
            r=resolved[key];item.setdefault('wiki',{})[r['site']]=r['title']
        if entity:
            zh,en=labels(entity)
            if row['review_state']!='curated':
                if zh:item['name_zh']=zh
                if en:item['name_en']=en
            scientific=next((v for v in claim_values(entity,'P225') if isinstance(v,str)),None)
            if scientific and row['review_state']!='curated':item['scientific']=scientific
            image=next((v for v in claim_values(entity,'P18') if isinstance(v,str)),None)
            if image:item['primary_image']=image
            item['wiki']={**item.get('wiki',{}),**{site:v['title'] for site,v in entity.get('sitelinks',{}).items() if site in {'zhwiki','enwiki'}}}
            item['aliases']=list(dict.fromkeys([*item.get('aliases',[]),*[v['value'] for lang in ('zh','zh-hans','zh-hant','zh-tw','en') for v in entity.get('aliases',{}).get(lang,[])]]))
        if status=='keep':
            item['scope']=scope
            if key in curated:
                # Overwrite imported generic view fields with the reviewed original.
                item.pop('scope_note',None)
                item={**item,**curated[key],'name_zh':curated[key]['name'],'name_en':curated[key]['english'],'scope':'culinary','review_state':'curated','source':'editorial'}
            elif scope=='botanical':
                item['review_state']='reference_only';item['scope_note']='植物分类或品种参考记录，未核实食用或调味用途。 / Botanical or cultivar reference; culinary use is not verified.'
                for field in ['forms','group','groups','commons_query','baidu','intro','intro_en']:item.pop(field,None)
            else:
                item['review_state']='source_classified';item['scope_note']='按来源分类的调味材料或混合物；成分、品种与食用条件请查阅原始资料。 / Source-classified culinary material or mixture; verify composition, identity and food use in the original sources.'
                item.pop('forms',None)
            item['cleaning_evidence']=ev;kept[key]=item
        decisions[key]={'id':key,'name_zh':row['name_zh'],'name_en':row['name_en'],'status':status,'scope':scope,'reason':reason,'evidence':ev};evidence[key]=ev
    # Deduplicate by entity identity first, then exact scientific name. Curated
    # records win, then existing accepted GBIF species. No fuzzy taxon merges.
    ordered=sorted(kept,key=lambda k:(0 if k in curated else 1 if raw[k]['source']=='gbif' else 2,k))
    by_qid={};by_sci={};merge={}
    for key in ordered:
        item=kept[key];qid=item.get('wikidata_id','');sci=normalized(item.get('scientific',''))
        target=(by_qid.get(qid) if qid else None) or (by_sci.get(sci) if sci else None)
        if target and target!=key:
            merge[key]=target;decisions[key].update(status='merged',target_id=target,reason='Exact shared Wikidata entity or scientific name; retained '+target)
            dst=kept[target];dst['aliases']=list(dict.fromkeys([*dst.get('aliases',[]),item.get('name_zh',''),item.get('name_en',''),*item.get('aliases',[])]))
            dst['wiki']={**item.get('wiki',{}),**dst.get('wiki',{})};dst['references']={**item.get('references',{}),**dst.get('references',{})}
            dst.setdefault('merged_records',[]).append({'id':key,'source':raw[key]['source'],'source_key':raw[key]['source_key'],'wikidata_id':qid,'evidence':evidence[key]})
            if not dst.get('primary_image') and item.get('primary_image'):dst['primary_image']=item['primary_image']
        else:
            if qid:by_qid[qid]=key
            if sci:by_sci[sci]=key
    for key in merge:del kept[key]
    dest=HERE/'cleaned_catalogue.sqlite3'
    if dest.exists():dest.unlink()
    src=sqlite3.connect(SOURCE);db=sqlite3.connect(dest);src.backup(db);src.close()
    db.executescript('''PRAGMA journal_mode=DELETE;
      CREATE TABLE IF NOT EXISTS quarantine(id TEXT PRIMARY KEY,status TEXT,reason TEXT,evidence TEXT,payload TEXT,original_scope TEXT,updated_at TEXT);
      CREATE TABLE IF NOT EXISTS catalogue_meta(key TEXT PRIMARY KEY,value TEXT);
      DELETE FROM entries; DELETE FROM aliases; DELETE FROM entry_search; DELETE FROM quarantine;
    ''')
    at=now()
    def clean_alias(x):
        x=html.unescape(re.sub('<[^>]*>','',str(x))).strip()
        return x if x and len(x)<=240 and not re.search(r'https?://|[\x00-\x08\x0b\x0c\x0e-\x1f]',x) else ''
    for key,item in kept.items():
        zh=item.get('name_zh','');en=item.get('name_en') or item.get('english','');sci=item.get('scientific','');wiki=item.get('wiki',{})
        item['aliases']=list(dict.fromkeys(x for a in item.get('aliases',[]) if (x:=clean_alias(a))))
        text=normalized(' '.join([zh,en,sci,item.get('family',''),*item['aliases']]))
        db.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,zh,en,sci,item.get('family',''),item['scope'],item['review_state'],item.get('source',''),str(item.get('source_key','')),item.get('wikidata_id',''),wiki.get('zhwiki',''),wiki.get('enwiki',''),json.dumps(item,ensure_ascii=False),text,at))
        db.execute('INSERT INTO entry_search VALUES(?,?)',(key,text))
        for lang,value in [('zh',zh),('en',en),('scientific',sci),*[('alias',x) for x in item['aliases']]]:
            if value:db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?)',(key,lang,value,normalized(value)))
    for key,d in decisions.items():
        if d['status']!='keep':db.execute('INSERT INTO quarantine VALUES(?,?,?,?,?,?,?)',(key,d['status'],d['reason'],json.dumps(d['evidence'],ensure_ascii=False),raw[key]['payload'],raw[key]['scope'],at))
    for old,target in merge.items():
        db.execute('INSERT OR IGNORE INTO membership SELECT node_id,? FROM membership WHERE entry_id=?',(target,old))
    db.execute('DELETE FROM membership WHERE entry_id NOT IN (SELECT id FROM entries)')
    db.execute('DELETE FROM jobs')
    db.execute("INSERT OR REPLACE INTO nodes VALUES('root-all','完整馆藏','All records','root','all','','{}')")
    db.executemany('INSERT OR IGNORE INTO edges VALUES(?,?)',[('root-all','root-culinary'),('root-all','root-botanical')])
    db.execute("INSERT OR REPLACE INTO nodes VALUES('wiki-botanical-references','维基植物与品种参考','Wiki plant & cultivar references','category','botanical','','{}')")
    db.execute("INSERT OR IGNORE INTO edges VALUES('root-botanical','wiki-botanical-references')")
    db.execute("INSERT OR IGNORE INTO membership SELECT 'wiki-botanical-references',id FROM entries WHERE scope='botanical' AND source<>'gbif'")
    count=collections.Counter(d['status'] for d in decisions.values())
    scope_counts=dict(db.execute('SELECT scope,COUNT(*) FROM entries GROUP BY scope'))
    cutoff=max(r['updated_at'] for r in original)
    metadata={'schema':4,'cleaned_at':at,'source_cutoff':cutoff,'original_total':len(original),'original_culinary':sum(r['scope']=='culinary' for r in original),'retained':len(kept),'scope_counts':scope_counts,'decisions':dict(count),'evidence_entities':len(entities),'evidence_types':len(types),'safety_note':'Botanical taxonomy is not a statement of edibility. A source description is not a food safety review.'}
    for k,v in metadata.items():db.execute('INSERT OR REPLACE INTO catalogue_meta VALUES(?,?)',(k,json.dumps(v,ensure_ascii=False)))
    db.commit();db.execute('VACUUM');db.close()
    save('cleaning_report.json',metadata);save('cleaning_decisions.json',list(decisions.values()))
    type_labels={qid:{'name_en':labels(e)[1],'name_zh':labels(e)[0],'decision':'reject' if qid in TYPE_REJECT else 'botanical' if qid in TYPE_BOTANICAL else 'culinary' if qid in TYPE_CULINARY else 'review','description_en':e.get('descriptions',{}).get('en',{}).get('value','')} for qid,e in types.items()}
    save('entity_type_labels.json',{'schema':1,'created_at':at,'source':'Wikidata wbgetentities P31 types; exact ids only','types':type_labels,'manual_reject':MANUAL_REJECT,'manual_pending':MANUAL_PENDING,'manual_botanical':MANUAL_BOTANICAL,'manual_culinary':MANUAL_CULINARY,'rules':{'reject_description':REJECT_DESCRIPTION.pattern,'culinary_description':CULINARY_DESCRIPTION.pattern,'botanical_description':BOTANICAL_DESCRIPTION.pattern}})
    save('entity_type_rules.json',{'schema':1,'created_at':at,'excluded_types':{q:type_labels.get(q,{}).get('name_en',q)+' is outside botanical/spice materials' for q in sorted(TYPE_REJECT)},'culinary_types':sorted(TYPE_CULINARY),'taxon_types':sorted(TYPE_BOTANICAL),'pending_types':sorted(set(types)-TYPE_REJECT-TYPE_CULINARY-TYPE_BOTANICAL),'manual_reject':MANUAL_REJECT,'manual_pending':MANUAL_PENDING,'manual_botanical':MANUAL_BOTANICAL,'manual_culinary':MANUAL_CULINARY,'description_patterns':{'reject':REJECT_DESCRIPTION.pattern,'culinary':CULINARY_DESCRIPTION.pattern,'botanical':BOTANICAL_DESCRIPTION.pattern},'notes':['Unknown entity types remain pending.','Manual identity decisions precede type rules.','Taxon/cultivar identifies reference material, not edibility.']})
    print(json.dumps(metadata,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['fetch','clean'])
    args=parser.parse_args()
    if args.action=='fetch':asyncio.run(fetch())
    else:clean()
