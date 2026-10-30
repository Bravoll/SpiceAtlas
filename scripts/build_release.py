"""Build a portable release plus an in-place update manifest."""
import argparse,json,sqlite3,tempfile,zipfile,sys,tomllib
from pathlib import Path
from release_support import ROOT,release_files,release_bytes,update_manifest
sys.path.insert(0,str(ROOT))
from atlas.seed import ensure_baseline

def build(out=None,previous=None,base_release=None):
    ensure_baseline(ROOT/'data/catalogue.sqlite3')
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version'];label='Spice_Atlas_Local_v'+'.'.join(version.split('.')[:2]);out=Path(out or ROOT.parent/(label+'.zip'))
    files=release_files();manifest=update_manifest(files,previous,base_release=base_release)
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary)/'catalogue.sqlite3';source=sqlite3.connect(ROOT/'data/catalogue.sqlite3');destination=sqlite3.connect(target)
        source.backup(destination);destination.execute('PRAGMA journal_mode=DELETE');destination.close();source.close()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in files:archive.writestr(label+'/'+path.relative_to(ROOT).as_posix(),release_bytes(path))
            archive.write(target,label+'/data/catalogue.sqlite3')
            archive.writestr(label+'/update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return {'path':str(out),'version':version,'bytes':out.stat().st_size,'files':len(files)+2,'update_files':len(manifest['steps'][0]['files']),'dependencies_changed':manifest['steps'][0]['dependencies_changed']}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',nargs='?');parser.add_argument('--previous-release',action='append');parser.add_argument('--base-release');args=parser.parse_args();print(json.dumps(build(args.output,args.previous_release,args.base_release)))
