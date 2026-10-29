from __future__ import annotations
import argparse
import asyncio
import json
import os
import secrets
from typing import Literal
from contextlib import asynccontextmanager
from atlas.workspaces import workspaces
from atlas.activity import activity
from atlas.health import health, BROWSER_PROBES
from atlas.resources import resource_plan, image_gateways, language_policy, available
from atlas.providers import ARTICLE_VARIANT
from atlas.image_lexicon import lexicon
from atlas.pronunciation import name_metadata, pronunciations
from atlas.launcher_protocol import runtime_identity
from urllib.parse import urlsplit

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from atlas.catalogue import catalogue
from atlas.discovery import GBIF_FAMILIES, WIKI_ROOTS, import_wiki_members, jobs, resolve_entry
from atlas.network import SourceFailure, diagnostics
from atlas.preferences import preferences
from atlas.providers import Reader, WIKIS, entry_for, frame_capability, outbound_images, sources_for
from atlas.storage import ROOT

@asynccontextmanager
async def lifespan(app):
    health.start()
    yield
    await health.stop()
    for version in workspaces.list()["versions"]:await jobs.pause_all(version["id"])

app=FastAPI(title="Spice Atlas · Live Catalogue",version="0.6.0",lifespan=lifespan)
reader=Reader()

@app.exception_handler(ValueError)
async def invalid_value(request:Request,exc:ValueError):return JSONResponse({"error":str(exc)},status_code=400)

@app.exception_handler(SourceFailure)
async def source_failure(request:Request,exc:SourceFailure):
    status=404 if exc.code=="not_found" else 502
    return JSONResponse({"error":str(exc),"diagnostic":exc.public()},status_code=status)

@app.middleware("http")
async def boundaries(request:Request,call_next):
    if request.method not in {"GET","HEAD","OPTIONS"}:
        origin=request.headers.get("origin")
        if origin and urlsplit(origin).netloc!=request.headers.get("host"):
            return JSONResponse({"error":"Use the local application page."},status_code=403)
        try:
            if int(request.headers.get("content-length","0"))>16_000_000:
                return JSONResponse({"error":"Request body too large"},status_code=413)
        except ValueError:
            return JSONResponse({"error":"Invalid content length"},status_code=400)
    active=workspaces.active_id
    supplied=request.headers.get("X-Atlas-Version")
    if supplied and supplied!=active and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/versions"):
        return JSONResponse({"error":"The active version changed; reload this tab.","active_version":active},status_code=409)
    with workspaces.use(active):response=await call_next(request)
    response.headers["X-Atlas-Version"]=workspaces.active_id
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; media-src 'self' https://api.dictionaryapi.dev https://upload.wikimedia.org https://ssl.gstatic.com; connect-src 'self' https://zh.wikipedia.org https://en.wikipedia.org https://commons.wikimedia.org; frame-src 'self' https://www.bing.com https://*.bing.com; object-src 'none'; base-uri 'self'"
    return response

@app.get("/")
def index():return FileResponse(ROOT/"static/index.html")

@app.get("/api/catalog")
def catalog(q:str="",scope:Literal["culinary","botanical","all"]="all",node:str|None=None,offset:int=0,limit:int=30,group:str|None=None,collection:Literal["catalogue","favorites","history"]="catalogue"):
    return catalogue.page(q[:150],scope,node,max(0,offset),max(1,min(limit,100)),group,collection,preferences.values()["history_order"])

@app.get("/api/catalog/stats")
def catalog_stats():return catalogue.stats()

@app.get('/api/catalog/random')
def random_record(scope:Literal['culinary','botanical','all']|None=None,exclude:str=''):
    value=catalogue.random_entry(scope or preferences.values()['random_scope'],exclude[:180])
    if not value:raise HTTPException(404,'No eligible local records in this scope')
    return value

@app.get("/api/catalog/nodes")
def nodes(parent:str="root-culinary",language:str="zh-Hans"):
    return {"parent":parent,"nodes":catalogue.children(parent,language)}

@app.get("/api/entry/{entry_id}")
async def entry(entry_id:str,resolve:bool=False,browser_language:str="en"):
    p=preferences.values()
    item=await resolve_entry(entry_id,force=True) if resolve else entry_for(entry_id)
    plan=resource_plan(item,p["ui_language"],browser_language,p["content_language"],health.report())
    return {**item,**name_metadata(item),**plan,"image_gateways":image_gateways(item,mode=p["ui_language"],browser=browser_language,preferred=p["content_language"],report=health.report()),"related":catalogue.related(item),"favorite":any(r["entry_id"]==entry_id for r in activity.collection("favorites"))}

@app.get('/api/pronunciation/{entry_id}')
async def pronunciation(entry_id:str):
    return await pronunciations.for_entry(entry_for(entry_id),online=available('pronunciation_dictionary',health.report()))

@app.get("/api/article/{entry_id}")
async def article(entry_id:str,source:str="auto",refresh:bool=False,preferred:str="auto",browser_language:str="en"):
    p=preferences.values();item=entry_for(entry_id);plan=resource_plan(item,p['ui_language'],browser_language,p['content_language'] if preferred=='auto' else preferred,health.report());policy=plan['policy']
    selected=next((row for row in plan['sources'] if row['key']==source),None)
    if source=='auto':selected=next(iter(plan['sources']),None)
    if selected and selected['id'] not in WIKIS:
        return {'mode':'external','source':selected['id'],'title':selected['name_en'] if policy['ui']=='en' else selected['name'],'source_url':selected['url'],'message':'Open the live source website / 前往实时来源网页','language':selected['language']}
    actual=selected['id'] if selected else source.split(':')[0]
    if actual in WIKIS and not available(actual,health.report()):raise SourceFailure('Source is temporarily unavailable',code='source_unavailable')
    token=ARTICLE_VARIANT.set(policy['variant'])
    try:return await reader.article(entry_id,'auto' if source=='auto' else actual,refresh,policy['primary'])
    finally:ARTICLE_VARIANT.reset(token)

@app.get("/api/images/{entry_id}")
async def images(entry_id:str,provider:str="commons",form:str|None=None,refresh:bool=False,browser_language:str="en",profile:str|None=None):
    p=preferences.values();gateways=image_gateways(entry_for(entry_id),form,p['ui_language'],browser_language,p['content_language'],health.report(),profile)
    if provider not in gateways:raise SourceFailure('Image source is temporarily unavailable',code='source_unavailable')
    value=await reader.images(entry_id,provider,form,refresh,profile);value['gateways']=gateways;return value

@app.get("/api/media/{identifier}")
async def media(identifier:str):
    try:
        async with reader.locks.setdefault((workspaces.current_id,"media:"+identifier),asyncio.Lock()):
            path=await reader.image_file(identifier)
        return FileResponse(path,headers={"Cache-Control":"public,max-age=86400"})
    except httpx.HTTPError:
        raise SourceFailure("Image connection failed; try direct delivery.",code="image_unavailable") from None

class TranslationRequest(BaseModel):
    entry_id:str
    source:Literal["zhwiki","enwiki"]
    target:str="zh-Hans"
    variant:str="zh-hans"
    refresh:bool=False

@app.post("/api/translate")
async def translate(body:TranslationRequest):
    token=ARTICLE_VARIANT.set("zh-hant" if body.variant=="zh-hant" else "zh-hans")
    try:return await reader.translate(body.entry_id,body.source,body.refresh,body.target)
    finally:ARTICLE_VARIANT.reset(token)

@app.get("/api/settings")
def settings():return preferences.public()

@app.post("/api/settings")
async def save_settings(value:dict=Body(...)):
    try:
        before=preferences.values();result=preferences.save(value);after=preferences.values();activity.log("settings.save",{"fields":[k for k in value if "key" not in k]})
        connection_keys={"proxy_url","trust_env","timeout_seconds","user_agent","lm_enabled","lm_base_url","lm_model","lm_api_key","google_translate_key","azure_translate_key","azure_region","google_api_key","google_cse_id"}
        if health.loop_task and any(before.get(k)!=after.get(k) for k in connection_keys):health.restart()
        return result
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post("/api/settings/test-model")
async def test_model():return await reader.model_models()

@app.post("/api/settings/diagnostics")
async def diagnose():
    health.restart();return health.report()

@app.get("/api/status")
def status():
    return {"version":"0.6.0",**runtime_identity(ROOT),"active_version":workspaces.active_id,"cache":reader.store.stats(),"catalogue":catalogue.stats(),
            "providers":[{"id":"wikimedia","name":"Wikipedia / Commons","mode":"live_api"},
                         {"id":"wikidata","name":"Wikidata names / aliases","mode":"metadata_api"},
                         {"id":"gbif","name":"GBIF botanical reference","mode":"taxonomy_api"},
                         {"id":"baidu","name":"Baidu","mode":"external"},
                         {"id":"bing","name":"Bing","mode":"frame_if_permitted"},
                         {"id":"google","name":"Google","mode":"existing_key_only"}]}

@app.post('/api/launcher/shutdown')
async def launcher_shutdown(request:Request):
    expected=os.environ.get('SPICE_LAUNCHER_CONTROL_TOKEN','')
    shutdown=getattr(app.state,'launcher_shutdown',None)
    if not expected or not callable(shutdown):raise HTTPException(404,'Managed launcher is not active')
    if not secrets.compare_digest(request.headers.get('X-Atlas-Launcher',''),expected):raise HTTPException(403,'Launcher authorization required')
    shutdown()
    return {'ok':True}

class BrowserIngest(BaseModel):
    entry_id:str
    source:str="enwiki"
    form:str|None=None
    data:dict
    variant:str="zh-hans"
    browser_language:str="en"
    profile:str|None=None

@app.get("/api/browser-plan/article/{entry_id}")
def browser_article_plan(entry_id:str,source:Literal["zhwiki","enwiki"]="enwiki",variant:str="zh-hans"):
    item=entry_for(entry_id)
    title=item.get("wiki",{}).get(source) or item.get("scientific") or item["english"]
    return {"url":WIKIS[source]+"/w/api.php","source":source,
            "params":{"action":"parse","page":title,"redirects":1,"prop":"text|tocdata|images|revid|displaytitle",
                      "format":"json","formatversion":2,"origin":"*","disableeditsection":1,
                      "variant":("zh-hant" if variant=="zh-hant" else "zh-hans") if source=="zhwiki" else "en"}}

@app.get("/api/browser-plan/images/{entry_id}")
def browser_images_plan(entry_id:str,form:str|None=None,profile:str|None=None):
    item=entry_for(entry_id);form=form or item["forms"][0]["id"]
    if form not in {f["id"] for f in item["forms"]}:raise HTTPException(400,"Unknown form")
    return {"url":"https://commons.wikimedia.org/w/api.php","form":form,"params":reader.commons_params(item,form,profile),"queries":reader.commons_plans(item,form,profile),"profile":lexicon.queries(item,lexicon.form(item,form,profile))}

@app.post("/api/browser-ingest/article")
def browser_article_ingest(value:BrowserIngest):
    token=ARTICLE_VARIANT.set("zh-hant" if value.variant=="zh-hant" else "zh-hans")
    try:return reader.browser_article(value.entry_id,value.source,value.data)
    finally:ARTICLE_VARIANT.reset(token)

@app.post("/api/browser-ingest/images")
def browser_image_ingest(value:BrowserIngest):
    item=entry_for(value.entry_id)
    form=value.form or item["forms"][0]["id"];result=reader.browser_images(value.entry_id,form,value.data,value.profile);p=preferences.values()
    result["gateways"]=image_gateways(item,form,p["ui_language"],value.browser_language,p["content_language"],health.report(),value.profile);return result

@app.get("/api/frame/{entry_id}")
async def frame(entry_id:str,provider:Literal["bing","google","baidu"],form:str|None=None,browser_language:str="en",profile:str|None=None):
    p=preferences.values();links=image_gateways(entry_for(entry_id),form,p['ui_language'],browser_language,p['content_language'],health.report(),profile)
    if provider not in links:return {'can_try':False,'reason':'Temporarily unavailable','url':''}
    result=await frame_capability(entry_for(entry_id),provider,form,url=links[provider]);result['url']=links[provider];return result

@app.get("/api/discovery/options")
def discovery_options():
    return {"wiki_roots":[{"id":key,"source":v[0],"category":v[1],"label_zh":v[2],"label_en":v[3]} for key,v in WIKI_ROOTS.items()],
            "gbif_families":[{"id":key,"label_en":key,"label_zh":v["zh"],"key":v["key"]} for key,v in GBIF_FAMILIES.items()]}

@app.get("/api/discovery/search")
async def discovery_search(q:str,language:Literal["zh","en"]="zh"):
    from atlas.network import fetch_json
    from atlas.content import plain
    source="zhwiki" if language=="zh" else "enwiki"
    data=await fetch_json(WIKIS[source]+"/w/api.php",{"action":"query","list":"search","srsearch":q[:150],"srlimit":10,"format":"json","formatversion":2})
    return {"source":source,"results":[{"pageid":r["pageid"],"title":r["title"],"snippet":plain(r.get("snippet",""))} for r in data.get("query",{}).get("search",[])]}

class ImportPage(BaseModel):
    source:Literal["zhwiki","enwiki"]
    pageid:int=Field(gt=0)
    title:str

@app.post("/api/discovery/import-page")
async def import_page(value:ImportPage):
    root="wiki-search-import"
    catalogue.node(root,"远程检索导入","Remote search imports","category","culinary",parent="root-culinary")
    await import_wiki_members(value.source,[{"ns":0,"pageid":value.pageid,"title":value.title}],root)
    key=catalogue.find_wiki(value.source,value.title)
    return {"entry_id":key,"stats":catalogue.stats()}

@app.get("/api/jobs")
def list_jobs():return {"jobs":jobs.list()}

class NewJob(BaseModel):
    kind:Literal["wiki","gbif"]
    options:dict={}

@app.post("/api/jobs")
async def create_job(body:NewJob):
    try:job=jobs.create(body.kind,body.options)
    except ValueError as exc:raise HTTPException(400,str(exc))
    jobs.start(job);return jobs.public(job)

@app.post("/api/jobs/{job_id}/pause")
async def pause_job(job_id:str):
    if not jobs.get(job_id):raise HTTPException(404,"Job not found")
    await jobs.pause(job_id);return jobs.public(jobs.get(job_id))

@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id:str,value:dict=Body(default={})):
    job=jobs.get(job_id)
    if not job:raise HTTPException(404,"Job not found")
    if job["status"]=="completed":raise HTTPException(409,"Job already completed")
    if "max_categories" in value:
        job["state"]["max_categories"]=max(job["state"].get("max_categories",0),min(int(value["max_categories"]),2000))
    jobs.save(job);activity.log("import.resume",{"job_id":job_id,"progress":job["progress"],"max_categories":job["state"].get("max_categories")});jobs.start(job);return jobs.public(job)

@app.get("/api/export/{entry_id}")
def export(entry_id:str):
    item=entry_for(entry_id);articles=[]
    for source in WIKIS:
        cached,_,_=reader.stored(f"article:{entry_id}:{source}:"+("zh-hans" if source=="zhwiki" else "en"))
        if cached:articles.append(cached)
    return JSONResponse({"entry":item,"sources":sources_for(item),"articles":articles},
                        headers={"Content-Disposition":f'attachment; filename="spice-atlas-{entry_id}.json"'})

@app.get('/api/health')
def health_report():return {**health.report(),'notifications':activity.notifications()}

@app.get('/api/browser-plan/health')
def browser_health():return {'probes':BROWSER_PROBES,'interval_seconds':600}

@app.post('/api/health/browser')
def browser_health_results(value:dict=Body(...)):return health.browser_results(value.get('results',[])[:3])

@app.post('/api/notifications/{notice_id}/dismiss')
def dismiss_notice(notice_id:str):activity.dismiss(notice_id);return {'ok':True}

@app.get('/api/image-vocabulary')
def vocabulary():return lexicon.summary()

@app.get('/api/catalog/audit')
def audit(offset:int=0,limit:int=40,status:str=''):return catalogue.audit(max(0,offset),max(1,min(100,limit)),status)

@app.get('/api/collections/{kind}')
def collections(kind:Literal['favorites','history']):
    return {'rows':[{**row,'entry':catalogue.get(row['entry_id'])} for row in activity.collection(kind,preferences.values()['history_order']=='custom')]}

@app.post('/api/collections/{kind}/order')
def collection_order(kind:Literal['favorites','history'],value:dict=Body(...)):
    try:activity.reorder(kind,value['order'])
    except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc))
    return {'ok':True}

@app.post('/api/favorite/{entry_id}')
def favorite(entry_id:str,value:dict=Body(...)):
    entry_for(entry_id);activity.favorite(entry_id,bool(value.get('enabled',True)),str(value.get('note','')));return {'ok':True}

@app.post('/api/history/{entry_id}')
def history_entry(entry_id:str):entry_for(entry_id);activity.visit(entry_id);return {'ok':True}

@app.get('/api/logs')
def logs(before:int|None=None,limit:int=100,manager:bool=False):return {'rows':workspaces.manager_logs(before,limit) if manager else activity.events(before,limit)}

VIEW_KEYS={'entry','form','source','imageProvider','imageProfile','query','scope','node','path','offset','group','collection','mainScroll','catalogScroll','windowScroll','readerMode','textMode','typeStyle','frameOpen','frameFit','frameMode','frameExpanded','anchor'}
@app.get('/api/view-state')
def view_state():
    path=workspaces.directory()/'view_state.json';return json.loads(path.read_text('utf-8')) if path.exists() else {}

@app.post('/api/view-state')
def save_view(value:dict=Body(...)):
    safe={k:v for k,v in value.items() if k in VIEW_KEYS};text=json.dumps(safe,ensure_ascii=False)
    if len(text)>20000:raise HTTPException(400,'View state too large')
    path=workspaces.directory()/'view_state.json';tmp=path.with_suffix('.tmp');tmp.write_text(text,'utf-8');tmp.replace(path);return {'ok':True}

@app.get('/api/versions')
def versions():return {**workspaces.list(),'deleted':workspaces.trash()}

@app.post('/api/versions')
async def create_version(value:dict=Body(...)):
    try:
        source=value.get('source_id') or workspaces.active_id
        await jobs.pause_all(source)
        return workspaces.create(value.get('name',''),value.get('mode','copy'),source)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/versions/order')
def order_versions(value:dict=Body(...)):
    try:return workspaces.reorder(value.get('order'),value.get('sort'),value.get('direction','asc'))
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/versions/{key}/{action}')
async def version_action(key:str,action:Literal['switch','rename','delete','restore'],value:dict=Body(default={})):
    try:
        if action=='rename':workspaces.rename(key,value.get('name',''))
        elif action=='restore':workspaces.restore(key)
        else:
            await jobs.pause_all(workspaces.active_id)
            if action=='switch':workspaces.switch(key)
            else:
                await jobs.pause_all(key)
                task=health.tasks.pop(key,None)
                if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
                workspaces.remove(key)
            with workspaces.use(workspaces.active_id):
                from atlas.catalogue import Catalogue
                Catalogue(path=workspaces.directory()/'catalogue.sqlite3')
            health.switched()
        return {**workspaces.list(),'deleted':workspaces.trash()}
    except ValueError as exc:raise HTTPException(400,str(exc))

app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")

if __name__=="__main__":
    import uvicorn
    parser=argparse.ArgumentParser()
    parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    uvicorn.run(app,host=args.host,port=args.port,log_level="warning")
