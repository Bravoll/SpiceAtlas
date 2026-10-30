/* QA-only controls. The production page does not load this file. */
document.getElementById('fixtureNotices').addEventListener('click',async()=>{for(let i=0;i<2;i++)await fetch('/api/fixture-change-health',{method:'POST'});});
for(const action of ['Pause','Resume'])document.getElementById('fixture'+action).addEventListener('click',()=>fetch('/api/fixture-runtime',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:action.toLowerCase()})}));

for(const action of ['Hold','Release'])document.getElementById('fixture'+action+'Article').addEventListener('click',()=>fetch('/api/fixture-'+action.toLowerCase()+'-article',{method:'POST'}));
