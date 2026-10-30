"use strict";
/* Bounded, real-text units. Tables, links and long prose never become a slide. */
const inkMotion={kind:null,overlays:[],units:[],effects:[],generation:0};
function clearInkMotion(){
 for(const effect of inkMotion.effects)effect.cancel?.();inkMotion.effects=[];
 for(const span of inkMotion.units)if(span.parentNode)span.replaceWith(document.createTextNode(span.textContent));inkMotion.units=[];
 for(const node of inkMotion.overlays)node.remove();inkMotion.overlays=[];
}
function inkWords(value){return String(value).match(/[\p{Script=Han}]|[\p{Script=Latin}\p{N}\p{M}]+(?:['’\-][\p{Script=Latin}\p{N}\p{M}]+)*|[^\s]|\s+/gu)||[];}
function beginInkChange(kind){inkMotion.generation++;clearInkMotion();inkMotion.kind=kind;}
function inkTargets(target){
 if(!target)return [];
 if(target.id==='articleBody')return Array.from(target.querySelectorAll('h2,h3,p')).filter(node=>!node.closest('table,pre,code,.translation-pair')&&node.textContent.trim().length<=260).slice(0,2);
 return target.textContent.length<=300?[target]:[];
}
function revealInkText(target,kind=inkMotion.kind){
 if(!target||!kind||motionLevel()!==3)return false;
 const generation=inkMotion.generation;let remaining=Math.max(0,64-inkMotion.units.length),animated=0;
 for(const root of inkTargets(target)){
  if(root.querySelector('table,pre,code,math,svg'))continue;
  const rect=root.getBoundingClientRect();if(rect.bottom<0||rect.top>window.innerHeight)continue;
  const nodes=[];const collect=node=>{for(const child of Array.from(node.childNodes)){if(child.nodeType===3)nodes.push(child);else if(child.nodeType===1&&!['SCRIPT','STYLE','BUTTON'].includes(child.tagName))collect(child);}};collect(root);
  const spans=[];
  for(const node of nodes){
   if(!remaining)break;const fragment=document.createDocumentFragment();
   for(const word of inkWords(node.textContent)){
    if(!word.trim()||remaining<=0){fragment.appendChild(document.createTextNode(word));continue;}
    const span=document.createElement('span');span.className='ink-unit';span.textContent=word;fragment.appendChild(span);spans.push(span);inkMotion.units.push(span);remaining--;
   }
   node.replaceWith(fragment);
  }
  root.dataset.textTransition=kind;
  spans.forEach((span,index)=>{
   const frames=kind==='language'?[{opacity:.1,transform:'perspective(320px) rotateX(-55deg) translateY(2px)'},{opacity:1,transform:'none'}]:[{opacity:.2,transform:'translateY(2px)'},{opacity:1,transform:'none'}];
   const effect=trackMotion(span.animate(frames,{duration:kind==='language'?240:180,delay:Math.min(index*7,140),easing:'cubic-bezier(.2,.75,.2,1)',fill:'backwards'}));inkMotion.effects.push(effect);animated++;
   const clean=()=>{if(span.parentNode)span.replaceWith(document.createTextNode(span.textContent));inkMotion.units=inkMotion.units.filter(x=>x!==span);inkMotion.effects=inkMotion.effects.filter(x=>x!==effect);if(generation===inkMotion.generation)delete root.dataset.textTransition;};effect.finished.then(clean,clean);
  });
 }
 return animated>0;
}
function revealReadingText(target){
 if(revealInkText(target))return;
 const node=target?.querySelector('h2,h3,p');if(node&&motionLevel())motionEffect(node,[{opacity:.7},{opacity:1}],motionLevel()===1?80:140);
}
window.addEventListener('pagehide',clearInkMotion);
