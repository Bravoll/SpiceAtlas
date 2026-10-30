"""Research the declared stratified sample; persist successes, failures and skips."""
import argparse,asyncio,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from atlas.search_pages import first_page,ENGINES

async def run(sample_path,output,timeout=8):
    sample=json.loads(sample_path.read_text());rows=[]
    async def engine_run(engine):
        failures=0;gate=None
        for item in sample['entries']:
            query=((item.get('name_zh') or item['query_name'])+' 植物 香料') if engine=='bing_cn' else item['query_name']+' plant herb spice'
            common={'entry_id':item['id'],'sample_index':item['sample_index'],'engine':engine,'query':query,'attempted_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'page':1,'request_timeout_seconds':timeout,'provenance':'direct named-engine HTML first-page request'}
            if gate:result={**common,'status':'skipped','reason':gate,'results':[]}
            else:
                result={**common,**await first_page(engine,query,timeout=timeout)}
                failures=failures+1 if result['status']!='ok' else 0
                if result['status']=='verification_required':gate='Provider requested verification; further automated requests stopped.'
                elif failures>=3:gate='Three consecutive unavailable/empty responses in this environment; circuit opened for this run.'
            rows.append(result)
            with output.open('a',encoding='utf-8') as stream:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            if not gate:await asyncio.sleep(.2)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text('')
    await asyncio.gather(*(engine_run(engine) for engine in ENGINES))
    summary={'sample_count':sample['sample_count'],'planned_first_pages':len(rows),'engines':{engine:{state:sum(r['engine']==engine and r['status']==state for r in rows) for state in sorted({r['status'] for r in rows if r['engine']==engine})} for engine in ENGINES},'actual_results':sum(len(r['results']) for r in rows),'supplemental_search_service':'Recorded separately; never counted as a named-engine first page.'}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sample',type=Path,default=Path('data/source_research/sample_v07.json'));parser.add_argument('--output',type=Path,default=Path('data/source_research/first_pages_v07.jsonl'));parser.add_argument('--timeout',type=float,default=8);args=parser.parse_args()
    asyncio.run(run(args.sample,args.output,args.timeout))
