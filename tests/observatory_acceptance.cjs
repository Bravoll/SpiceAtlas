/* v0.7 contracts: streamed text, cancellation, stable notification controls and motion. */
const assert=require('node:assert/strict');
const {boot,until,delay}=require('./interaction_harness.cjs');
const {otherEvents}=require('./fixture_service.cjs');
const errors=[];process.on('unhandledRejection',error=>errors.push(String(error)));
function streamed(events){
 const bytes=new TextEncoder().encode(events.map(x=>JSON.stringify(x)).join('\n'));
 let offset=0;
 return {ok:true,status:200,body:new ReadableStream({pull(controller){if(offset===bytes.length){controller.close();return;}const end=Math.min(offset+7,bytes.length);controller.enqueue(bytes.slice(offset,end));offset=end;}})};
}
(async()=>{
 let streamMode='normal',releaseLate,probeAborted=false;const signals=[];
 const h=boot({fetch:async(url,options,fixture)=>{
  const u=new URL(url,'http://127.0.0.1');
  if(u.pathname.includes('/other-sources/')&&u.pathname.endsWith('/stream')){
   signals.push(options.signal);
   if(streamMode==='late')return await new Promise(resolve=>{releaseLate=()=>resolve(streamed(otherEvents('old-entry')));});
   return streamed(otherEvents(u.pathname.split('/')[3]));
  }
  if(u.hostname==='late-probe.example')return await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{probeAborted=true;reject(new Error('aborted'));},{once:true}));
  return {ok:true,status:200,json:async()=>fixture.respond(url,options)};
 }});
 await until(()=>h.run('!state.restoring&&!!state.entry'),'bootstrap');await delay(20);
 assert.ok(h.el('sourceTabs').querySelector('[data-source="other"]'));
 await h.run("act({type:'source',source:'other'})");
 assert.equal(h.el('otherSourcesBoard').hidden,false);assert.equal(h.document.querySelector('.reader-shell').hidden,true);
 const cards=[...h.el('otherSourcesRail').children];assert.equal(cards.length,3);
 assert.deepEqual(cards.map(x=>x.querySelector('.other-arrival').textContent.split(' · ')[0]),['1','2','3']);
 assert.ok(cards[0].textContent.includes('中文内容用于检查流式 UTF-8 解码'));assert.ok(!cards[0].textContent.includes('�'));
 assert.equal(h.el('otherSourcesStop').disabled,true);assert.ok(h.el('otherSourcesStatus').textContent.includes('3'));
 assert.equal(cards[0].querySelector('.other-body a').getAttribute('rel'),'noopener noreferrer');assert.ok(cards[0].querySelector('.other-outline a').getAttribute('href').startsWith('#fixture-'));
 // A late response from a stopped entry must not appear in the new reader.
 streamMode='late';const pending=h.run('loadOtherSources()');await until(()=>!!releaseLate,'pending stream');
 h.run('stopOtherSources(true)');assert.equal(signals.at(-1).aborted,true);releaseLate();await pending;
 assert.equal(h.el('otherSourcesRail').children.length,0);assert.equal(h.el('otherSourcesBoard').hidden,true);
 streamMode='normal';await h.run("act({type:'source',source:'enwiki:en'})");assert.equal(h.document.querySelector('.reader-shell').hidden,false);
 // The same orb is retained while first-card dismissal advances the queue.
 h.fixture.changeHealth();h.fixture.changeHealth();await h.run("(async()=>{state.health=await api('/api/health');paintNotifications()})()");
 const orb=h.el('notificationToggle'),root=h.el('notificationCentre');assert.equal(h.el('notificationCount').textContent,'2');assert.equal(root.hidden,false);
 const enter=new h.window.Event('pointerenter');enter.pointerType='mouse';root.dispatchEvent(enter);assert.equal(orb.getAttribute('aria-expanded'),'true');
 const first=h.el('notificationDetails').firstElementChild.dataset.noticeId;orb.click();
 await until(()=>h.el('notificationCount').textContent==='1'&&!h.run('noticeUi.busy'),'first notice dismissed');
 assert.equal(h.el('notificationToggle'),orb);assert.notEqual(h.el('notificationDetails').firstElementChild.dataset.noticeId,first);assert.equal(root.dataset.expanded,'true');
 h.run("state.health.notifications.unshift({id:'"+first+"',created_at:'2026-10-29T00:00:00Z',details:{changes:[]}});paintNotifications()");assert.equal(h.el('notificationCount').textContent,'1');
 orb.click();await until(()=>root.hidden,'all notices dismissed');assert.equal(h.el('notificationToggle'),orb);
 // Language and source replacement have distinct art effects, with immediate level-0 cleanup.
 h.run("state.prefs.animation_level=3;applyReadingPreferences();beginInkChange('language');revealInkText($('entryName'),'language')");
 assert.ok(h.motion.effects.some(x=>x.frames[0].transform?.includes('rotateX')));assert.equal(h.document.querySelectorAll('.ink-veil').length,0);
 h.run("$('articleBody').innerHTML='<h2>Botanical notes</h2><p>Short source text.</p>';beginInkChange('source');revealInkText($('articleBody'))");assert.ok(h.motion.effects.some(x=>x.frames[0].transform==='translateY(2px)'));assert.ok(!h.motion.effects.some(x=>x.element===h.el('articleBody')&&x.frames[0].clipPath));
 assert.ok(h.run("inkWords('欧芹与植物图鉴').length")>1);
 h.run('state.prefs.animation_level=0;applyReadingPreferences()');assert.equal(h.document.querySelectorAll('.ink-veil').length,0);assert.equal(h.run('inkMotion.kind'),null);
 h.run('state.prefs.animation_level=3;applyReadingPreferences()');await h.run("act({type:'language',language:'zh-Hant'})");assert.equal(h.document.documentElement.lang,'zh-Hant');assert.equal(h.run('inkMotion.kind'),null);
 // Browser probes share the server deadline and never post a late recovery.
 const before=h.fixture.requests.filter(x=>x.path==='/api/health/browser').length;
 await h.run("browserHealth({round_id:'short-round',remaining_ms:25,probes:[{id:'commons',url:'https://late-probe.example/api',params:{}}]})");
 assert.equal(probeAborted,true);assert.equal(h.fixture.requests.filter(x=>x.path==='/api/health/browser').length,before);
 // The terminal bridge records identifiers, never search contents or settings values.
 h.run("traceUiEvent('change',{control:'modelKey',entry:'parsley'})");await delay(5);
 const trace=h.fixture.requests.filter(x=>x.path==='/api/ui-events').at(-1);assert.equal(trace.body.control,'modelKey');assert.equal(Object.hasOwn(trace.body,'value'),false);assert.equal(Object.hasOwn(trace.body,'query'),false);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,checks:['Other sources available in local entry plan','NDJSON cards retain completion order','UTF-8 split across chunks and final unterminated line','source links and internal outline retained','stop aborts stream and rejects stale entry data','Wiki reader restored after source switch','hover expands notification queue','same orb dismisses first card and advances next','stale health poll cannot resurrect dismissed notice','last dismissal hides orb without replacing it','bounded language and source word effects have distinct frames','level 0 clears text overlays immediately','language transition ends without replay state','browser deadline aborts and rejects late recovery','terminal bridge excludes entered values']}));process.exit(0);
})().catch(error=>{console.error(error.stack);console.error(errors);process.exit(1);});
