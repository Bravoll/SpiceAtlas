"""Runtime-only provider availability; stored, manually dismissed change notices."""
from __future__ import annotations
import asyncio,copy,time
from urllib.parse import urlsplit
import httpx
from .activity import activity
from .workspaces import workspaces
from .preferences import preferences
from .storage import now_iso
from .network import client_options
from .translations import cloud_translate
BROWSER_PROBES=[
 {'id':'zhwiki','url':'https://zh.wikipedia.org/w/api.php','params':{'action':'parse','page':'歐芹','redirects':1,'prop':'revid','format':'json','origin':'*'}},
 {'id':'enwiki','url':'https://en.wikipedia.org/w/api.php','params':{'action':'parse','page':'Parsley','redirects':1,'prop':'revid','format':'json','origin':'*'}},
 {'id':'commons','url':'https://commons.wikimedia.org/w/api.php','params':{'action':'query','list':'search','srnamespace':6,'srsearch':'parsley filetype:bitmap','srlimit':1,'format':'json','origin':'*'}},
]
class Health:
 interval=600
 def __init__(self):self.reports={};self.tasks={};self.browser={};self.loop_task=None;self.wakeup=None
 def report(self):return copy.deepcopy(self.reports.get(workspaces.current_id,{'phase':'checking','revision':0,'services':{},'interval_seconds':self.interval,'sample':'欧芹 / Parsley'}))
 def publish(self,rows):
  key=workspaces.current_id;previous=self.reports.get(key);services={};changed=[]
  for item in rows:
   row=dict(item);service=row['id'];row.setdefault('backend_ok',bool(row.get('ok')))
   browser=self.browser.get((key,service))
   if browser and time.time()-browser['at']<=self.interval+120:row.update(browser_ok=browser['ok'],browser_checked_at=browser['checked_at'])
   else:row.pop('browser_ok',None);row.pop('browser_checked_at',None)
   row['ok']=bool(row['backend_ok'] or row.get('browser_ok'));services[service]=row
   old=(previous or {}).get('services',{}).get(service)
   if old and old['ok']!=row['ok'] or not old and not row['ok']:changed.append({'service':service,'before':old['ok'] if old else None,'now':row['ok'],'http_status':row.get('http_status'),'message':row.get('message','')})
  # Do not create a second "initial failure" notice when only browser probes finished first.
  if previous and previous.get('phase')=='checking':
   changed=[{'service':k,'before':None,'now':v['ok'],'http_status':v.get('http_status'),'message':v.get('message','')} for k,v in services.items() if not v['ok']]
  revision=(previous or {}).get('revision',0)+(1 if changed or not previous else 0)
  report={'phase':'ready','checked_at':now_iso(),'revision':revision,'services':services,'interval_seconds':self.interval,'sample':'欧芹 / Parsley'}
  self.reports[key]=report
  if changed:activity.notify('来源可用性变化 / Source availability changed',{'revision':revision,'changes':changed});activity.log('services.change',{'revision':revision,'changes':changed})
  return copy.deepcopy(report)
 def browser_results(self,rows):
  key=workspaces.current_id
  for row in rows:
   if row.get('id') in {'zhwiki','enwiki','commons'} and isinstance(row.get('ok'),bool):self.browser[(key,row['id'])]={'ok':row['ok'],'at':time.time(),'checked_at':now_iso()}
  previous=self.reports.get(key)
  if previous and previous.get('phase')=='ready':return self.publish(list(previous['services'].values()))
  return self.report()
 def specs(self):
  p=preferences.values();rows=[{**x,'kind':'api'} for x in BROWSER_PROBES]
  rows.extend([
   {'id':'wikidata','url':'https://www.wikidata.org/w/api.php','params':{'action':'wbsearchentities','search':'parsley','language':'en','limit':1,'format':'json'},'kind':'api'},
   {'id':'gbif','url':'https://api.gbif.org/v1/species/match','params':{'name':'Petroselinum crispum'},'kind':'api'},
   {'id':'commons_web','url':'https://commons.wikimedia.org/wiki/Category:Petroselinum_crispum','kind':'web'},
   {'id':'wikidata_web','url':'https://www.wikidata.org/wiki/Q25284','kind':'web'},
   {'id':'gbif_web','url':'https://www.gbif.org/species/7828157','kind':'web'},
   {'id':'zhwiki_web','url':'https://zh.wikipedia.org/wiki/歐芹','kind':'web'},
   {'id':'enwiki_web','url':'https://en.wikipedia.org/wiki/Parsley','kind':'web'},
   {'id':'bing','url':'https://www.bing.com/search?q=parsley&mkt=en-AU','kind':'web'},
   {'id':'bing_cn','url':'https://cn.bing.com/search?q=%E6%AC%A7%E8%8A%B9&mkt=zh-CN','kind':'web'},
   {'id':'google','url':'https://www.google.com/search?q=parsley&hl=en','kind':'web'},
   {'id':'baidu','url':'https://baike.baidu.com/item/%E6%AC%A7%E8%8A%B9','kind':'web'},
   {'id':'baidu_images','url':'https://image.baidu.com/search/index?tn=baiduimage&word=parsley','kind':'web'},
  ])
  from .catalogue import catalogue
  entry=catalogue.get('parsley') or {}
  for key,ref in entry.get('references',{}).items():
   if key not in {x['id'] for x in rows}:rows.append({'id':key,'url':ref['url'],'kind':'web'})
  import json
  from .storage import ROOT
  for record in json.loads((ROOT/'data/catalog.json').read_text('utf-8'))['entries']:
   for key,ref in record.get('references',{}).items():
    if key not in {x['id'] for x in rows}:rows.append({'id':key,'url':ref['url'],'kind':'web','tested_entry':record['id'],'sample_note':'Representative known page; Parsley mapping not available'})
  if p['lm_enabled']:rows.append({'id':'translation_local','url':p['lm_base_url'].rstrip('/')+'/models','kind':'function','local':True})
  if p['google_translate_key']:rows.append({'id':'translation_google','url':'https://translation.googleapis.com','kind':'function','cloud':'google'})
  if p['azure_translate_key']:rows.append({'id':'translation_azure','url':'https://api.cognitive.microsofttranslator.com','kind':'function','cloud':'azure'})
  if p['google_api_key'] and p['google_cse_id']:rows.append({'id':'google_images','url':'https://customsearch.googleapis.com/customsearch/v1','params':{'key':p['google_api_key'],'cx':p['google_cse_id'],'q':'parsley','searchType':'image','num':1},'kind':'api'})
  return rows
 async def probe(self,spec,gate):
  result={'id':spec['id'],'kind':spec['kind'],'host':urlsplit(spec['url']).hostname,'url':spec['url'],'checked_at':now_iso(),'tested_entry':spec.get('tested_entry','parsley')}
  try:
   async with gate:
    if spec.get('cloud'):
     await cloud_translate(spec['cloud'],['Parsley'],'zh-Hans',preferences.values());return {**result,'ok':True,'http_status':200}
    options=client_options(9);options['follow_redirects']=True;options['max_redirects']=4
    if spec.get('local'):
     options.pop('proxy',None);options['trust_env']=False
     key=preferences.values()['lm_api_key']
     if key:options['headers']['Authorization']='Bearer '+key
    async with httpx.AsyncClient(**options) as client:response=await client.get(spec['url'],params=spec.get('params'))
   result['http_status']=response.status_code
   if response.status_code!=200:return {**result,'ok':False,'message':'HTTP '+str(response.status_code)}
   if spec['kind'] in {'api','function'}:
    data=response.json()
    if not isinstance(data,dict) or data.get('error'):return {**result,'ok':False,'message':'API error or invalid JSON'}
    if spec.get('local') and not data.get('data'):return {**result,'ok':False,'message':'No loaded model'}
   else:
    text=response.text[:30000].lower();url=str(response.url).lower()
    challenge=any(x in url for x in ('/sorry/','/consent','/captcha','wappass.baidu')) or '<title>just a moment' in text or 'enable javascript and cookies to continue' in text
    if challenge:return {**result,'ok':False,'message':'Verification or consent page'}
    result['frame_restricted']=response.headers.get('x-frame-options','').upper() in {'DENY','SAMEORIGIN'} or 'frame-ancestors' in response.headers.get('content-security-policy','').lower()
   return {**result,'ok':True}
  except (httpx.HTTPError,ValueError,KeyError,ImportError):return {**result,'ok':False,'message':'Connection, timeout or API response failed'}
 async def check(self):
  gate=asyncio.Semaphore(4);results=await asyncio.gather(*(self.probe(x,gate) for x in self.specs()));return self.publish(results)
 def restart(self):
  key=workspaces.current_id;task=self.tasks.get(key)
  if task and not task.done():task.cancel()
  self.tasks[key]=asyncio.create_task(self.check());return self.report()
 async def loop(self):
  while True:
   key=workspaces.active_id
   with workspaces.use(key):
    task=self.tasks.get(key)
    if not task or task.done():self.restart()
   self.wakeup.clear()
   try:await asyncio.wait_for(self.wakeup.wait(),timeout=self.interval)
   except asyncio.TimeoutError:pass
 def start(self):
  self.wakeup=asyncio.Event();self.loop_task=asyncio.create_task(self.loop())
 def switched(self):
  if self.wakeup:self.wakeup.set()
 async def stop(self):
  current_loop=asyncio.get_running_loop()
  all_tasks=[task for task in list(self.tasks.values())+([self.loop_task] if self.loop_task else []) if task.get_loop() is current_loop]
  for task in all_tasks:task.cancel()
  await asyncio.gather(*all_tasks,return_exceptions=True);self.tasks.clear();self.loop_task=None;self.wakeup=None
health=Health()
