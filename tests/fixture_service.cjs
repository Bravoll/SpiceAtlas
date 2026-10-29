/* Shared synthetic API fixture for DOM and managed browser QA. Not a production server. */
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
function createFixture(root){
 const packed=path.join(root,'tests/ui_fixtures.json.gz');
 const data=JSON.parse(fs.existsSync(packed)?zlib.gunzipSync(fs.readFileSync(packed)).toString('utf8'):fs.readFileSync(path.join(root,'tests/ui_fixtures.json'),'utf8'));
 const photos=fs.existsSync(path.join(root,'tests/live_image_metadata.json'))?JSON.parse(fs.readFileSync(path.join(root,'tests/live_image_metadata.json'),'utf8')):{};
 let prefs=structuredClone(data.settings),revision=1,googleOK=true,lastSaved=null,view={entry:'parsley'},active='fixture-version',favorites=[],history=[];
 const versions=[{id:active,name:'UI fixture · Initial collection',created_at:'2026-10-28T00:00:00Z',updated_at:'2026-10-28T00:00:00Z'}],notices=[];const requests=[];
 const health=()=>({phase:'ready',revision,services:Object.fromEntries(['zhwiki','enwiki','commons','bing','bing_cn','google','baidu','wikidata','gbif','baidu_images'].map(id=>[id,{id,ok:id==='google'?googleOK:true,backend_ok:true,kind:'api'}])),checked_at:'2026-10-28T00:00:00Z',interval_seconds:600,notifications:notices});
 function entry(id){if(!data.entries[id])throw new Error('Entry outside the synthetic QA sample: '+id);const value=structuredClone(data.entries[id]),chinese=(prefs.content_language==='auto'?prefs.ui_language:prefs.content_language).startsWith('zh');value.id=id;value.favorite=favorites.includes(id);const rows=value.sources.filter(s=>s.service!=='google'||googleOK);value.sources=[...rows.filter(s=>s.language===(chinese?'zh':'en')),...rows.filter(s=>s.language!==(chinese?'zh':'en'))].map(s=>({...s,primary:s.language===(chinese?'zh':'en')}));if(!googleOK)delete value.image_gateways.google;return value;}
 function respond(url,options={}){
  const u=new URL(url,'http://127.0.0.1:8765'),method=options.method||'GET',body=options.body?JSON.parse(options.body):{};requests.push({url:u.href,path:u.pathname,query:u.search,method,body});let result;
  if(u.hostname==='commons.wikimedia.org'){const image=photos.fresh?.images?.[0];result={query:{pages:image?[{pageid:42,title:'File:'+image.title,imageinfo:[{mime:'image/jpeg',url:image.original_url,thumburl:image.thumbnail_url,descriptionurl:image.source_url,extmetadata:{Artist:{value:image.author},LicenseShortName:{value:image.license}}}]}]:[]}};}
  else if(u.hostname.endsWith('wikipedia.org'))result={parse:{title:'Parsley',revid:1,text:'<p>Synthetic API test paragraph about parsley and botanical references.</p>'}};
  else if(u.pathname==='/api/settings'){if(method==='POST'){lastSaved=body;for(const [k,v] of Object.entries(body)){if(k.startsWith('clear_')){if(v)prefs['has_'+k.slice(6)]=false;}else if(k.endsWith('_key')){if(v)prefs['has_'+k]=true;}else prefs[k]=v;}prefs.translation_ready=prefs.lm_enabled||prefs.translation_provider==='google'&&prefs.has_google_translate_key||prefs.translation_provider==='azure'&&prefs.has_azure_translate_key;}result=prefs;}
  else if(u.pathname==='/api/settings/test-model'){prefs.model_ready=true;result={ok:true,models:[{id:'fixture-chat-model'}]};}
  else if(u.pathname==='/api/versions'){if(method==='POST'){const v={id:'version-'+versions.length,name:body.name,created_at:'2026-10-28T00:00:00Z',updated_at:'2026-10-28T00:00:00Z'};versions.push(v);result=v;}else result={active,versions,sort:'custom',direction:'asc',deleted:[]};}
  else if(u.pathname==='/api/versions/order'){if(body.order)versions.sort((a,b)=>body.order.indexOf(a.id)-body.order.indexOf(b.id));result={ok:true};}
  else if(u.pathname.startsWith('/api/versions/')){const [,key,action]=u.pathname.slice(5).split('/');if(action==='switch')active=key;result={active,versions,sort:'custom',direction:'asc',deleted:[]};}
  else if(u.pathname==='/api/view-state'){if(method==='POST')view=body;result=view;}
  else if(u.pathname==='/api/health')result=health();
  else if(u.pathname==='/api/browser-plan/health')result={probes:[{id:'commons',url:'https://commons.wikimedia.org/w/api.php',params:{action:'query',origin:'*'}}]};
  else if(u.pathname==='/api/health/browser'||u.pathname==='/api/settings/diagnostics')result=health();
  else if(u.pathname.startsWith('/api/notifications/')){notices.splice(notices.findIndex(n=>u.pathname.includes(n.id)),1);result={ok:true};}
  else if(u.pathname==='/api/catalog/random')result={id:u.searchParams.get('exclude')==='basil'?'coriander':'basil',scope:'culinary',eligible_count:92};
  else if(u.pathname.startsWith('/api/pronunciation/'))result={word:entry(u.pathname.split('/').at(-1)).english,variants:[{ipa:'/fixture/',region:'UK',audio_url:'',source_url:'https://example.org/ui-test'}],source_url:'https://example.org/ui-test',provider:'Synthetic pronunciation fixture'};
  else if(u.pathname==='/api/catalog'){if(u.searchParams.get('collection')==='favorites')result={...data.catalogue,entries:favorites.map(entry),total:favorites.length};else if(u.searchParams.get('q')){const q=u.searchParams.get('q').toLowerCase();const rows=Object.values(data.entries).filter(e=>JSON.stringify([e.name,e.english,e.aliases]).toLowerCase().includes(q));result={...data.catalogue,entries:rows,total:rows.length};}else result=u.searchParams.get('scope')==='botanical'?(data.botanical_pages?.[Math.floor(Number(u.searchParams.get('offset')||0)/30)]||data.botanical_next):data.catalogue;}
  else if(u.pathname==='/api/catalog/stats')result=data.catalogue.stats;
  else if(u.pathname==='/api/catalog/nodes')result=u.searchParams.get('parent')==='root-botanical'?data.tree_botanical:u.searchParams.get('parent')==='root-all'?data.tree_all:data.tree_culinary;
  else if(u.pathname.startsWith('/api/entry/'))result=entry(decodeURIComponent(u.pathname.split('/').at(-1)));
  else if(u.pathname.startsWith('/api/article/')){let source=(u.searchParams.get('source')||'auto').split(':')[0];if(source==='auto')source=entry('parsley').sources[0].id;result=data['article_'+source]||{mode:'external',title:source,source_url:'https://example.org/ui-test',message:'Synthetic source fixture'};}
  else if(u.pathname.startsWith('/api/browser-plan/images/'))result={url:'https://commons.wikimedia.org/w/api.php',params:{action:'query',gsrsearch:u.searchParams.get('form')==='fresh'?'Petroselinum crispum leaves':'parsley dried',origin:'*'},queries:[{action:'query',gsrsearch:u.searchParams.get('form')==='fresh'?'Petroselinum crispum leaves':'parsley dried',origin:'*'}]};
  else if(u.pathname==='/api/browser-ingest/images'||u.pathname.startsWith('/api/images/')){const form=body.form||u.searchParams.get('form')||'flakes',key=body.entry_id||decodeURIComponent(u.pathname.split('/').at(-1)),sample=key==='parsley'?(photos[form]||photos.fresh||{}):{};result={...sample,mode:'images',provider:'commons',images:sample.images||[],gateways:entry(key).image_gateways,image_mode:'direct'};if(u.searchParams.get('provider')&&u.searchParams.get('provider')!=='commons')result={...result,mode:'external',images:[]};}
  else if(u.pathname.startsWith('/api/browser-plan/article/'))result={url:'https://en.wikipedia.org/w/api.php',params:{action:'parse',origin:'*'}};
  else if(u.pathname==='/api/browser-ingest/article')result=data.article_enwiki;
  else if(u.pathname.startsWith('/api/history/')){const id=u.pathname.split('/').at(-1);if(!history.includes(id))history.unshift(id);result={ok:true};}
  else if(u.pathname.startsWith('/api/favorite/')){const id=u.pathname.split('/').at(-1);if(body.enabled&&!favorites.includes(id))favorites.push(id);else if(!body.enabled)favorites=favorites.filter(x=>x!==id);result={ok:true};}
  else if(u.pathname.startsWith('/api/collections/')){const kind=u.pathname.split('/')[3];result={rows:(kind==='favorites'?favorites:history).map(id=>({entry_id:id,entry:entry(id),added_at:'2026-10-28T00:00:00Z'}))};}
  else if(u.pathname==='/api/discovery/options')result=data.discovery_options;
  else if(u.pathname==='/api/image-vocabulary')result=data.vocabulary;
  else if(u.pathname==='/api/catalog/audit')result={rows:[],total:0};
  else if(u.pathname==='/api/logs')result={rows:[{id:1,at:'2026-10-28T00:00:00Z',action:'fixture.preview',details:{synthetic:true}}]};
  else if(u.pathname==='/api/jobs')result=data.jobs;
  else if(u.pathname.startsWith('/api/frame/'))result={can_try:true,url:'/tests/frame_fixture.html',synthetic:true};
  else if(u.pathname==='/api/translate')result={blocks:[{id:'1',original_html:'<p>Synthetic original.</p>',translated_html:'<p>测试译文。</p>'}],model:'Synthetic fixture'};
  else throw new Error('Unexpected fixture request '+u.pathname);
  return structuredClone(result);
 }
 return {respond,requests,get prefs(){return prefs;},get lastSaved(){return lastSaved;},changeHealth(){googleOK=!googleOK;revision++;notices.push({id:'notice-'+revision,created_at:'2026-10-28T00:00:00Z',details:{changes:[{service:'google',before:!googleOK,now:googleOK}]}});}};
}
module.exports={createFixture};
