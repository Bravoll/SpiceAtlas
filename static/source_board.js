"use strict";
const otherUi={controller:null,token:0,cards:0,errors:[],ended:false};
function stopOtherSources(hide=false){
 otherUi.token++;otherUi.controller?.abort();otherUi.controller=null;
 if(hide){$('otherSourcesBoard').hidden=true;document.querySelector('.reader-shell').hidden=false;}
 else{$('otherSourcesStatus').textContent=t('otherStopped');$('otherSourcesStop').disabled=true;}
}
function appendOtherCard(card){
 const rail=$('otherSourcesRail'),follow=rail.scrollLeft+rail.clientWidth>=rail.scrollWidth-30;
 const article=document.createElement('article');article.className='other-card';article.dataset.sourceUrl=card.source_url;article.setAttribute('aria-label',card.title);
 article.innerHTML='<header><span class="other-provider">'+esc(state.ui==='en'?card.provider_name:card.provider_name_zh)+'</span><span class="other-arrival">'+esc(card.order)+' · '+esc((card.elapsed_ms/1000).toFixed(2))+' s</span><h3>'+esc(card.title)+'</h3><p>'+esc(t('otherCandidate'))+'</p>'+ext(card.source_url,t('openSource'))+'</header>'+(card.toc?.length?'<details class="other-outline"><summary>'+esc(t('contents'))+'</summary>'+card.toc.map(item=>'<a href="#'+esc(item.id)+'">'+esc(item.title)+'</a>').join('')+'</details>':'')+'<div class="other-body article-body">'+card.html+'</div><footer><span>'+esc(formatDate(card.completed_at))+'</span><span>'+esc(card.license||t('sourceTerms'))+'</span>'+ext(card.source_url,t('source')+' ↗')+(card.revision_url?ext(card.revision_url,t('fixedVersion')):'')+(card.license_url?ext(card.license_url,t('license')):'')+'</footer>';
 rail.appendChild(article);otherUi.cards++;
 const effect=motionEffect(article,[{opacity:0,transform:'translateX(42px) scale(.98)'},{opacity:1,transform:'none'}],[0,90,230,430][motionLevel()]);
 if(effect)article.dataset.arriving='true';effect?.finished.catch(()=>{}).then(()=>delete article.dataset.arriving);
 requestAnimationFrame(()=>{if(follow)rail.scrollTo?.({left:rail.scrollWidth,behavior:motionLevel()?'smooth':'instant'});settleReadingAnchor();});
}
function consumeOtherEvent(record,token){
 if(token!==otherUi.token)return;
 if(record.type==='card')appendOtherCard(record.card);
 else if(record.type==='error'||record.type==='search'&&record.status!=='ok'){
  record={...record,code:record.code||record.status};
  otherUi.errors.push(record);const row=document.createElement('li');row.textContent=record.provider+' · '+record.code+(record.message?' · '+record.message:'');
  if(record.url){const link=document.createElement('a');link.href=record.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=t('openSource');row.appendChild(link);}
  $('otherSourcesErrors').appendChild(row);
 }else if(record.type==='done'){
  otherUi.ended=true;$('otherSourcesStop').disabled=true;
  $('otherSourcesStatus').textContent=t('otherFinished',{count:otherUi.cards,failed:otherUi.errors.length})+' · '+t(record.reason==='paused'?'servicePaused':record.reason==='timeout'?'otherTimedOut':record.reason==='card_limit'?'otherCardLimit':'otherComplete');
 }else if(record.type==='progress')$('otherSourcesStatus').textContent=t('otherProgress',{count:otherUi.cards,pending:record.pending});
 if(!otherUi.ended&&record.type==='card')$('otherSourcesStatus').textContent=t('otherReceived',{count:otherUi.cards});
}
async function loadOtherSources(refresh=false){
 stopOtherSources();const token=otherUi.token,entry=state.id,version=state.version,controller=otherUi.controller=new AbortController();
 otherUi.cards=0;otherUi.errors=[];otherUi.ended=false;
 $('otherSourcesRail').innerHTML='';$('otherSourcesErrors').innerHTML='';$('otherSourcesBoard').hidden=false;document.querySelector('.reader-shell').hidden=true;$('otherSourcesStop').disabled=false;
 $('otherSourcesStatus').textContent=t('otherLoading',{seconds:state.prefs.other_total_timeout||20});
 state.article={mode:'aggregate',source:'other'};state.actualSource='other';renderSources();
 const cap=setTimeout(()=>controller.abort(),((state.prefs.other_total_timeout||20)+2)*1000);
 try{
  const response=await fetch('/api/other-sources/'+encodeURIComponent(entry)+'/stream?refresh='+String(Boolean(refresh)),{headers:{'X-Atlas-Version':version,'X-Atlas-Event':resourceUi.eventId},signal:controller.signal});
  if(!response.ok){const error=await response.json();if(response.status===409){location.reload();return;}throw new Error(error.error||error.detail||t('failed'));}
  if(!response.body?.getReader){const text=await response.text();for(const line of text.split('\n'))if(line.trim())consumeOtherEvent(JSON.parse(line),token);return;}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
   if(token!==otherUi.token){await reader.cancel();return;}
   let end;while((end=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,end);buffer=buffer.slice(end+1);if(line.trim())consumeOtherEvent(JSON.parse(line),token);}
  }
  buffer+=decoder.decode();if(buffer.trim())consumeOtherEvent(JSON.parse(buffer),token);
  if(!otherUi.ended&&token===otherUi.token)$('otherSourcesStatus').textContent=t('otherStreamEnded');
 }catch(error){if(token===otherUi.token)$('otherSourcesStatus').textContent=controller.signal.aborted?t('otherTimedOut'):errorMessage(error);}
 finally{clearTimeout(cap);if(token===otherUi.token){$('otherSourcesStop').disabled=true;otherUi.controller=null;rememberView();}}
}
function setupSourceBoard(){
 $('otherSourcesStop').addEventListener('click',()=>stopOtherSources());
 $('otherSourcesRefresh').addEventListener('click',()=>act({type:'refreshArticle'}));
 $('otherSourcesLatest').addEventListener('click',()=>$('otherSourcesRail').scrollTo?.({left:$('otherSourcesRail').scrollWidth,behavior:motionLevel()?'smooth':'instant'}));
 window.addEventListener('pagehide',()=>stopOtherSources());
}
