"""Public metadata and synthetic article text, never a bundled encyclopedia snapshot."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app
from atlas.catalogue import catalogue
from atlas.preferences import DEFAULTS,SECRET_FIELDS
from atlas.resources import resource_plan,image_gateways
client=TestClient(app)
fixture={'settings':{**{k:v for k,v in DEFAULTS.items() if k not in SECRET_FIELDS},'has_lm_api_key':False,'has_google_api_key':False,'has_google_translate_key':False,'has_azure_translate_key':False,'model_ready':False,'translation_ready':False},'entries':{}}
for key,url in {'catalogue':'/api/catalog?scope=all&limit=30','botanical':'/api/catalog?scope=botanical&limit=30','botanical_next':'/api/catalog?scope=botanical&limit=30&offset=30','tree_culinary':'/api/catalog/nodes?parent=root-culinary&language=en','tree_all':'/api/catalog/nodes?parent=root-all&language=en','tree_botanical':'/api/catalog/nodes?parent=root-botanical&language=en','discovery_options':'/api/discovery/options','vocabulary':'/api/image-vocabulary'}.items():fixture[key]=client.get(url).json()
fixture['jobs']={'jobs':[]}
for key in ['parsley','basil','coriander','cinnamon','paprika']:
 item=catalogue.get(key);fixture['entries'][key]={**item,**resource_plan(item,'auto','en-AU'),'related':catalogue.related(item),'image_gateways':image_gateways(item),'favorite':False}
fixture['entry']=fixture['entries']['parsley']
for source,language in [('zhwiki','zh'),('enwiki','en')]:
 html='<p>'+('Synthetic UI fixture text, not encyclopedia content. This paragraph supports layout and scroll testing. '*5 if language=='en' else '此处是界面测试文本，不是百科正文。用于测试长文阅读、滚动以及来源引用的显示。'*8)+'</p>'
 fixture['article_'+source]={'mode':'article','source':source,'language':language,'variant':'zh-hans' if language=='zh' else 'en','title':'UI fixture · Synthetic reading text','source_url':'https://example.org/ui-test','fetched_at':'2026-10-28T00:00:00Z','revision_id':1,'html':''.join('<h2 id="fixture-'+str(i)+'">'+('Chapter ' if language=='en' else '章节 ')+str(i+1)+'</h2>'+html*2 for i in range(8)),'focus_html':html*8,'toc':[{'id':'fixture-'+str(i),'title':'Chapter '+str(i+1),'level':2} for i in range(8)],'focus_toc':[],'revision_url':'https://example.org/ui-test','authors_url':'https://example.org/ui-test','license':'Synthetic UI fixture','license_url':'https://example.org/ui-test','delivery':'cache'}
path=Path(sys.argv[1] if len(sys.argv)>1 else 'tests/ui_fixtures.json');path.write_text(json.dumps(fixture,ensure_ascii=False),'utf-8');print(path)
