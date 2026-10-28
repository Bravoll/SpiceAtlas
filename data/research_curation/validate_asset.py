import json,sqlite3
import curate_catalogue as c

def run():
 db=sqlite3.connect(c.HERE/'cleaned_catalogue.sqlite3');db.row_factory=sqlite3.Row;checks={}
 checks['integrity']=db.execute('pragma integrity_check').fetchone()[0]
 checks['bad_primary_rows']=db.execute("select count(*) from entries where name_en in ('JDB Group','masala dabba','2015 United States E. coli outbreak','Wong Lo Kat')").fetchone()[0]
 checks['dangling_membership']=db.execute('select count(*) from membership where entry_id not in (select id from entries)').fetchone()[0]
 checks['dangling_aliases']=db.execute('select count(*) from aliases where entry_id not in (select id from entries)').fetchone()[0]
 checks['fts_count']=db.execute('select count(*) from entry_search').fetchone()[0]
 checks['entry_count']=db.execute('select count(*) from entries').fetchone()[0]
 checks['audit_count']=db.execute('select count(*) from quarantine').fetchone()[0]
 checks['archive_samples']=[dict(r) for r in db.execute("select id,status,reason from quarantine where id in ('wd-Q18231093','wd-Q23808433','wd-Q22020932','wd-Q701395')")]
 original=json.loads((c.ROOT/'data/catalog.json').read_text())['entries']
 checks['curated_notes_preserved']=all(json.loads(db.execute('select payload from entries where id=?',(e['id'],)).fetchone()[0]).get('scope_note')==e.get('scope_note') for e in original)
 from opencc import OpenCC
 checks['traditional_search_matches']=db.execute('select count(*) from entries where search_text like ?',('%'+c.norm(OpenCC('t2s').convert('歐芹'))+'%',)).fetchone()[0]>0
 checks['no_duplicate_qid']=not bool(db.execute("select wikidata_id from entries where wikidata_id<>'' group by wikidata_id having count(*)>1").fetchall())
 checks['no_duplicate_scientific']=not bool(db.execute("select scientific from entries where scientific<>'' group by lower(scientific) having count(*)>1").fetchall())
 db.close();c.save('asset_validation.json',checks)
 assert checks['integrity']=='ok' and checks['bad_primary_rows']==checks['dangling_membership']==checks['dangling_aliases']==0 and checks['fts_count']==checks['entry_count'] and checks['curated_notes_preserved'] and checks['no_duplicate_qid'] and checks['no_duplicate_scientific'],checks
 print(json.dumps(checks,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
