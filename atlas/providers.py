"""Live, language-aware sources, image metadata and local translation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .catalogue import catalogue
from .content import article_content, plain, safe_url, translation_blocks, translated_html
from .discovery import resolve_entry
from .network import SourceFailure, fetch_json, client_options
from .preferences import ENV, preferences
from .storage import MEDIA, Store, now_iso, media_root
from .image_lexicon import lexicon
from .preferences import TRANSLATION_LANGUAGES
from .translations import cloud_translate, local_translate, validate_numbers, excluded
from .health import health
from .resources import available
import contextvars
from .workspaces import workspaces
ARTICLE_VARIANT=contextvars.ContextVar("article_variant",default="zh-hans")

SourceError = SourceFailure
WIKIS = {"zhwiki":"https://zh.wikipedia.org","enwiki":"https://en.wikipedia.org"}
IMAGE_HOSTS = {"upload.wikimedia.org","thumb.wikimedia.org"}


def setting(name,default=""):
    key=next((k for k,v in ENV.items() if v==name),name)
    return preferences.values().get(key,default)


def entry_for(key):
    item=catalogue.get(key)
    if not item:raise SourceError("条目不存在。",code="not_found")
    return item


def source_url(entry,source):
    if source in WIKIS:
        title=entry.get("wiki",{}).get(source)
        return WIKIS[source]+"/wiki/"+quote(title.replace(" ","_")) if title else WIKIS[source]+"/w/index.php?search="+quote(entry.get("scientific") or entry["english"])
    if source=="baidu":return "https://baike.baidu.com/item/"+quote(entry.get("baidu") or entry["name"])
    if source=="wikidata" and entry.get("wikidata_id"):return "https://www.wikidata.org/wiki/"+entry["wikidata_id"]
    ref=entry.get("references",{}).get(source)
    if ref:return ref["url"]
    raise SourceError("此条目没有该来源。",code="not_found")


def sources_for(entry):
    result=[{"id":"auto","name":"自动 / Auto","kind":"auto","url":source_url(entry,"enwiki")}]
    for source,zh,en in [("zhwiki","中文维基","Chinese Wikipedia"),("enwiki","英文维基","English Wikipedia")]:
        available=bool(entry.get("wiki",{}).get(source))
        result.append({"id":source,"name":zh,"name_en":en,"kind":"api" if available else "search","available":available,"url":source_url(entry,source),"language":"zh" if source=="zhwiki" else "en"})
    if entry.get("wikidata_id"):
        result.append({"id":"wikidata","name":"Wikidata 名称资料","name_en":"Wikidata names","kind":"external","url":source_url(entry,"wikidata")})
    result.append({"id":"baidu","name":"百度百科","name_en":"Baidu Baike","kind":"external","url":source_url(entry,"baidu")})
    for key,ref in entry.get("references",{}).items():
        result.append({"id":key,"name":ref["name"],"name_en":ref.get("name_en",ref["name"]),"kind":"reference","url":ref["url"]})
    return result


def outbound_images(entry,form=None):
    chosen=next((f for f in entry["forms"] if f["id"]==form),entry["forms"][0])
    query=chosen.get("image_query") or entry.get("scientific") or entry["english"]
    q=quote(query)
    return {"query":query,
            "commons":"https://commons.wikimedia.org/w/index.php?search="+q+"&title=Special:MediaSearch&type=image",
            "baidu":"https://image.baidu.com/search/index?tn=baiduimage&word="+q,
            "bing":"https://www.bing.com/images/search?q="+q,
            "google":"https://www.google.com/search?tbm=isch&q="+q}


def select_images(entry,form,images):
    patterns={"parsley":r"parsley|petroselinum","coriander":r"coriander|coriandrum|cilantro","celery":r"celery|apium","dill":r"\bdill\b|anethum","basil":r"\bbasil\b|ocimum","oregano":r"oregano|origanum","thyme":r"thyme|thymus","rosemary":r"rosemary|rosmarin","cumin":r"\bcumin\b|cuminum","pepper":r"black pepper|peppercorn|piper nigrum","cinnamon":r"cinnam|canelle","clove":r"\bcloves?\b|syzygium aromaticum","paprika":r"paprika|red pepper powder"}
    rejected=re.compile(r"cow parsley|parsley hay|geograph|garlic cloves?|black cumin|health benefits|text labels|recalled|our lady|st cumin|blattläuse|itersonilia|cercosporidium|botrytis|befall|eristalinus",re.I)
    pattern=patterns.get(entry["id"])
    kept=[im for im in images if (not pattern or re.search(pattern,im["title"],re.I)) and not rejected.search(im["title"])]
    chosen=next((f for f in entry["forms"] if f["id"]==form),entry["forms"][0])
    preferred=[x.lower().replace("_"," ") for x in chosen.get("preferred_images",[])]
    def score(im):
        title=im["title"].lower().replace("_"," ")
        value=100-preferred.index(title) if title in preferred else 0
        if form in {"ground","flakes"} and re.search(r"ground|powder|dried|flakes",title):value+=15
        if form=="seed" and re.search(r"seed|whole",title):value+=15
        return value
    return sorted(kept,key=score,reverse=True)


async def request_json(url,params=None,**kwargs):
    return await fetch_json(url,params,**kwargs)


class Reader:
    def __init__(self,store=None):
        self.store=store or Store()
        self.locks={}

    def stored(self,key):
        found=self.store.get(key)
        return (found["value"],"cache",found["stale"]) if found else (None,None,False)

    def parse_article(self,entry,source,parsed,transport="backend"):
        canonical=WIKIS[source]+"/wiki/"+quote(parsed["title"].replace(" ","_"))
        raw=parsed.get("text","")
        if isinstance(raw,dict):raw=raw.get("*","")
        if not isinstance(raw,str) or len(raw)>8_000_000:
            raise SourceError("正文格式或大小无效。",code="invalid_content")
        revision=parsed.get("revid")
        content=article_content(raw,canonical,f"{entry['id']}-{source}-{revision or 'page'}")
        return {"mode":"article","entry_id":entry["id"],"source":source,
                "title":plain(parsed.get("displaytitle",parsed["title"])),"source_url":canonical,
                "language":"zh" if source=="zhwiki" else "en","variant":ARTICLE_VARIANT.get() if source=="zhwiki" else "en","page_id":parsed.get("pageid"),
                "revision_id":revision,"revision_url":WIKIS[source]+"/w/index.php?oldid="+str(revision) if revision else canonical,
                "fetched_at":now_iso(),"license":"CC BY-SA（以原页许可为准）",
                "license_url":"https://creativecommons.org/licenses/by-sa/4.0/",
                "authors_url":canonical+"?action=history","image_titles":parsed.get("images",[]),
                "scope_note":entry.get("scope_note",""),"transport":transport,
                "processing_note":"正文已清理并按原章节筛选；省略的章节或脚注跳转原站。 / Cleaned source text; omitted targets open the original page.",
                **content}

    async def article(self,entry_id,source="auto",refresh=False,preferred="zh"):
        item=entry_for(entry_id)
        from .wiki_languages import cached_mapping,mapped_entry,resolve_languages
        info=cached_mapping(item,self.store)
        if info:item=mapped_entry(item,info)
        wanted=("enwiki" if preferred=="en" else "zhwiki") if source=="auto" else source
        missing_wanted=wanted in WIKIS and not item.get("wiki",{}).get(wanted)
        if source in {"auto","zhwiki","enwiki"} and (not item.get("wiki") or not item.get("sources_resolved") and item.get("review_state")!="curated" or refresh and missing_wanted):
            item=await resolve_entry(entry_id,force=bool(refresh and missing_wanted))
        resolution=item.get("resolution_error")
        if source in {"auto","zhwiki","enwiki"} and resolution and not item.get("wiki"):
            raise SourceError("来源映射尚未完成，不能确认条目是否存在；请先检查连接。",code=resolution.get("code","network_error"),status=resolution.get("http_status"),host=resolution.get("host"),excerpt=resolution.get("response_excerpt",""))
        if source in {"auto","zhwiki","enwiki"} and not item.get("wiki",{}).get(wanted):
            item=mapped_entry(item,await resolve_languages(item,self.store,refresh))
        if source=="auto":
            first="enwiki" if preferred=="en" else "zhwiki"
            order=[s for s in [first,"zhwiki" if first=="enwiki" else "enwiki"] if item.get("wiki",{}).get(s)]
            if not order:
                return {"mode":"unavailable","source":"auto","title":item["name"],"source_url":item.get("references",{}).get("gbif",{}).get("url",source_url(item,"enwiki")),
                        "message":"尚未找到可核实的维基对应条目。可查看植物分类来源或搜索更多资料。","reason":"no_article","language":None}
            failures=[];old_result=None
            for candidate in order:
                try:
                    result=await self._article_one(item,candidate,refresh)
                    if result.get("warning"):
                        old_result=result;failures.append(result.get("diagnostic",{}));continue
                    if candidate!=first:
                        missing=first not in order and not resolution or bool(failures and failures[0].get("code") in {"missingtitle","missingpage","not_found"})
                        result["fallback"]={"preferred_source":first,"actual_source":candidate,"reason":"missing_language" if missing else "connection_failure"}
                    return result
                except SourceError as exc:failures.append(exc.public())
            if old_result:
                old_result["diagnostics"]=failures;return old_result
            raise SourceError("可用维基来源均未能连接；请运行设置中的来源诊断，或尝试浏览器官方 API。",code="all_sources_failed",excerpt=json.dumps(failures,ensure_ascii=False))
        if source in WIKIS:
            if not item.get("wiki",{}).get(source):
                return {"mode":"unavailable","source":source,"title":item["name"],"source_url":source_url(item,source),"message":"该语言暂未找到对应条目。请使用自动来源或另一种语言。","reason":"missing_language"}
            return await self._article_one(item,source,refresh)
        if source=="wikidata" or source=="baidu":
            return {"mode":"external","source":source,"source_url":source_url(item,source),"title":"Wikidata" if source=="wikidata" else "百度百科",
                    "message":"此来源在原站查看。 / Open this source on its own website."}
        ref=item.get("references",{}).get(source)
        if ref:
            return {"mode":"reference","source":source,"source_url":ref["url"],"title":ref["name"],"summary":ref["summary"],"fetched_at":ref.get("checked_at"),"delivery":"editorial","reference_links":ref.get("links",[]),"message":"资料说明与原站链接，并非自动抓取的全文。 / Source note and original link, not a retrieved full article."}
        raise SourceError("当前条目没有此来源。",code="not_found")

    async def _article_one(self,item,source,refresh):
        key=f"article:{item['id']}:{source}:"+(ARTICLE_VARIANT.get() if source=="zhwiki" else "en")
        old,delivery,stale=self.stored(key)
        if old and not stale and not refresh:return {**old,"delivery":delivery}
        async with self.locks.setdefault((workspaces.current_id,key),asyncio.Lock()):
            try:
                data=await request_json(WIKIS[source]+"/w/api.php",{"action":"parse","page":item["wiki"][source],"redirects":1,"prop":"text|tocdata|images|revid|displaytitle","variant":ARTICLE_VARIANT.get() if source=="zhwiki" else "en","disableeditsection":1,"format":"json","formatversion":2,"maxlag":5})
                if "parse" not in data:raise SourceError("来源没有正文。",code="not_found")
                value=await asyncio.to_thread(self.parse_article,item,source,data["parse"])
                self.store.put(key,value,900)
                return {**value,"delivery":"live"}
            except SourceError as exc:
                if old:return {**old,"delivery":"stale_cache","warning":str(exc),"diagnostic":exc.public()}
                raise

    def browser_article(self,entry_id,source,data):
        if source not in WIKIS or not isinstance(data,dict) or not isinstance(data.get("parse"),dict):
            raise SourceError("官方 API 响应格式不正确。",code="invalid_content")
        item=entry_for(entry_id)
        value=self.parse_article(item,source,data["parse"],"browser-cors")
        self.store.put(f"article:{entry_id}:{source}:"+(ARTICLE_VARIANT.get() if source=="zhwiki" else "en"),value,900)
        return {**value,"delivery":"live"}

    def commons_params(self,item,form,profile=None):
        selected=lexicon.form(item,form,profile)
        query=lexicon.queries(item,selected)["queries"][0]
        params={"action":"query","format":"json","formatversion":2,"generator":"search",
                "gsrnamespace":6,"gsrlimit":8,"gsrsearch":query+" filetype:bitmap",
                "prop":"imageinfo","iiprop":"url|size|mime|extmetadata|timestamp|sha1","iiurlwidth":800,
                "iiextmetadatalanguage":"zh-hans","maxlag":5,"origin":"*"}
        if selected["id"]=="overview" and item.get("primary_image"):
            for key in ["generator","gsrnamespace","gsrlimit","gsrsearch"]:params.pop(key,None)
            params["titles"]="File:"+item["primary_image"]
        return params

    def commons_plans(self,item,form,profile=None):
        selected=lexicon.form(item,form,profile);base=self.commons_params(item,form,profile);plans=[]
        if selected.get('preferred_images'):
            exact={k:v for k,v in base.items() if k not in {'generator','gsrnamespace','gsrlimit','gsrsearch'}}
            exact.update(titles='|'.join('File:'+title.removeprefix('File:') for title in selected['preferred_images'][:4]),redirects=1)
            plans.append(exact)
        for query in lexicon.queries(item,selected)["queries"]:
            value=dict(base)
            if "gsrsearch" in value:value["gsrsearch"]=query+" filetype:bitmap"
            if value not in plans:plans.append(value)
        return plans

    def normalize_images(self,item,form,data,profile=None):
        if not isinstance(data,dict):raise SourceError("图片 API 响应格式错误。",code="invalid_content")
        result=[]
        for page in sorted(data.get("query",{}).get("pages",[]),key=lambda p:p.get("index",999)):
            info=(page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in {"image/jpeg","image/png","image/webp"}:continue
            url=info.get("thumburl") or info.get("url")
            if not url or urlsplit(url).hostname not in IMAGE_HOSTS:continue
            meta=info.get("extmetadata",{})
            text=lambda k:plain(meta.get(k,{}).get("value",""))
            identifier=hashlib.sha256((page["title"]+url).encode()).hexdigest()[:24]
            image={"id":identifier,"title":page["title"].removeprefix("File:"),"thumbnail_url":url,"original_url":safe_url(info.get("url","")) or url,
                   "source_url":safe_url(info.get("descriptionurl","")) or "https://commons.wikimedia.org/wiki/"+quote(page["title"]),
                   "description":text("ImageDescription"),"author":text("Artist") or "See file page",
                   "credit":text("Credit"),"license":text("LicenseShortName") or "See file license",
                   "license_url":safe_url(meta.get("LicenseUrl",{}).get("value","")) or "",
                   "width":info.get("width"),"height":info.get("height"),"provider":"commons","review_state":"candidate"}
            self.store.put("image:"+identifier,image,2592000);result.append(image)
        chosen=lexicon.form(item,form,profile)
        return {"images":lexicon.rank(item,chosen,select_images(item,form,result)),"fetched_candidate_count":len(result),"has_more":"continue" in data}

    def image_delivery(self,value):
        mode=preferences.values()["image_mode"]
        images=[]
        for image in value.get("images",[]):
            image=dict(image)
            image["display_url"]="/api/media/"+image["id"] if mode=="proxy" and image.get("provider")=="commons" else image["thumbnail_url"]
            image["delivery_mode"]=mode
            images.append(image)
        return {**value,"images":images,"image_mode":mode}

    async def images(self,entry_id,provider="commons",form=None,refresh=False,profile=None):
        item=entry_for(entry_id);form=form or item["forms"][0]["id"]
        if form not in {f["id"] for f in item["forms"]}:raise SourceError("原料形态不存在。",code="not_found")
        gateways=outbound_images(item,form)
        if provider in {"bing","baidu"}:
            return {"mode":"external","provider":provider,"images":[],"gateways":gateways,"message":"可尝试来源视窗，或在原站打开搜索结果。 / Try the source window or open the search page."}
        if provider=="google" and not(setting("GOOGLE_API_KEY") and setting("GOOGLE_CSE_ID")):
            return {"mode":"needs_key","provider":provider,"images":[],"gateways":gateways,"message":"未配置可用的 Google 图片 API；原站可能禁止嵌入。 / Google API is not configured; its search page may block framing."}
        if provider not in {"commons","google"}:raise SourceError("图片来源不存在。",code="not_found")
        key=f"v4images:{entry_id}:{form}:{provider}:{profile or 'auto'}"
        old,_,stale=self.stored(key)
        if old and not stale and not refresh:return self.image_delivery({**old,"delivery":"cache"})
        try:
            if provider=="commons":
                pages=[]
                for params in self.commons_plans(item,form,profile):
                    raw=await request_json("https://commons.wikimedia.org/w/api.php",params);pages.extend(raw.get("query",{}).get("pages",[]))
                    partial={page.get('pageid',page.get('title')):page for page in pages}
                    if self.normalize_images(item,form,{'query':{'pages':list(partial.values())}},profile)['images']:break
                unique={page.get("pageid",page.get("title")):page for page in pages}
                value=self.normalize_images(item,form,{"query":{"pages":list(unique.values())}},profile)
            else:
                data=await request_json("https://customsearch.googleapis.com/customsearch/v1",{"key":setting("GOOGLE_API_KEY"),"cx":setting("GOOGLE_CSE_ID"),"q":gateways["query"],"searchType":"image","num":8,"safe":"active"})
                images=[]
                for row in data.get("items",[]):
                    info=row.get("image",{});original=safe_url(row.get("link",""));thumb=safe_url(info.get("thumbnailLink",""));context=safe_url(info.get("contextLink",""))
                    if original and thumb and context:
                        images.append({"id":hashlib.sha256(original.encode()).hexdigest()[:24],"title":row.get("title",""),"thumbnail_url":thumb,"original_url":original,"source_url":context,"description":row.get("snippet",""),"author":"See source page","license":"Check original license","license_url":"","provider":"google"})
                value={"images":images}
            value.update({"mode":"images","provider":provider,"fetched_at":now_iso(),"query":gateways["query"],"gateways":gateways})
            self.store.put(key,value,900)
            return self.image_delivery({**value,"delivery":"live"})
        except SourceError as exc:
            if old:return self.image_delivery({**old,"delivery":"stale_cache","warning":str(exc),"diagnostic":exc.public()})
            raise

    def browser_images(self,entry_id,form,data,profile=None):
        item=entry_for(entry_id)
        if form not in {f["id"] for f in item["forms"]}:raise SourceError("原料形态无效。",code="not_found")
        value=self.normalize_images(item,form,data,profile)
        value.update({"mode":"images","provider":"commons","fetched_at":now_iso(),"gateways":outbound_images(item,form),"transport":"browser-cors"})
        self.store.put(f"v4images:{entry_id}:{form}:commons:{profile or 'auto'}",value,900)
        return self.image_delivery({**value,"delivery":"live"})

    async def image_file(self,identifier):
        if not re.fullmatch(r"[a-f0-9]{24}",identifier):raise SourceError("图片标识无效。",code="not_found")
        saved=next((p for p in media_root().glob(identifier+".*") if p.suffix in {".jpg",".png",".webp"}),None)
        if saved:return saved
        record=self.store.get("image:"+identifier)
        if not record:raise SourceError("图片信息尚未获取。",code="not_found")
        url=record["value"]["thumbnail_url"]
        options=client_options(30);options["headers"]["Accept"]="image/*"
        async with httpx.AsyncClient(**options) as client:
            for _ in range(4):
                if urlsplit(url).scheme!="https" or urlsplit(url).hostname not in IMAGE_HOSTS:raise SourceError("图片地址不属于支持的维基服务。",code="invalid_url")
                async with client.stream("GET",url) as response:
                    if response.status_code in {301,302,303,307,308}:
                        url=urljoin(url,response.headers.get("location",""));continue
                    if response.status_code>=400:raise SourceError("图片服务拒绝请求；请尝试浏览器直连或打开文件页。",code="image_unavailable",status=response.status_code)
                    mime=response.headers.get("content-type","").split(";")[0]
                    suffix={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}.get(mime)
                    if not suffix:raise SourceError("暂不支持此图片格式。",code="invalid_content")
                    chunks=[];size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>8_000_000:raise SourceError("图片超过 8 MB。",code="too_large")
                        chunks.append(chunk)
                    path=media_root()/(identifier+suffix);tmp=media_root()/(identifier+".part")
                    tmp.write_bytes(b"".join(chunks));tmp.replace(path);return path
        raise SourceError("图片重定向次数过多。",code="network_error")

    async def model_models(self):
        p=preferences.values();base=p["lm_base_url"].rstrip("/")
        headers={"Authorization":"Bearer "+p["lm_api_key"]} if p["lm_api_key"] else {}
        try:
            async with httpx.AsyncClient(timeout=15,trust_env=False,headers=headers) as client:
                response=await client.get(base+"/models");response.raise_for_status()
                models=response.json().get("data",[])
            result={"ok":True,"base_url":base,"models":[{"id":m["id"]} for m in models if m.get("id")],"checked_at":now_iso()}
            preferences.model_test({"ok":bool(models),"base_url":base,"checked_at":result["checked_at"],"available_model_ids":[m["id"] for m in models if m.get("id")]})
            return result
        except (httpx.HTTPError,ValueError,KeyError):
            preferences.model_test({"ok":False,"base_url":base,"checked_at":now_iso()})
            raise SourceError("无法连接模型 API。请确认 LM Studio 已启动服务器、地址和认证设置正确。",code="model_unavailable") from None

    async def translate(self,entry_id,source,refresh=False,target="zh-Hans"):
        if target=="zh":target="zh-Hans"
        if source not in WIKIS or target not in TRANSLATION_LANGUAGES-{'auto'}:raise SourceError("Unsupported translation language",code="invalid_content")
        p=preferences.values();provider=p['translation_provider'];source_language=('zh-Hant' if ARTICLE_VARIANT.get()=='zh-hant' else 'zh-Hans') if source=='zhwiki' else 'en'
        if excluded(source_language,p['excluded_languages']) or source_language==target:return {'skipped':True,'reason':'excluded_language' if source_language!=target else 'same_language','blocks':[]}
        if provider=='off' or provider=='local' and not p['lm_enabled'] or provider in {'google','azure'} and not p[provider+'_translate_key']:raise SourceError('Configure a translation service in Settings',code='model_unavailable')
        if not health.report().get('services',{}).get('translation_'+provider,{}).get('ok',True):raise SourceError('Translation service is temporarily unavailable',code='model_unavailable')
        article=await self.article(entry_id,source,False);model=p['lm_model'];base=p['lm_base_url'];signature=hashlib.sha256((provider+'|'+base+'|'+model+'|'+target+'|'+source_language+'|links-v4').encode()).hexdigest()[:16]
        index=f"translation-v4:{entry_id}:{source}:{article.get('revision_id')}:{signature}"
        old=self.store.get(index)
        if old and not refresh:return {**old['value'],'delivery':'cache'}
        blocks=translation_blocks(article['focus_html'],limit=8)
        if not blocks:raise SourceError('No suitable paragraphs',code='no_paragraphs')
        try:
            if provider=='local':
                if not model:
                    options=await self.model_models()
                    if not options['models']:raise ValueError('No loaded model')
                    model=options['models'][0]['id']
                texts=await local_translate(blocks,target,p,model)
            else:model=provider;texts=await cloud_translate(provider,[b['text'] for b in blocks],target,p)
            pairs=[]
            for block,text in zip(blocks,texts):
                validate_numbers(block['text'],text);pairs.append({'id':block['id'],'original_html':block['html'],'translated_html':translated_html(text,block['links'])})
            result={'entry_id':entry_id,'source':source,'source_url':article['source_url'],'revision_id':article.get('revision_id'),'model':model,'provider':provider,'target_language':target,'created_at':now_iso(),'blocks':pairs,'label':'Machine translation · not human reviewed','scope':'Up to 8 focus paragraphs'}
            self.store.put(index,result,31536000)
            from .activity import activity
            activity.log('translation.complete',{'entry_id':entry_id,'provider':provider,'source':source,'target':target,'paragraphs':len(pairs)})
            return {**result,'delivery':'live'}
        except (httpx.HTTPError,ValueError,KeyError,TypeError):raise SourceError('Translation or number/link validation failed; original text remains available',code='translation_failed') from None


async def frame_capability(entry,provider,form=None,url=None):
    if provider not in {"bing","google","baidu"}:raise SourceError("Unsupported frame source",code="not_found")
    from .web_sources import frame_check
    return await frame_check(url or outbound_images(entry,form)[provider])
