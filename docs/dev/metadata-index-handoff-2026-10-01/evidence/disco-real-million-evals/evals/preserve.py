from pathlib import Path
import hashlib,json,sqlite3,sys
ROOT=Path('/private/tmp/disco-real-million-20261001');REPO=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
expected={'workspace_disk_index.py':'bc38a7d0859a0d41edb1fd31b05048211ff4c94a30092003fc1b79b6fa2425a2','workspace_predicates.py':'c8b7a4b44a8c051b0216eaaa939f4278ea591c41772a7ec9af8e8899756aa2bd','workspace_metadata_objects.py':'8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd'}
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as stream:
  for raw in iter(lambda:stream.read(4*1024*1024),b''):h.update(raw)
 return h.hexdigest()
checked={}
for name,value in expected.items():
 actual=sha(REPO/name);assert actual==value,(name,actual,value);checked[str(REPO/name)]=actual
source=Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite');seal=json.loads(Path(str(source)+'.sha256.json').read_text())
assert sha(source)==seal['sha256'];checked[str(source)]=seal['sha256']
base=ROOT/'base.sqlite';seal=json.loads(Path(str(base)+'.sha256.json').read_text());actual=sha(base);assert actual==seal['sha256'];checked[str(base)]=actual
sidecar=ROOT/'typed'/'sidecar.sqlite';checked[str(sidecar)]=sha(sidecar)
# Active mounted source bytes and manifests stay outside experiment ownership.
project=Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
mounted=project/'cache'/'metadata'/'1acbf50ca7fa6ed75946b16eac5db41f06f1d5b4d7030c3f215c033da34a6b2d.sqlite'
if mounted.exists():
 actual=sha(mounted);assert actual==checked[str(source)];checked[str(mounted)]=actual
manifests={}
for kind in ('metadata','source-projections'):
 p=project/'cache'/kind/'.current-generations.json';manifests[str(p)]=dict(sha256=sha(p),contents=json.loads(p.read_text()))
previous=json.loads(Path('/private/tmp/disco-real-typed-sqlite-20261001/evals/v3/receipt.json').read_text())
protected_before={p:value for p,value in previous['input_after'].items() if p.startswith(str(project)+'/cache/')}
protected_after={p:sha(Path(p)) for p in protected_before}
assert protected_before==protected_after,'Mounted cached generations or manifests changed from the real-data snapshot'
final_code={str(p):sha(p) for directory in ('typed','evals') for p in (ROOT/directory).glob('*.py')}
result=dict(all_passed=True,source_base_unchanged=True,mounted_active_metadata_matches_snapshot=mounted.exists(),checked_sha256=checked,final_code_sha256=final_code,mounted_manifests_after=manifests,mounted_protected_before=protected_before,mounted_protected_after=protected_after,mounted_protection_origin='Previous same-project real-data qualification snapshot; unchanged throughout this replay experiment',python=sys.version,sqlite=sqlite3.sqlite_version,policy='Expected current query-source hashes from initial snapshot; real/base file seals verified after all experiments. Mounted source/index files read only; no scientific database exported or canonical annotations written. Final code includes retained v2/v3 and prior batched catalog.')
(ROOT/'evals'/'preservation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(preservation_passed=True,files=len(checked),code_files=len(final_code),sqlite=sqlite3.sqlite_version)),flush=True)
