const assert=require('node:assert/strict');const {boot,until,delay}=require('./interaction_harness.cjs');
const errors=[];process.on('unhandledRejection',error=>errors.push(String(error)));
(async()=>{
 let cached=false,cachedArticleValue=null,cachedImagesValue=null;const h=boot({fetch:async(url,options,fixture)=>{
  const u=new URL(url,'http://127.0.0.1');
  if(u.hostname==='fast-probe.example')return {ok:true,json:async()=>({})};
  if(u.hostname==='slow-probe.example')return await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('deadline')),{once:true}));
  const base=fixture.respond(url,options);if(u.pathname.startsWith('/api/article/'))cachedArticleValue=base;if(u.pathname==='/api/browser-ingest/images'||u.pathname.startsWith('/api/images/'))cachedImagesValue=base;
  if(u.pathname==='/api/catalog/nodes'){
   const total=19,offset=Number(u.searchParams.get('offset')||0),limit=Number(u.searchParams.get('limit')||6);
   return {ok:true,status:200,json:async()=>({...base,total,offset,limit,has_more:offset+limit<total,nodes:Array.from({length:Math.min(limit,total-offset)},(_,i)=>({id:'subset-'+(offset+i),label:'Subset '+(offset+i),label_hant:'子集 '+(offset+i),child_count:2,entry_count:20}))})};
  }
  if(cached&&u.pathname==='/api/cache/lookup'&&!JSON.parse(options.body).track_only){const resource=JSON.parse(options.body).resource;
   if(resource.kind==='article')return {ok:true,status:200,json:async()=>({hit:true,tier:'retained',value:{...cachedArticleValue,delivery:'retained_cache'}})};
   if(resource.kind==='images')return {ok:true,status:200,json:async()=>({hit:true,tier:'memory',value:{...cachedImagesValue,delivery:'memory_cache'}})};
  }
  return {ok:true,status:200,json:async()=>base};
 }});
 await until(()=>h.run('!state.restoring&&!!state.entry'),'bootstrap');await delay(20);
 assert.equal(h.el('manageCatalogue'),null);assert.ok(h.document.querySelector('[data-settings-tab="catalogue"]'));
 assert.equal(h.el('treePrevious').disabled,true);const operationCount=()=>h.fixture.requests.filter(r=>r.path==='/api/cache/operation').length,beforeLocal=operationCount();
 h.key(']');await until(()=>h.run('catalogNav.treeOffset===6&&!catalogNav.treeBusy'),'next subset page');assert.ok(h.el('treePage').textContent.includes('7–12 / 19'));assert.equal(h.el('catalogTreeViewport').scrollTop,0);
 h.key('[');await until(()=>h.run('catalogNav.treeOffset===0&&!catalogNav.treeBusy'),'previous subset page');
 h.key('.');await until(()=>h.run('state.offset===30&&!repeatState.running'),'next entry page');h.key(',');await until(()=>h.run('state.offset===0&&!repeatState.running'),'previous entry page');assert.equal(operationCount(),beforeLocal);
 const input=h.el('search');h.key(']',input);h.key('.',input);h.key(']',h.document.body,{isComposing:true});h.key('.',h.document.body,{ctrlKey:true});await delay(10);assert.equal(h.run('catalogNav.treeOffset'),0);assert.equal(h.run('state.offset'),0);
 await h.run("openSettings('cache')");assert.equal(h.el('shortcutTreePrevious').value,'[');assert.equal(h.el('cacheWeightRecent').value,'0.5');
 for(const [id,value] of [['shortcutTreePrevious','h'],['shortcutTreeNext','j'],['shortcutEntryPrevious','k'],['shortcutEntryNext','l']])h.el(id).value=value;
 await h.run('savePrefs(false)');assert.equal(h.fixture.prefs.shortcuts.tree_next,'j');assert.ok(h.el('treeNext').title.endsWith('j'));h.key('Escape');await until(()=>!h.el('settingsDialog').open,'settings close');
 h.key(']');await delay(10);assert.equal(h.run('catalogNav.treeOffset'),0);h.key('j');await until(()=>h.run('catalogNav.treeOffset===6&&!catalogNav.treeBusy'),'custom subset shortcut');h.key('l');await until(()=>h.run('state.offset===30&&!repeatState.running'),'custom entry shortcut');
 // Hover locks the actual controls, then releases into an animated layout correction.
 const bar=h.el('entryPager'),button=h.el('catalogNext');let flowingTop=180;
 bar.getBoundingClientRect=function(){const top=this.dataset.pointerHeld?parseFloat(this.style.top):flowingTop;return {x:0,y:top,left:0,top,right:200,bottom:top+34,width:200,height:34};};
 const enter=new h.window.Event('pointerenter');enter.pointerType='mouse';bar.dispatchEvent(enter);assert.equal(bar.dataset.pointerHeld,'true');assert.equal(bar.style.bottom,'auto');assert.equal(bar.style.height,'34px');flowingTop=260;assert.equal(bar.getBoundingClientRect().top,180);assert.equal(h.el('catalogNext'),button);
 bar.dispatchEvent(new h.window.Event('pointerleave'));assert.equal(bar.hasAttribute('data-pointer-held'),false);assert.equal(bar.getBoundingClientRect().top,260);assert.ok(h.motion.effects.some(effect=>effect.element===bar&&String(effect.frames[0].transform).includes('-80px')));
 // Cached remote material returns before either live transport; refresh still records the packet.
 cached=true;const articleRequests=h.fixture.requests.filter(x=>x.path.startsWith('/api/article/')).length;
 await h.run("act({type:'source',source:'enwiki:en'})");assert.equal(h.fixture.requests.filter(x=>x.path.startsWith('/api/article/')).length,articleRequests);assert.equal(h.run('state.article.delivery'),'retained_cache');
 const directImages=()=>h.fixture.requests.filter(x=>x.url.includes('commons.wikimedia.org/w/api.php')).length,imagesBefore=directImages();await h.run("act({type:'form',form:'fresh'})");assert.equal(directImages(),imagesBefore);
 await h.run("cachedResource({kind:'article',entry:'parsley',source:'enwiki'},true)");assert.equal(h.fixture.requests.filter(x=>x.path==='/api/cache/lookup').at(-1).body.track_only,true);
 // Halo is 1.5 radii; expanded retention includes all four edges plus half a radius.
 h.fixture.changeHealth();await h.run("(async()=>{state.health=await api('/api/health');paintNotifications()})()");
 h.el('notificationToggle').getBoundingClientRect=()=>({left:1295,right:1341,top:114,bottom:160,width:46,height:46});h.el('notificationDetails').getBoundingClientRect=()=>({left:967,right:1341,top:114,bottom:414,width:374,height:300});
 assert.equal(h.run('noticeHit(1318,104)'),true);assert.equal(h.run('noticeHit(1318,101)'),false);
 const pointer=(x,y)=>{const event=new h.window.Event('pointermove');Object.assign(event,{pointerType:'mouse',clientX:x,clientY:y});h.document.dispatchEvent(event);};
 pointer(1318,104);await until(()=>h.run("noticeUi.phase==='open'"),'expanded before touching bell');assert.equal(h.run('noticeHit(959,420)'),true);assert.equal(h.run('noticeHit(952,420)'),false);
 const dismissBefore=h.fixture.requests.filter(x=>x.path.includes('/dismiss')).length;const click=new h.window.Event('click');click.detail=1;h.el('notificationToggle').dispatchEvent(click);await delay(10);assert.equal(h.fixture.requests.filter(x=>x.path.includes('/dismiss')).length,dismissBefore);
 h.motion.auto=false;pointer(940,450);await until(()=>h.run("noticeUi.phase==='closing'"),'collapse started');assert.equal(h.el('notificationDetails').hidden,false);
 pointer(1000,200);await until(()=>h.run("noticeUi.phase==='opening'"),'collapse reversed');for(const effect of h.motion.effects)if(effect.playState==='running')effect.finish();await until(()=>h.run("noticeUi.phase==='open'"),'reversed open completes');h.motion.auto=true;
 pointer(940,450);await until(()=>h.el('notificationDetails').hidden,'collapse animation completes');
 // Service transitions are general notices and retest is a deliberate user action.
 h.run("applyRuntimeState({kind:'service.pausing',phase:'pausing',paused:false,notification:{id:'service-a',created_at:'2026-10-29T00:00:00Z',details:{kind:'service.pausing'}}})");assert.equal(h.run('state.runtimePaused'),false);assert.ok(h.el('notificationDetails').textContent.includes('preparing to pause'));
 h.run("applyRuntimeState({kind:'service.paused',phase:'paused',paused:true,notification:{id:'service-a',created_at:'2026-10-29T00:00:00Z',details:{kind:'service.paused'}}})");assert.equal(h.run('state.runtimePaused'),true);assert.ok(h.el('notificationDetails').textContent.includes('Service paused'));
 h.run("applyRuntimeState({kind:'service.resumed',phase:'running',paused:false,needs_retest:true,notification:{id:'service-b',created_at:'2026-10-29T00:00:01Z',details:{kind:'service.resumed',action:'retest'}}})");
 const writes=h.fixture.requests.filter(x=>x.path==='/api/settings'&&x.method==='POST').length;h.el('notificationDetails').querySelector('[data-notice-action="retest"]').click();await until(()=>h.fixture.requests.some(x=>x.path==='/api/settings/diagnostics'),'manual retest');assert.equal(h.fixture.requests.filter(x=>x.path==='/api/settings'&&x.method==='POST').length,writes);
 // One slow probe cannot withhold an already completed browser success.
 const healthBefore=h.fixture.requests.filter(x=>x.path==='/api/health/browser').length;
 await h.run("browserHealth({round_id:'independent-probes',remaining_ms:30,probes:[{id:'enwiki',url:'https://fast-probe.example/api',params:{}},{id:'commons',url:'https://slow-probe.example/api',params:{}}]})");
 const probeRows=h.fixture.requests.filter(x=>x.path==='/api/health/browser').slice(healthBefore);assert.equal(probeRows.length,1);assert.equal(probeRows[0].body.results[0].id,'enwiki');assert.equal(probeRows[0].body.results[0].ok,true);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,checks:['catalogue management is settings-only','bracket keys page subcategories with stable path position','comma/period keys page entries','local paging does not train remote predictor','inputs IME and modifiers protect new shortcuts','cache and shortcut controls retain configured values','custom keys replace defaults','pointer-held pager retains controls across layout movement','pager release animates correction','retained article skips backend source read','memory images skip browser live request','manual refresh still counts its remote packet','bell opens within expanded circular halo','expanded hit region includes half-radius padding on every edge','fast approach click does not dismiss notice','collapse waits for exit animation','collapse can reverse without stale callbacks','pre-pause and paused notices update same card','resume offers manual retest without settings writes','fast browser probe posts before slow sibling deadline']}));process.exit(0);
})().catch(error=>{console.error(error.stack);console.error(errors);process.exit(1);});
