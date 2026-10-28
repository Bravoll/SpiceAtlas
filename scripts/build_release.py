"""Build a portable source release, excluding credentials and runtime workspace data."""
import json,sqlite3,tempfile,zipfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from atlas.seed import ensure_baseline
ensure_baseline(ROOT/'data/catalogue.sqlite3')
out=Path(sys.argv[1] if len(sys.argv)>1 else ROOT.parent/'Spice_Atlas_Local_v0.4.zip')
files=[]
for folder in ('atlas','static','scripts','tests'):
 files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'node_modules' not in p.parts)
files.extend(ROOT/p for p in ('main.py','launch.py','run.cmd','run.sh','README.md','development.md','CONTENT_LICENSES.md','config.example.json','pyproject.toml','uv.lock','requirements.txt') if (ROOT/p).exists())
files.extend(p for p in (ROOT/'data').glob('*') if p.is_file() and p.suffix in {'.json','.md'} and p.name not in {'versions.json','catalogue_manifest.json','verification_v03.json'})
files.extend(p for p in (ROOT/'data/research_curation').rglob('*') if p.is_file() and p.suffix in {'.json','.md','.py'} and '__pycache__' not in p.parts and p.name!='pending_extracts.json' and not p.name.startswith('pending_extracts_'))
with tempfile.TemporaryDirectory() as td:
 target=Path(td)/'catalogue.sqlite3'
 source=sqlite3.connect(ROOT/'data/catalogue.sqlite3');dest=sqlite3.connect(target);source.backup(dest);dest.execute('PRAGMA journal_mode=DELETE');dest.close();source.close()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for path in sorted(set(files)):archive.write(path,'Spice_Atlas_Local_v0.4/'+path.relative_to(ROOT).as_posix())
  archive.write(target,'Spice_Atlas_Local_v0.4/data/catalogue.sqlite3')
print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'files':len(files)+1}))
