"""Shared source selection and incremental-update manifests."""
from __future__ import annotations
import io,json,subprocess,tarfile,tomllib,zipfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from update import ROOT_FILES,managed_path,digest,canonical,UpdateError
BASE_REF='9e02c9fdaaf6a106e05ed37acfa5928b8640f4d8'
BUILD='0.7.0'
def release_files(root=ROOT):
    files=[]
    for folder in ('atlas','desktop','static','scripts','tests','docs','browser_helper'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and 'node_modules' not in p.parts)
    files.extend(root/p for p in ROOT_FILES if (root/p).is_file())
    files.extend(p for p in (root/'data').glob('*') if p.is_file() and p.suffix in {'.json','.md'} and p.name not in {'versions.json','catalogue_manifest.json','verification_v03.json','install_state.json'})
    for folder in ('source_research','research_curation'):
        files.extend(p for p in (root/'data'/folder).rglob('*') if p.is_file() and p.suffix in {'.json','.jsonl','.md','.py'} and '__pycache__' not in p.parts and not p.name.startswith('pending_extracts'))
    return sorted(set(files))
def release_bytes(path):
    raw=path.read_bytes()
    return canonical(raw).replace(b'\n',b'\r\n') if path.suffix=='.cmd' else raw
def git_files(ref=BASE_REF):
    raw=subprocess.check_output(['git','archive',ref],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:return {p.name:archive.extractfile(p).read() for p in archive.getmembers() if p.isfile()}
def archived_files(path):
    if not path or not Path(path).exists():return {}
    with zipfile.ZipFile(path) as archive:return {n.split('/',1)[1]:archive.read(n) for n in archive.namelist() if '/' in n and not n.endswith('/')}
def dependency_signature(files):
    project=tomllib.loads(files['pyproject.toml'].decode())['project'];lock=tomllib.loads(files['uv.lock'].decode()) if 'uv.lock' in files else {}
    return {'requires_python':project['requires-python'],'requirements':sorted(project['dependencies']),'resolved':sorted((p['name'],p.get('version','')) for p in lock.get('package',[]) if p['name']!=project['name'])}
def update_manifest(files,previous=None,base_ref=BASE_REF,base_release=None):
    previous_paths=([previous] if isinstance(previous,(str,Path)) else previous) or []
    baseline=git_files(base_ref);priors=[archived_files(p) for p in previous_paths];published=archived_files(base_release);current={p.relative_to(ROOT).as_posix():release_bytes(p) for p in files}
    before_version=tomllib.loads(baseline['pyproject.toml'].decode())['project']['version'];version=tomllib.loads(current['pyproject.toml'].decode())['project']['version'];rows=[]
    if (before_version,version)!=('0.6.0','0.7.0'):raise UpdateError('This release builder has only the reviewed 0.6→0.7 recipe. Add real migration steps before producing another version.')
    if base_release:
        if not published or tomllib.loads(published['pyproject.toml'].decode())['project']['version']!=before_version:raise UpdateError('The published baseline archive must be the actual 0.6.0 release')
    supported=[snapshot for snapshot in [baseline,published,*priors] if snapshot]
    for name,raw in current.items():
        old=baseline.get(name)
        if all(snapshot.get(name)==raw for snapshot in supported):continue
        try:managed_path(name)
        except UpdateError:
            if name.startswith('data/') and old==raw:continue
            raise
        known=[snapshot[name] for snapshot in supported if name in snapshot]+[raw]
        rows.append({'path':name,'source':name,'sha256':digest(raw),'before_sha256':list(dict.fromkeys(digest(canonical(x)) for x in known)),'before_missing':any(name not in snapshot for snapshot in supported)})
    for name in sorted(set().union(*(snapshot.keys() for snapshot in supported))):
        if name in current:continue
        try:managed_path(name)
        except UpdateError:continue
        rows.append({'path':name,'delete':True,'before_sha256':list(dict.fromkeys(digest(canonical(snapshot[name])) for snapshot in supported if name in snapshot)),'before_missing':True})
    deps=dependency_signature(baseline)!=dependency_signature(current)
    manifest={'format':1,'app_id':'spice-atlas-local','target_version':version,'build':BUILD,'base_commit':base_ref,'steps':[{'id':'v'+before_version+'-to-v'+version,'from_versions':list(dict.fromkeys([before_version,version])),'to_version':version,'migration':'preserve-workspaces-v1','dependencies_changed':deps,'files':rows}]}
    if base_release:manifest['base_release_sha256']=digest(Path(base_release).read_bytes())
    if previous_paths:manifest['previous_candidates_sha256']=[digest(Path(p).read_bytes()) for p in previous_paths]
    return manifest
