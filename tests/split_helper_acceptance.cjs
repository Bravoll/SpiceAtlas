const assert=require('node:assert/strict'),{allowedSearch,localAtlas,openNativeSplit,queuedSplit}=require('../browser_helper/background.js');
function api({split=-1,pair,createdSplit=7,supported=true}={}){
 const calls=[],saved={};let currentSplit=split;if(pair)saved['atlas-pair-1']=pair;
 return {calls,storage:{session:{get:async()=>saved,set:async v=>Object.assign(saved,v)}},tabs:{createSplit:supported?async()=>7:undefined,get:async()=>({id:1,index:4,windowId:2,splitViewId:currentSplit}),query:async()=>[{id:saved['atlas-pair-1']||3,splitViewId:currentSplit}],create:async value=>(calls.push(['create',value]),currentSplit=createdSplit,{id:8,splitViewId:createdSplit}),update:async(id,value)=>calls.push(['update',id,value])}};
}
(async()=>{
 const tab={id:1,url:'http://127.0.0.1:8765/?entry=parsley'},url='https://www.google.com/search?tbm=isch&q=parsley';
 for(const bad of ['https://evil.example/','https://user@www.google.com/search?q=x','http://www.google.com/search?q=x','https://www.google.com:8443/search?q=x','https://127.0.0.1/'])assert.equal(allowedSearch(bad),null);
 assert.equal(localAtlas('https://unrelated.example/'),false);assert.equal(localAtlas(tab.url),true);
 let bridge=api();assert.equal((await openNativeSplit(bridge,tab,url)).ok,true);assert.equal(bridge.calls[0][1].splitWithTabId,1);assert.equal(bridge.calls[0][1].index,5);
 bridge=api({supported:false});assert.equal((await openNativeSplit(bridge,tab,url)).code,'split_unsupported');assert.equal(bridge.calls.length,0);
 bridge=api({split:7});assert.equal((await openNativeSplit(bridge,tab,url)).code,'existing_user_split');assert.equal(bridge.calls.length,0);
 bridge=api({split:7,pair:8});assert.equal((await openNativeSplit(bridge,tab,url)).reused,true);assert.equal(bridge.calls[0][0],'update');
 bridge=api({createdSplit:-1});assert.equal((await openNativeSplit(bridge,tab,url)).ok,false);
 let active=0,maxActive=0;bridge=api();const get=bridge.tabs.get;bridge.tabs.get=async()=>{active++;maxActive=Math.max(maxActive,active);await new Promise(resolve=>setTimeout(resolve,5));active--;return get();};const second='https://image.baidu.com/search/index?word=parsley';await Promise.all([queuedSplit(bridge,tab,url),queuedSplit(bridge,tab,second)]);assert.equal(maxActive,1);assert.equal(bridge.calls[1][0],'update');assert.equal(bridge.calls[1][2].url,second);
 console.log(JSON.stringify({passed:true,checks:['split helper rejects unapproved URL credentials protocol and port','split helper accepts only local Atlas tabs','native split creation pairs next to the owning Atlas tab','missing browser API performs no pretend split','existing user split is not replaced','helper-owned split is reused and missing split result is reported','rapid split requests serialize per owning tab']}));
})().catch(error=>{console.error(error.stack);process.exit(1);});
