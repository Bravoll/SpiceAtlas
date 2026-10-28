import asyncio,json,sqlite3,sys
from pathlib import Path
import curate_catalogue as c
async def main():
 decisions=c.read('cleaning_decisions.json');pending={d['id'] for d in decisions if d['status']=='pending'}
 db=sqlite3.connect(c.SOURCE);items={r[0]:json.loads(r[1]) for r in db.execute('select id,payload from entries') if r[0] in pending};db.close()
 index={}
 async with c.httpx.AsyncClient(headers={'User-Agent':c.UA,'Accept':'application/json'},follow_redirects=True) as client:
  for site in ['enwiki','zhwiki']:
   batchitems=[(k,v.get('wiki',{}).get(site)) for k,v in items.items() if v.get('wiki',{}).get(site) and k not in index]
   for start in range(0,len(batchitems),20):
    batch=batchitems[start:start+20];file=f'raw/pending_extracts_{site}_{start:04}.json'
    if (c.HERE/file).exists():ev=c.read(file)
    else:
     ev=await c.request(client,'https://'+('en' if site=='enwiki' else 'zh')+'.wikipedia.org/w/api.php',{'action':'query','titles':'|'.join(x[1] for x in batch),'redirects':1,'prop':'extracts','exintro':1,'explaintext':1,'exlimit':'max','formatversion':2});c.save(file,ev)
    q=ev['response'].get('query',{});redirect={c.norm(x['from']):x['to'] for x in [*q.get('normalized',[]),*q.get('redirects',[])]};pages={c.norm(p['title']):p for p in q.get('pages',[])}
    for key,title in batch:
     seen=set()
     while c.norm(title) in redirect and c.norm(title) not in seen:
      seen.add(c.norm(title));title=redirect[c.norm(title)]
     p=pages.get(c.norm(title),{});text=p.get('extract','')
     if text:index[key]={'site':site,'title':title,'pageid':p.get('pageid'),'extract':text,'fetched_at':ev['fetched_at'],'evidence_file':file}
    c.save('pending_extracts.json',index);print(site,start+len(batch),'/',len(batchitems),len(index),flush=True)
asyncio.run(main())
