/* No remote page access, script injection, header rewriting or tab-content reading. */
function allowedSearch(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&(['www.google.com','google.com'].includes(u.hostname)&&u.pathname==='/search'||['www.bing.com','cn.bing.com'].includes(u.hostname)&&u.pathname.startsWith('/images/search')||u.hostname==='image.baidu.com'&&u.pathname==='/search/index')?u.href:null;}catch{return null;}}
function localAtlas(value){try{const u=new URL(value);return u.protocol==='http:'&&['127.0.0.1','localhost'].includes(u.hostname)&&['/','/static/index.html'].includes(u.pathname);}catch{return false;}}
async function openNativeSplit(api,source,url){
 const target=allowedSearch(url);if(!target||!localAtlas(source.url))return {ok:false,code:'invalid_target'};
 if(typeof api.tabs.createSplit!=='function')return {ok:false,code:'split_unsupported'};
 const tab=await api.tabs.get(source.id),key='atlas-pair-'+source.id,stored=await api.storage.session.get(key),old=stored[key];
 if(tab.splitViewId!==undefined&&tab.splitViewId!==-1){
  const siblings=await api.tabs.query({windowId:tab.windowId}),pair=siblings.find(other=>other.id===old&&other.splitViewId===tab.splitViewId&&other.id!==tab.id);
  if(!pair)return {ok:false,code:'existing_user_split'};
  await api.tabs.update(pair.id,{url:target,active:true});return {ok:true,mode:'split',reused:true};
 }
 const created=await api.tabs.create({url:target,windowId:tab.windowId,index:tab.index+1,active:true,splitWithTabId:tab.id});
 if(created.splitViewId===undefined||created.splitViewId===-1)return {ok:false,code:'split_not_created',mode:'tab'};
 await api.storage.session.set({[key]:created.id});return {ok:true,mode:'split'};
}
const splitQueues=new Map();
function queuedSplit(api,source,url){
 const previous=splitQueues.get(source.id)||Promise.resolve(),next=previous.catch(()=>{}).then(()=>openNativeSplit(api,source,url));splitQueues.set(source.id,next);
 const clean=()=>{if(splitQueues.get(source.id)===next)splitQueues.delete(source.id);};next.then(clean,clean);return next;
}
if(typeof chrome!=='undefined')chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(!sender.tab||!localAtlas(sender.tab.url))return false;
 if(message.action==='capabilities'){reply({ok:true,nativeSplit:typeof chrome.tabs.createSplit==='function'});return false;}
 if(message.action!=='openSplit')return false;
 queuedSplit(chrome,sender.tab,message.url).then(reply,()=>reply({ok:false,code:'browser_api_failed'}));return true;
});
if(typeof module!=='undefined')module.exports={allowedSearch,localAtlas,openNativeSplit,queuedSplit};
