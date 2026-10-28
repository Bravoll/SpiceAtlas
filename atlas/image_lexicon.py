"""Image-only form vocabulary, seeded from recorded Commons filename samples."""
import hashlib,json,re,sqlite3
from .storage import ROOT
from .localization import to_hant
from .workspaces import workspaces,ClosingConnection
class ImageLexicon:
 def connect(self):
  path=workspaces.directory()/'image_keywords.sqlite3';db=sqlite3.connect(path,timeout=20,factory=ClosingConnection);db.row_factory=sqlite3.Row
  db.executescript('CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,payload TEXT);CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,payload TEXT);CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);')
  seed=ROOT/'data/image_lexicon_seed.json'
  if seed.exists():
   raw=seed.read_bytes();digest=hashlib.sha256(raw).hexdigest();row=db.execute("SELECT value FROM metadata WHERE key='seed_hash'").fetchone()
   if not row or row[0]!=digest:
    data=json.loads(raw);db.execute('DELETE FROM profiles');db.execute('DELETE FROM samples')
    db.executemany('INSERT INTO profiles VALUES(?,?)',[(key,json.dumps(value,ensure_ascii=False)) for key,value in data['profiles'].items()]);db.executemany('INSERT INTO samples(payload) VALUES(?)',[(json.dumps(x,ensure_ascii=False),) for x in data['samples']])
    for key,value in {'seed_hash':digest,'sampled_materials':data['sampled_materials'],'sampled_queries':data['sampled_queries'],'created_at':data['created_at'],'observed_terms':data['observed_terms']}.items():db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False) if key!='seed_hash' else value))
    db.commit()
  return db
 def summary(self):
  with self.connect() as db:
   profiles={r['id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM profiles')};meta={r['key']:json.loads(r['value']) for r in db.execute("SELECT * FROM metadata WHERE key<>'seed_hash'")}
  return {**meta,'profiles':{key:{**value,'zh_hant':to_hant(value.get('zh',''))} for key,value in profiles.items()},'scope':'Image retrieval only; no change to knowledge or edibility claims'}
 def form(self,item,form,profile=None):
  selected=next((f for f in item["forms"] if f["id"]==form),item["forms"][0])
  if not profile or profile=="auto":return selected
  profiles=self.summary()["profiles"]
  if profile not in profiles:raise ValueError("Unknown image profile")
  value=profiles[profile];return {"id":profile,"name":value["zh"],"name_en":value["en"]}
 def profile(self,form):
  key=form['id'];name=(form.get('name','')+' '+form.get('name_en','')).lower()
  if key in {'leaf','fresh'}:key='flakes' if re.search('干|乾|dried|flakes',name) else 'fresh'
  if key=='seed':key='whole'
  if key=='bud':return 'bud'
  return key if key in {'fresh','flakes','ground','whole','bark','bud','flower','root','sliced','jar','bag'} else 'overview'
 def queries(self,item,form):
  profile=self.profile(form);data=self.summary()['profiles'].get(profile,{})
  base=item.get('english') or item.get('scientific') or item['name'];scientific=item.get('scientific') or base
  if profile=='overview':values=[scientific]
  else:
   modifiers=data.get('query_terms',[]) or {'fresh':['fresh leaves'],'flakes':['dried flakes'],'ground':['ground powder'],'whole':['whole seeds'],'bark':['bark sticks'],'bud':['dried buds'],'root':['root'],'flower':['flowers'],'sliced':['sliced'],'jar':['jar'],'bag':['bag']}.get(profile,[])
   values=[base+' '+x for x in modifiers[:2]]+[scientific+' '+(modifiers[0] if modifiers else '')]
  first=form.get('commons_query')
  if first and profile!='overview':values.insert(0,first)
  return {'profile':profile,'queries':list(dict.fromkeys(x.strip() for x in values if x.strip()))[:3],'terms':data.get('terms',[]),'negative':data.get('negative',[])}
 def rank(self,item,form,images):
  plan=self.queries(item,form);profile=plan['profile'];scored=[]
  for im in images:
   title=im['title'].lower().replace('_',' ');text=title+' '+im.get('description','').lower()
   if re.search(r'\b(soup|salad|pasta|stew|recipe|risotto|lasagna|pizza|spaghetti|bacon|topped|stuffed|skewers|kebab|noodles|grilled|sausage|epidermis|stomata|ciboulette replaced)\b|cac[ıi]k|vichyssoise',title):continue
   if any(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',title,re.I) for term in plan['negative']):continue
   matches=[term for term in plan['terms'] if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I)]
   if profile=='fresh' and re.search(r'flakes|powder|ground|dried',title):continue
   preferred=[x.lower().replace('_',' ') for x in form.get('preferred_images',[])]
   score=len(matches)+(100 if title in preferred else 0)
   scored.append((score,{**im,'image_profile':profile,'shape_verified':False,'form_keyword_match':bool(matches),'matched_terms':matches}))
  return [x[1] for x in sorted(scored,key=lambda x:-x[0])][:8]
lexicon=ImageLexicon()
