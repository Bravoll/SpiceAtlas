"""Language policy and explicit, capability-aware source plans."""
from urllib.parse import quote
from .localization import to_hant

def detect_locale(browser='en'):
 value=browser.lower()
 if value.startswith('zh'):
  return 'zh-Hant' if any(x in value for x in ('hant','-tw','-hk','-mo')) else 'zh-Hans'
 return 'en'

def language_policy(mode='auto',browser='en',preferred='auto'):
 ui=detect_locale(browser) if mode=='auto' else ('zh-Hans' if mode=='zh' else mode)
 content=ui if preferred=='auto' else ('zh-Hans' if preferred=='zh' else preferred)
 return {'ui':ui,'locale':content,'primary':'zh' if content.startswith('zh') else 'en','domestic':mode=='auto' and ui=='zh-Hans',
         'variant':'zh-hant' if content=='zh-Hant' else 'zh-hans','market':'zh-CN' if mode=='auto' and ui=='zh-Hans' else 'zh-TW' if content.startswith('zh') else 'en-AU'}

def available(service,report=None):
 row=(report or {}).get('services',{}).get(service,{})
 return row.get('ok') is not False

def resource_plan(item,mode='auto',browser='en',preferred='auto',report=None):
 policy=language_policy(mode,browser,preferred);output=[]
 for language in [policy['primary'],'en' if policy['primary']=='zh' else 'zh']:
  primary=language==policy['primary'];chinese=language=='zh';query=(item.get('name_zh') or item.get('name') or item.get('scientific')) if chinese else (item.get('name_en') or item.get('english') or item.get('scientific'))
  query=query or item.get('scientific') or item['id'];q=quote(query);wiki='zhwiki' if chinese else 'enwiki';host='https://zh.wikipedia.org' if chinese else 'https://en.wikipedia.org'
  title=item.get('wiki',{}).get(wiki);wiki_url=host+'/wiki/'+quote(title.replace(' ','_')) if title else host+'/w/index.php?search='+q
  wik={'id':wiki,'name':'中文维基' if chinese else '英文维基','name_en':'Chinese Wikipedia' if chinese else 'English Wikipedia','kind':'api' if title else 'search','available':bool(title),'url':wiki_url,'service':wiki}
  domestic=policy['domestic'] and primary;bing='bing_cn' if domestic else 'bing';bhost='https://cn.bing.com' if domestic else 'https://www.bing.com';market='zh-CN' if domestic else ('zh-TW' if chinese else 'en-AU')
  baidu={'id':'baidu','name':'百度百科','name_en':'Baidu Baike','kind':'external','url':'https://baike.baidu.com/item/'+q,'service':'baidu'}
  bingrow={'id':'bing','name':'必应（国内）' if domestic else 'Bing（国际）','name_en':'Bing China' if domestic else 'Bing International','kind':'external','url':bhost+'/search?q='+q+'&mkt='+market,'service':bing}
  google={'id':'google','name':'Google','name_en':'Google','kind':'external','url':'https://www.google.com/search?q='+q+'&hl='+('zh-TW' if policy['locale']=='zh-Hant' else 'zh-CN' if chinese else 'en')+'&lr=lang_'+language,'service':'google'}
  rows=[baidu,bingrow,wik] if domestic else [wik,bingrow,google]
  if not domestic and chinese:rows.append(baidu)
  for key,ref in item.get('references',{}).items():
   ref_language=ref.get('language','en')
   if ref_language==language:rows.append({'id':key,'name':ref['name'],'name_en':ref.get('name_en',ref['name']),'kind':'reference','url':ref['url'],'service':'gbif_web' if key=='gbif' else key})
  if item.get('wikidata_id'):rows.append({'id':'wikidata','name':'Wikidata 名称资料','name_en':'Wikidata names','kind':'external','url':'https://www.wikidata.org/wiki/'+item['wikidata_id'],'service':'wikidata_web'})
  for row in rows:
   if available(row['service'],report):output.append({**row,'name':to_hant(row['name']) if policy['ui']=='zh-Hant' else row['name'],'key':row['id']+':'+language,'language':language,'primary':primary,'query':query})
 return {'policy':policy,'sources':output}

def image_gateways(item,form=None,mode='auto',browser='en',preferred='auto',report=None,profile=None):
 selected=next((f for f in item['forms'] if f['id']==form),item['forms'][0]);p=language_policy(mode,browser,preferred)
 query=selected.get('image_query') or item.get('scientific') or item.get('english') or item['name']
 if profile and profile!='auto':
  from .image_lexicon import lexicon
  selected=lexicon.form(item,form,profile);query=lexicon.queries(item,selected)['queries'][0]
 q=quote(query)
 candidates={'commons':('commons','https://commons.wikimedia.org/w/index.php?search='+q+'&title=Special:MediaSearch&type=image'),
 'bing':('bing_cn' if p['domestic'] else 'bing',('https://cn.bing.com' if p['domestic'] else 'https://www.bing.com')+'/images/search?q='+q+'&mkt='+p['market']),
 'google':('google','https://www.google.com/search?tbm=isch&q='+q+'&hl='+('zh-TW' if p['locale']=='zh-Hant' else 'zh-CN' if p['primary']=='zh' else 'en')),
 'baidu':('baidu_images','https://image.baidu.com/search/index?tn=baiduimage&word='+q)}
 return {'query':query,**{k:url for k,(service,url) in candidates.items() if available(service,report)}}
