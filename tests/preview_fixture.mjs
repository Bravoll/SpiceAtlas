// Synthetic UI preview only. Production uses the Python FastAPI app.
import http from 'node:http';import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),{createFixture,otherEvents}=require('./fixture_service.cjs');
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'..'),fixture=createFixture(root),streams=new Set();
let holdNextArticle=false;const heldArticles=[];
let port=4173;for(let i=0;i<process.argv.length;i++)if(process.argv[i]==='--port')port=Number(process.argv[i+1]);
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json'};
const broadcast=value=>{for(const stream of streams)if(!stream.destroyed)stream.write('data: '+JSON.stringify({...value,version:'fixture-version'})+'\n\n');};
const server=http.createServer(async(req,res)=>{try{
 const u=new URL(req.url,'http://localhost');
 if(u.pathname==='/api/runtime/events'){
  res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache'});streams.add(res);
  res.write('data: '+JSON.stringify({kind:'snapshot',...fixture.runtimeState,notifications:fixture.respond('/api/health').notifications,version:'fixture-version'})+'\n\n');
  const timer=setInterval(()=>res.write(': heartbeat\n\n'),15000);res.on('close',()=>{streams.delete(res);clearInterval(timer);});return;
 }
 if(u.pathname.startsWith('/api/')){
  let body='';for await(const chunk of req)body+=chunk;
  if(u.pathname==='/api/fixture-hold-article'){holdNextArticle=true;res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');return;}
  if(u.pathname==='/api/fixture-release-article'){for(const item of heldArticles.splice(0)){if(!item.res.destroyed){item.res.writeHead(200,{'Content-Type':'application/json'});item.res.end(JSON.stringify(item.data));}}res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');return;}
  if(u.pathname==='/api/fixture-change-health'){fixture.changeHealth();res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');return;}
  if(u.pathname==='/api/fixture-runtime'){
   const action=JSON.parse(body).action;
   if(action==='pause'){broadcast(fixture.pause());setTimeout(()=>broadcast(fixture.finishPause()),500);}else broadcast(fixture.resume());
   res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');return;
  }
  if(/^\/api\/other-sources\/[^/]+\/stream$/.test(u.pathname)){
   res.writeHead(200,{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store'});
   const events=otherEvents(decodeURIComponent(u.pathname.split('/')[3])),timers=[];
   events.forEach((event,i)=>timers.push(setTimeout(()=>{if(!res.destroyed){res.write(JSON.stringify(event)+'\n');if(i===events.length-1)res.end();}},[0,180,500,900,1000][i])));
   res.on('close',()=>timers.forEach(clearTimeout));return;
  }
  const data=fixture.respond(u.href,{method:req.method,body:body||undefined});
  if(data.mode==='article'&&['enwiki','zhwiki'].includes(data.source)){
   const chapters=[['fixture-identity','UI fixture · Identity'],['fixture-classification','UI fixture · Classification'],['fixture-context','UI fixture · Context']];
   const paragraphs=(data.html||'').match(/<p[\s>][\s\S]*?<\/p>/g)||[];
   data.html=chapters.map(([id,title],i)=>'<h2 id="'+id+'">'+title+'</h2>'+paragraphs.slice(i*3,i*3+3).join('')).join('');data.focus_html=data.html;data.toc=data.focus_toc=chapters.map(([id,title])=>({id,title,level:2}));
  }
  if(holdNextArticle&&u.pathname.startsWith('/api/article/')){holdNextArticle=false;heldArticles.push({res,data});return;}res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(data));return;
 }
 const relative=u.pathname==='/'?'static/index.html':u.pathname.replace(/^\//,''),file=path.resolve(root,relative);
 if(!file.startsWith(root+'/')||!fs.existsSync(file)){res.writeHead(404);res.end('Not found');return;}
 let content=fs.readFileSync(file);
 if(relative==='static/index.html')content=content.toString().replace('</body>','<div class="fixture-tools" style="position:fixed;bottom:6px;right:10px;z-index:100;background:#263b29;color:#fff;padding:4px 7px;font:9px system-ui">Synthetic UI fixture <button id="fixtureNotices">2 notices</button><button id="fixturePause">Pause</button><button id="fixtureResume">Resume</button><button id="fixtureHoldArticle">Hold article</button><button id="fixtureReleaseArticle">Release article</button></div><script src="/tests/preview_controls.js"></script></body>');
 res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(content);
 }catch(error){res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:String(error)}));}
});
server.listen(port,'0.0.0.0',()=>console.log('Synthetic UI fixture ready on '+port));
