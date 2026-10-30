/* Only Atlas's local page and a recent real click/key action may request a split. */
let lastGesture=0;for(const type of ['pointerdown','keydown'])window.addEventListener(type,event=>{if(event.isTrusted)lastGesture=Date.now();},{capture:true,passive:true});
window.addEventListener('message',event=>{
 if(event.source!==window||event.origin!==location.origin||event.data?.channel!=='SPICE_ATLAS_BROWSER_REQUEST')return;
 if(!document.getElementById('homeLink')||!document.getElementById('imageTabs')||!document.getElementById('entryName'))return;
 const {id,action,url}=event.data;if(typeof id!=='string'||id.length>150||!['capabilities','openSplit'].includes(action))return;
 const reply=result=>window.postMessage({channel:'SPICE_ATLAS_BROWSER_RESPONSE',id,result},location.origin);
 if(action==='openSplit'&&Date.now()-lastGesture>30000){reply({ok:false,code:'user_gesture_required'});return;}
 chrome.runtime.sendMessage({action,url}).then(reply,()=>reply({ok:false,code:'helper_unavailable'}));
});
