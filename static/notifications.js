"use strict";
const noticeUi={open:false,phase:'closed',revision:0,timer:0,busy:false,items:[],dismissed:new Set(),effect:null,openedAt:0,pointer:null,frame:0,keyboard:false};
function bellFrames(){return [{opacity:0,transform:'translate(12px,-8px) scale(.93)'},{opacity:1,transform:'none'}];}
function setBellOpen(open){
 const root=$('notificationCentre'),panel=$('notificationDetails');
 if(!noticeUi.items.length)open=false;
 if(noticeUi.open===open&&noticeUi.phase!=='closing'&&noticeUi.phase!=='opening')return;
 if(noticeUi.open===open&&noticeUi.effect)return;
 const revision=++noticeUi.revision;noticeUi.open=open;noticeUi.phase=open?'opening':'closing';
 if(open)noticeUi.openedAt=Date.now();
 root.dataset.expanded='true';root.dataset.noticePhase=noticeUi.phase;panel.hidden=false;
 $('notificationToggle').setAttribute('aria-expanded',String(open));
 $('notificationToggle').setAttribute('aria-label',open?t('dismissCurrentNotice'):t('notificationSummary',{count:noticeUi.items.length}));
 panel.setAttribute('aria-hidden',String(!open));
 const finish=()=>{if(revision!==noticeUi.revision)return;noticeUi.effect?.cancel();noticeUi.effect=null;noticeUi.phase=open?'open':'closed';root.dataset.noticePhase=noticeUi.phase;root.dataset.expanded=String(open);panel.hidden=!open;if(!noticeUi.items.length)root.hidden=true;};
 if(!motionLevel()||!panel.animate){finish();return;}
 let effect=noticeUi.effect;
 if(effect&&effect.playState==='running'&&typeof effect.reverse==='function')effect.reverse();
 else{
  effect?.cancel();effect=panel.animate(bellFrames(),{duration:[0,100,210,330][motionLevel()],easing:'cubic-bezier(.16,1,.3,1)',fill:'both'});
  if(!open){effect.currentTime=[0,100,210,330][motionLevel()];effect.reverse?.();}
  noticeUi.effect=effect;trackMotion(effect);
 }
 effect.finished.catch(()=>{}).then(finish);
}
function noticeTitle(item){return t(({'service.pausing':'servicePausingTitle','service.paused':'servicePausedTitle','service.resumed':'serviceResumedTitle'})[item.details?.kind]||(item.details?.changes?'healthChanged':'importantNotice'));}
function noticeMarkup(item){
 const details=item.details||{};let body='';
 if(details.changes)body='<ul>'+details.changes.map(row=>'<li><strong>'+esc(row.service)+'</strong> '+esc(t(row.now?'serviceRecovered':'serviceDisabled'))+(row.http_status?' · HTTP '+esc(row.http_status):'')+(row.message?'<small>'+esc(row.message)+'</small>':'')+'</li>').join('')+'</ul><p>'+esc(t('refreshPending'))+'</p>';
 else if(details.kind?.startsWith('service.'))body='<p>'+esc(t(details.kind==='service.resumed'?'serviceResumedBody':details.kind==='service.pausing'?'servicePausingBody':'servicePausedBody'))+'</p>';
 else body='<p>'+esc(item.title||'')+'</p>'+(details.message?'<p>'+esc(details.message)+'</p>':'');
 if(details.action==='retest')body+='<button type="button" class="notice-action" data-notice-action="retest">'+esc(t('retestConnections'))+'</button>';
 return '<button type="button" class="notice-card-close" data-dismiss="'+esc(item.id)+'" aria-label="'+esc(t('dismiss'))+'">×</button><h3>'+esc(noticeTitle(item))+'</h3><time>'+esc(formatDate(item.created_at))+'</time>'+body;
}
function paintNotifications(){
 const root=$('notificationCentre'),panel=$('notificationDetails'),items=(state.health?.notifications||[]).filter(n=>!noticeUi.dismissed.has(n.id));
 noticeUi.items=items;if(items.length)root.hidden=false;$('notificationCount').textContent=String(items.length);$('notificationToggle').disabled=noticeUi.busy;
 const old=new Map(Array.from(panel.children).map(card=>[card.dataset.noticeId,card]));
 for(const item of items){
  let card=old.get(item.id);if(!card){card=document.createElement('article');card.className='notice-card';card.dataset.noticeId=item.id;}
  const signature=state.locale+JSON.stringify(item.details||{});
  if(card.dataset.signature!==signature){card.dataset.signature=signature;card.innerHTML=noticeMarkup(item);card.querySelector('[data-dismiss]').addEventListener('click',()=>dismissBellNotice(item.id));card.querySelector('[data-notice-action]')?.addEventListener('click',event=>retestFromNotice(event.currentTarget));}
  panel.appendChild(card);old.delete(item.id);
 }
 for(const card of old.values())card.remove();
 if(!items.length){if(noticeUi.phase!=='closed')setBellOpen(false);else{root.hidden=true;panel.hidden=true;}}
 $('notificationToggle').setAttribute('aria-expanded',String(noticeUi.open));$('notificationToggle').setAttribute('aria-label',noticeUi.open?t('dismissCurrentNotice'):t('notificationSummary',{count:items.length}));
}
async function retestFromNotice(button){
 button.disabled=true;button.textContent=t('diagnosing');
 try{await beginHealthCycle(true);button.textContent=t('retestStarted');applyRuntimeState({phase:'running',paused:false,needs_retest:false});}
 catch(error){button.disabled=false;button.textContent=t('retestConnections');showNotice('globalMessage',errorMessage(error));}
}
async function dismissBellNotice(id=noticeUi.items[0]?.id){
 if(!id||noticeUi.busy)return;noticeUi.busy=true;$('notificationToggle').disabled=true;
 const card=Array.from($('notificationDetails').children).find(x=>x.dataset.noticeId===id),before=new Map(Array.from($('notificationDetails').children).map(x=>[x.dataset.noticeId,x.getBoundingClientRect()]));
 try{
  await post('/api/notifications/'+encodeURIComponent(id)+'/dismiss');noticeUi.dismissed.add(id);
  const effect=motionEffect(card,bellFrames().slice().reverse(),[0,90,170,240][motionLevel()]);if(effect)await effect.finished.catch(()=>{});
  state.health.notifications=(state.health.notifications||[]).filter(n=>n.id!==id);paintNotifications();
  if(motionLevel())for(const item of $('notificationDetails').children){const a=before.get(item.dataset.noticeId),b=item.getBoundingClientRect();if(a&&a.top!==b.top)motionEffect(item,[{transform:`translateY(${a.top-b.top}px)`},{transform:'none'}],motionLevel()===3?330:150);}
 }catch(error){showNotice('globalMessage',errorMessage(error));}
 finally{noticeUi.busy=false;$('notificationToggle').disabled=false;}
}
function noticeHit(x,y){
 const orb=$('notificationToggle').getBoundingClientRect(),radius=orb.width/2,pad=radius/2;
 if(noticeUi.phase==='closed')return Math.hypot(x-(orb.left+radius),y-(orb.top+radius))<=radius+pad;
 const panel=$('notificationDetails').getBoundingClientRect();
 return x>=Math.min(orb.left,panel.left)-pad&&x<=Math.max(orb.right,panel.right)+pad&&y>=Math.min(orb.top,panel.top)-pad&&y<=Math.max(orb.bottom,panel.bottom)+pad;
}
function checkNoticePointer(){
 noticeUi.frame=0;if(!noticeUi.items.length||!noticeUi.pointer)return;
 const {x,y}=noticeUi.pointer,inside=noticeHit(x,y);
 if(inside){clearTimeout(noticeUi.timer);if(!noticeUi.open)setBellOpen(true);}
 else if(noticeUi.open&&!(noticeUi.keyboard&&$('notificationCentre').contains(document.activeElement)))setBellOpen(false);
}
function setupNotificationBell(){
 const root=$('notificationCentre'),button=$('notificationToggle');
 document.addEventListener('pointermove',event=>{if(event.pointerType&&event.pointerType!=='mouse')return;noticeUi.pointer={x:event.clientX,y:event.clientY};if(!noticeUi.frame)noticeUi.frame=requestAnimationFrame(checkNoticePointer);},{passive:true});
 root.addEventListener('pointerenter',event=>{if(!event.pointerType||event.pointerType==='mouse')setBellOpen(true);});
 document.addEventListener('keydown',event=>{if(event.key==='Tab')noticeUi.keyboard=true;});
 root.addEventListener('focusin',()=>clearTimeout(noticeUi.timer));root.addEventListener('focusout',()=>{noticeUi.timer=setTimeout(checkNoticePointer,40);});
 button.addEventListener('click',event=>{if(!noticeUi.open||event.detail>0&&Date.now()-noticeUi.openedAt<350)setBellOpen(true);else dismissBellNotice();});
 document.addEventListener('pointerdown',event=>{noticeUi.keyboard=false;if(noticeUi.open&&!root.contains(event.target)&&!noticeHit(event.clientX,event.clientY))setBellOpen(false);});
 window.addEventListener('resize',()=>{if(noticeUi.open)checkNoticePointer();});
}
let runtimePollTimer=0,runtimeEvents=null;
function traceUiEvent(action,details={}){post('/api/ui-events',{action,...details}).catch(()=>{});}
function applyRuntimeState(data){
 const was=state.runtimePaused;state.runtimePaused=!!data.paused;state.runtimeNeedsRetest=!!data.needs_retest;
 $('runtimeState').hidden=!data.paused&&data.phase!=='pausing'&&!data.needs_retest;$('runtimeState').textContent=t(data.phase==='pausing'?'servicePausingTitle':data.paused?'servicePaused':'retestConnections');
 if(data.paused){if(typeof otherUi!=='undefined'&&otherUi.controller)stopOtherSources();if(typeof pausePrefetch==='function')pausePrefetch();}
 if(data.version&&state.version&&data.version!==state.version)return;
 const notices=data.notifications||[];if(data.notification)notices.unshift(data.notification);
 if(notices.length){state.health=state.health||{};const map=new Map((state.health.notifications||[]).map(x=>[x.id,x]));notices.forEach(x=>{if(!noticeUi.dismissed.has(x.id))map.set(x.id,x);});state.health.notifications=[...map.values()];paintNotifications();}
 if(data.notification&&data.kind!=='snapshot')setBellOpen(true);
 if(was&&!data.paused&&state.bootstrapPaused)location.reload();
}
async function checkRuntimeState(){try{applyRuntimeState(await api('/api/status'));}catch{}}
function setupRuntimeEvents(){
 document.addEventListener('click',event=>{const button=event.target.closest?.('button');if(button)traceUiEvent('click',{control:button.id||button.dataset.source||button.dataset.provider||button.dataset.entry||'button',entry:state.id});});
 document.addEventListener('change',event=>{if(event.target.id)traceUiEvent('change',{control:event.target.id,entry:state.id});});
 if(window.PerformanceObserver){try{const observer=new window.PerformanceObserver(list=>{for(const row of list.getEntries()){try{const url=new URL(row.name);if(url.origin!==location.origin)traceUiEvent('browser.resource',{provider:url.hostname,control:row.initiatorType+' '+Math.round(row.duration)+' ms'});}catch{}}});observer.observe({entryTypes:['resource']});}catch{}}
 if(window.EventSource){runtimeEvents=new window.EventSource('/api/runtime/events');runtimeEvents.onmessage=event=>{try{applyRuntimeState(JSON.parse(event.data));}catch{}};window.addEventListener('pagehide',()=>runtimeEvents.close());}
 checkRuntimeState();runtimePollTimer=setInterval(checkRuntimeState,3000);
}
