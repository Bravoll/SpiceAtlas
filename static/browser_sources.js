"use strict";
/* A normal page cannot call extension-only tabs APIs. Use an explicit local bridge. */
const browserSources={connected:false,nativeSplit:false,pending:new Map(),url:null};
function browserIdentity(){const agent=navigator.userAgent||'';const edge=agent.match(/Edg\/(\d+)/),chrome=agent.match(/Chrome\/(\d+)/);return edge?'Edge '+edge[1]:chrome?'Chrome '+chrome[1]:t('browserOther');}
function safeSearchPage(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&(['www.google.com','google.com'].includes(u.hostname)&&u.pathname==='/search'||['www.bing.com','cn.bing.com'].includes(u.hostname)&&u.pathname.startsWith('/images/search')||u.hostname==='image.baidu.com'&&u.pathname==='/search/index')?u.href:null;}catch{return null;}}
function browserHelperRequest(action,url){
 if(typeof window.postMessage!=='function')return Promise.resolve({ok:false,code:'helper_unavailable'});
 const id=resourceEventId();return new Promise(resolve=>{const timer=setTimeout(()=>{browserSources.pending.delete(id);resolve({ok:false,code:'helper_unavailable'});},2200);browserSources.pending.set(id,{resolve,timer});window.postMessage({channel:'SPICE_ATLAS_BROWSER_REQUEST',id,action,url},new URL(location.href).origin);});
}
function renderBrowserCapability(){
 $('browserSourceCapability').textContent=browserIdentity()+' · '+t(browserSources.nativeSplit?'splitHelperReady':browserSources.connected?'splitApiMissing':'splitHelperMissing');
 $('openSourceSplit').textContent=t(browserSources.nativeSplit?'openNativeSplit':'splitHelp');
}
function renderImageQuery(data={}){
 let query=data.query||data.gateways?.query||'';const url=data.source_url||data.gateways?.[state.imageProvider]||state.entry?.image_gateways?.[state.imageProvider];
 if(!query&&url)try{const p=new URL(url).searchParams;query=p.get('q')||p.get('word')||p.get('search')||'';}catch{}
 $('imageQuery').textContent=query;$('imageQuery').parentElement.hidden=!query;
}
async function offerBrowserSource(result,epoch){
 const url=safeSearchPage(result.url);if(!url||epoch!==state.frameEpoch)return;
 browserSources.url=url;$('openSourceTab').href=url;$('browserSourceFallback').hidden=false;
 if(!state.currentImages?.length)$('imageGrid').replaceChildren();
 $('browserSourceExplanation').textContent=t(result.code==='verification_required'?'splitVerificationNote':'splitFrameNote');renderBrowserCapability();
 if(browserSources.nativeSplit){const opened=await browserHelperRequest('openSplit',url);if(epoch!==state.frameEpoch)return;$('browserSourceExplanation').textContent=t(opened.ok?'splitOpened':'splitCouldNotOpen');}
}
function setupBrowserSources(){
 window.addEventListener('message',event=>{
  if(event.source!==window||event.origin!==new URL(location.href).origin||event.data?.channel!=='SPICE_ATLAS_BROWSER_RESPONSE')return;
  const row=browserSources.pending.get(event.data.id);if(!row)return;clearTimeout(row.timer);browserSources.pending.delete(event.data.id);row.resolve(event.data.result);
 });
 browserHelperRequest('capabilities').then(result=>{browserSources.connected=!!result.ok;browserSources.nativeSplit=!!result.nativeSplit;renderBrowserCapability();});
 $('openSourceSplit').addEventListener('click',async()=>{
  if(browserSources.nativeSplit&&browserSources.url){const result=await browserHelperRequest('openSplit',browserSources.url);$('browserSourceExplanation').textContent=t(result.ok?'splitOpened':'splitCouldNotOpen');return;}
  $('helpTitle').textContent=t('splitHelp');$('helpBody').textContent=t('splitHelpBody');showPopup($('helpDialog'),'help');
 });
}
