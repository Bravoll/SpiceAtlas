/* Reading races: independent sources, obsolete cache misses and cancelled translation. */
const assert=require('node:assert/strict'),{boot,until,delay}=require('./interaction_harness.cjs');
const passed=[],failures=[],errors=[];process.on('unhandledRejection',e=>errors.push(String(e)));
async function check(name,test){try{await test();passed.push(name);}catch(error){failures.push({name,error:String(error.stack)});}}
function fixtureWithHolds(){
 const gates={kind:null,replies:[]};
 const h=boot({fetch:async(url,options={},fixture)=>{
  const value=fixture.respond(url,options),path=new URL(url,'http://127.0.0.1').pathname,body=options.body?JSON.parse(options.body):{};
  const held=gates.kind==='languages'&&path.startsWith('/api/wiki-languages/')||gates.kind==='web-cache'&&path==='/api/cache/lookup'&&body.resource.kind==='web_article'||gates.kind==='translation-cache'&&path==='/api/cache/lookup'&&body.resource.kind==='translation'||gates.kind==='translation'&&path==='/api/translate';
  const response={ok:true,status:200,json:async()=>value};
  return held?new Promise(resolve=>gates.replies.push(()=>resolve(response))):response;
 }});
 return {h,gates,release(){gates.kind=null;gates.replies.splice(0).forEach(resolve=>resolve());}};
}
async function ready(h){await until(()=>h.run('!state.restoring&&!!state.article'),'bootstrap');await delay(15);}
(async()=>{
 await check('non-Wiki reading does not wait for Chinese Wiki discovery',async()=>{
  const {h,gates,release}=fixtureWithHolds();await ready(h);gates.kind='languages';
  h.run("state.prefs.content_language='zh-Hans';state.entry.wiki={enwiki:state.entry.wiki.enwiki};state.source='gbif:en';state.wikiReady=loadWikiLanguages(state.id,state.entryEpoch)");
  const load=h.run('loadArticle()');await delay(35);
  try{assert.equal(h.run('state.article?.source'),'gbif');}finally{release();await load;}
 });
 await check('refreshing a web source does not launch unrelated Wiki discovery',async()=>{
  const {h,gates,release}=fixtureWithHolds();await ready(h);await h.run("act({type:'source',source:'bing:en'})");const before=h.fixture.requests.filter(x=>x.path.startsWith('/api/wiki-languages/')).length;
  gates.kind='languages';const load=h.run('loadArticle(true)');await delay(35);
  try{assert.equal(h.fixture.requests.filter(x=>x.path.startsWith('/api/wiki-languages/')).length,before);assert.equal(h.run('state.article?.mode'),'search_results');}finally{release();await load;}
 });
 await check('obsolete reviewed-result cache misses cannot read against a new entry',async()=>{
  const {h,gates,release}=fixtureWithHolds();await ready(h);const before=h.fixture.requests.filter(x=>x.path.startsWith('/api/source-read/')).length;
  gates.kind='web-cache';const read=h.run("readWebResult('https://www.nparks.gov.sg/florafaunaweb/flora/5/9/5944')");await until(()=>gates.replies.length,'held reviewed lookup');
  await h.run("loadEntry(state.id==='basil'?'parsley':'basil')");release();await read;
  assert.equal(h.fixture.requests.filter(x=>x.path.startsWith('/api/source-read/')).length,before);assert.equal(h.run('state.sourceReadUrl'),null);
 });
 await check('returning to original text cancels a pending translation cache miss',async()=>{
  const {h,gates,release}=fixtureWithHolds();await ready(h);h.run("state.prefs.translation_ready=true;state.prefs.translation_language='zh-Hans';state.article.language='en';$('languageMode').value='bilingual'");
  gates.kind='translation-cache';const translate=h.run('setLanguage()');await until(()=>gates.replies.length,'held translation lookup');
  h.run("$('languageMode').value='original'");await h.run('setLanguage()');release();await translate;
  assert.equal(h.fixture.requests.filter(x=>x.path==='/api/translate').length,0);assert.equal(h.run('state.translation'),null);assert.equal(h.el('languageMode').disabled,false);
 });
 await check('a late translation response cannot replace an explicit original-text choice',async()=>{
  const {h,gates,release}=fixtureWithHolds();await ready(h);h.run("state.prefs.translation_ready=true;state.prefs.translation_language='zh-Hans';state.article.language='en';$('languageMode').value='bilingual'");
  gates.kind='translation';const translate=h.run('setLanguage()');await until(()=>gates.replies.length,'held translation response');
  h.run("$('languageMode').value='original'");await h.run('setLanguage()');release();await translate;
  assert.equal(h.run('state.translation'),null);assert.equal(h.run('state.lang'),'original');assert.equal(h.el('languageMode').disabled,false);
 });
 await check('a completed no-services state clears the reader loading indicator',async()=>{
  const {h}=fixtureWithHolds();await ready(h);await h.run("state.source='auto';state.entry.policy={domestic:true};state.entry.sources=[];state.wikiReady=null;loadArticle()");
  assert.equal(h.el('articleBody').hasAttribute('aria-busy'),false);
 });
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:!failures.length,checks:passed,failures}));process.exit(failures.length?1:0);
})().catch(error=>{console.error(error.stack);process.exit(1);});
