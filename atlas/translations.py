"""Official translation adapters with preserved source anchors and numbers."""
import html,json,re
import httpx
from bs4 import BeautifulSoup
from .network import client_options,SourceFailure
from .preferences import TRANSLATION_LANGUAGES

def excluded(source,targets):
 return source in targets or source.startswith('zh') and 'zh' in targets

def protected(value):
 pattern=r'⟪LINK_\d+⟫|\d+(?:[.,]\d+)*'
 return ''.join('<span class="notranslate" translate="no">'+html.escape(part)+'</span>' if re.fullmatch(pattern,part) else html.escape(part) for part in re.split('('+pattern+')',value))

async def cloud_translate(provider,texts,target,p):
 if target=='zh':target='zh-Hans'
 if target not in TRANSLATION_LANGUAGES-{'auto'}:raise ValueError('Unsupported target')
 options=client_options(60);payloads=[protected(x) for x in texts]
 if provider=='google':
  url='https://translation.googleapis.com/language/translate/v2';params={'key':p['google_translate_key']}
  payload={'q':payloads,'target':{'zh-Hans':'zh-CN','zh-Hant':'zh-TW'}.get(target,target),'format':'html','model':'nmt'}
 elif provider=='azure':
  url='https://api.cognitive.microsofttranslator.com/translate';params={'api-version':'3.0','to':target,'textType':'html'}
  options['headers']['Ocp-Apim-Subscription-Key']=p['azure_translate_key']
  if p.get('azure_region'):options['headers']['Ocp-Apim-Subscription-Region']=p['azure_region']
  payload=[{'Text':x} for x in payloads]
 else:raise ValueError('Unsupported provider')
 async with httpx.AsyncClient(**options) as client:
  response=await client.post(url,params=params,json=payload);response.raise_for_status();data=response.json()
 if provider=='google':values=[x['translatedText'] for x in data['data']['translations']]
 else:values=[x['translations'][0]['text'] for x in data]
 if len(values)!=len(texts) or any(not isinstance(x,str) for x in values):raise ValueError('Translation count mismatch')
 return [BeautifulSoup(x,'html.parser').get_text() for x in values]

async def local_translate(blocks,target,p,model):
 schema={'type':'object','properties':{'translations':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'text':{'type':'string'}},'required':['id','text'],'additionalProperties':False}}},'required':['translations'],'additionalProperties':False}
 payload={'model':model,'temperature':0.1,'max_tokens':6000,'messages':[
 {'role':'system','content':'Translate faithfully into '+{'zh-Hans':'Simplified Chinese','zh-Hant':'Traditional Chinese'}.get(target,target)+'. Preserve scientific names, every number, unit, ID and every ⟪LINK_n⟫ marker exactly once. No invented facts, citations or HTML. Return JSON.'},
 {'role':'user','content':json.dumps([{'id':x['id'],'text':x['text']} for x in blocks],ensure_ascii=False)}],
 'response_format':{'type':'json_schema','json_schema':{'name':'atlas_translation','strict':True,'schema':schema}}}
 headers={'Authorization':'Bearer '+p['lm_api_key']} if p['lm_api_key'] else {}
 async with httpx.AsyncClient(timeout=240,trust_env=False,headers=headers) as client:
  response=await client.post(p['lm_base_url'].rstrip('/')+'/chat/completions',json=payload);response.raise_for_status();items=json.loads(response.json()['choices'][0]['message']['content'])['translations']
 if len(items)!=len(blocks) or {x['id'] for x in items}!={x['id'] for x in blocks}:raise ValueError('Paragraph mismatch')
 mapping={x['id']:x['text'] for x in items}
 return [mapping[x['id']] for x in blocks]

def validate_numbers(before,after):
 if not isinstance(after,str) or sorted(re.findall(r'\d+(?:[.,]\d+)*',before))!=sorted(re.findall(r'\d+(?:[.,]\d+)*',after)):raise ValueError('Number mismatch')
