"""Opt-in live source checks; no configured personal translation service is called."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from atlas.providers import Reader,ARTICLE_VARIANT
from atlas.health import Health
from atlas.preferences import preferences,DEFAULTS
from atlas.network import SourceFailure
from unittest.mock import patch
async def run():
 reader=Reader();results=[];photos={}
 for source in ('zhwiki','enwiki'):
  try:
   value=await reader.article('parsley',source,True);results.append({'service':source,'ok':value['mode']=='article','revision':value.get('revision_id'),'preserved_links':'href=' in value.get('html',''),'variant':value.get('variant')})
  except SourceFailure as e:results.append({'service':source,'ok':False,'diagnostic':e.public()})
 for form in ('flakes','fresh'):
  try:
   value=await reader.images('parsley','commons',form,True);photos[form]=value;results.append({'service':'commons','form':form,'ok':True,'images':len(value['images']),'titles':[x['title'] for x in value['images']],'attribution':all(x.get('source_url') and x.get('author') and x.get('license') for x in value['images'])})
  except SourceFailure as e:results.append({'service':'commons','form':form,'ok':False,'diagnostic':e.public()})
 health=Health();report=await health.check();results.append({'service':'health','report':report})
 Path('tests/live_image_metadata.json').write_text(json.dumps(photos,ensure_ascii=False),'utf-8')
 Path('data/verification_v04_live.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(results,ensure_ascii=False))
with patch.object(preferences,'values',return_value=dict(DEFAULTS)):asyncio.run(run())
