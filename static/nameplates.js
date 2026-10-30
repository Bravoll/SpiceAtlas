"use strict";
function renderNameplates(){
 if(!state.entry)return;const e=state.entry,cn=state.nameChineseStyle||state.prefs.name_chinese_style||'botanical',west=state.nameWesternStyle||state.prefs.name_western_style||'book';
 $('chineseNameStyle').value=cn;$('westernNameStyle').value=west;$('chineseNameplate').dataset.style=cn;$('westernNameplate').dataset.style=west;
 $('chineseName').textContent=state.locale==='zh-Hant'?(e.name_zh_hant||e.name_hant||e.name_zh||e.name_en):(e.name_zh||e.name_en||e.english);
 $('chineseName').lang=state.locale==='zh-Hant'?'zh-Hant':'zh-Hans';
 $('specimenTitle').textContent=west==='inscription'?(e.scientific_en||e.scientific):(e.name_en||e.spoken_english||e.english||e.scientific_en);
 $('specimenTitle').lang=west==='inscription'?'la':'en';$('scientific').hidden=west==='inscription';
 for(const id of ['chineseNameplate','westernNameplate'])$(id).title=t('styleNote');
}
function updateOutlinePresentation(){
 const outline=$('readerOutline');if(outline)outline.hidden=state.source==='other'||!$('outline').querySelector('a');
}
function setupNameplates(){
 $('chineseNameStyle').addEventListener('change',()=>act({type:'nameChineseStyle',style:$('chineseNameStyle').value}));
 $('westernNameStyle').addEventListener('change',()=>act({type:'nameWesternStyle',style:$('westernNameStyle').value}));
}
