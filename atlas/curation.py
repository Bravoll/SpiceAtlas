"""Conservative import admission; category membership alone proves no culinary use."""
import json,re
from .storage import ROOT

def admit(item,entity=None):
 if item.get('review_state')=='curated':return {'status':'keep','scope':'culinary','review_state':'curated','reason':'Editorial material identity retained'}
 path=ROOT/'data/research_curation/entity_type_rules.json';rules=json.loads(path.read_text('utf-8')) if path.exists() else {}
 qid=item.get('wikidata_id') or (entity or {}).get('id')
 for key,status,scope in [('manual_reject','excluded',None),('manual_pending','pending',None),('manual_botanical','keep','botanical'),('manual_culinary','keep','culinary')]:
  if qid in rules.get(key,{}):return {'status':status,'scope':scope,'review_state':'reference_only' if scope=='botanical' else 'candidate','reason':rules[key][qid],'qid':qid}
 types=set(item.get('entity_types',[]))
 if entity:
  types|={x.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id') for x in entity.get('claims',{}).get('P31',[]) if isinstance(x.get('mainsnak',{}).get('datavalue',{}).get('value'),dict)}
 text=' '.join([item.get('name_zh',''),item.get('name_en',''),*item.get('entity_descriptions',{}).values()]).lower()
 excluded_types=rules.get('excluded_types',{})
 if types & set(excluded_types) or re.search(r'加多[宝寶]|jdb group|wong lo kat|\b(company|corporation|brand|restaurant|business|festival|film|album|storage container|spice rack|microorganism|bacterium)\b|公司|品牌|企業|企业|人物|细菌|細菌',text):return {'status':'excluded','reason':'Non-material entity: company, brand, object, event or organism outside plant scope','entity_types':sorted(x for x in types if x)}
 if 'Q16521' in types or types & set(rules.get('taxon_types',[])) or item.get('scientific'):
  return {'status':'keep','scope':'botanical','review_state':'reference_only','reason':'Botanical identity; culinary use is not established','entity_types':sorted(x for x in types if x)}
 if types & set(rules.get('culinary_types',[])):
  return {'status':'keep','scope':'culinary','review_state':'candidate','reason':'Culinary material evidence; individual record remains unreviewed','entity_types':sorted(x for x in types if x)}
 return {'status':'pending','reason':'Insufficient material or culinary evidence; review required','entity_types':sorted(x for x in types if x)}
