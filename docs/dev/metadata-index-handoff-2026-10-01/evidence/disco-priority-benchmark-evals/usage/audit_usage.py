"""Read mounted state and HTTP log. No native connection or mounted writes."""
import collections, hashlib, json, pathlib, re, sys, urllib.parse
ROOT = pathlib.Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
OUT = pathlib.Path('/private/tmp/disco-priority-benchmark-20261001/usage')
sys.path.insert(0, '/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
from workspace_state_snapshot import load

def leaves(v):
    if isinstance(v,dict):
        if isinstance(v.get('field'),str):yield v['field']
        for k,w in v.items():
            if k!='field':yield from leaves(w)
    elif isinstance(v,list):
        for w in v:yield from leaves(w)

def fields(v):
    if isinstance(v,str):return [x.strip() for x in v.split(',') if x.strip()]
    if isinstance(v,list):return [x.get('id') if isinstance(x,dict) else x for x in v]
    return []

def item(predicate=None, split=None, **extra):
    return dict(predicate=predicate,predicate_fields=sorted(set(leaves(predicate))),split_fields=fields(split),**extra)

pointer=json.loads((ROOT/'app-state.json').read_text())
state=load(ROOT/pointer['store'])
protocols={v['protocol_uuid']:v['name'] for v in state['protocols'].values()}
current={k:len(v) for k,v in state['tables'].items()}
presets=[];layouts=[];runs=[];revisions=[];exports=[]
for r in state['tables']['search_preset']:
    presets.append(item(r['predicate'],r['splits'],name=r['name'],updated_at=r['updated_at'],actor=r['actor'],identity=r['preset_uuid']))
for r in state['tables']['protocol_tree_layout']:
    layouts.append(item(split=r['split_order'],protocol=protocols.get(r['protocol_uuid'],r['protocol_uuid']),version=r['version'],updated_at=r['updated_at'],actor=r['actor']))
for r in state['tables']['search_query_last_run']:
    w=r['result'];runs.append(item(w.get('predicate'),w.get('splits'),identity=r['query_sha256'],ran_at=w['ran_at'],actor=w['actor'],epoch_count=w['epoch_count']))
for r in state['tables']['explorer_revision']:
    w=r['recipe'];revisions.append(item(w.get('predicate'),w.get('splits'),identity=r['revision_uuid'],name=r['name'],created_at=r['created_at']))
for r in state['tables']['dataset_revision']:
    w=r['recipe'];q=w.get('query',{});o=w.get('options',{});exports.append(item(q.get('predicate',q),o.get('split_order'),identity=r['dataset_uuid'],created_at=r['created_at'],name=o.get('name'),destination=w.get('destination'),evidence='persisted export recipe; duplicated file copy excluded'))

snapshots=[]
for p in sorted((ROOT/'query-snapshots').glob('*/*.json')):
    w=json.loads(p.read_text());snapshots.append(item(w.get('query'),w.get('view',{}).get('group_by'),identity=w['snapshot_uuid'],created_at=w['created_at'],protocol=protocols.get(w['protocol_uuid'],w['protocol_uuid']),epoch_count=len(w['epochs']),source_revisions=w['source_revisions'],stale_source=any(x.startswith('46ee6') for x in w['source_revisions'])))

# Backups are evidence of previous state, never counted as additional actions.
historical=[]
for p in sorted((ROOT/'backups/app-state').glob('*.sqlite')):
    if p.name==pathlib.Path(pointer['store']).name:continue
    s=load(p);historical.append({'file':p.name,'table_counts':{k:len(v) for k,v in s['tables'].items()},'layouts':[item(split=r['split_order'],protocol=protocols.get(r['protocol_uuid'],r['protocol_uuid']),version=r['version'],updated_at=r['updated_at']) for r in s['tables']['protocol_tree_layout']], 'runs_with_predicate':[item(w['result'].get('predicate'),w['result'].get('splits'),identity=w['query_sha256'],ran_at=w['result'].get('ran_at')) for w in s['tables']['search_query_last_run'] if w['result'].get('predicate')]})

log=ROOT/'logs/app-jobs/server.log';counts=collections.Counter();success=collections.Counter();splitsets=collections.Counter();scope_splits=collections.defaultdict(collections.Counter);predfields=collections.Counter();queries=collections.Counter();params=collections.Counter();timestamps=[]
pattern=re.compile(r'(GET|POST|PATCH|PUT|DELETE) ([^ ]+) HTTP/[^" ]+"\s+(\d+)')
for line in log.open():
    m=pattern.search(line)
    if not m:continue
    method,url,status=m.groups();status=int(status);u=urllib.parse.urlsplit(url);endpoint=re.sub(r'/[0-9a-f-]{36}(?=/|$)','/<uuid>',u.path);counts[method+' '+endpoint]+=1
    timestamps.append(line[:23]);q=urllib.parse.parse_qs(u.query)
    if status>=400:continue
    success[method+' '+endpoint]+=1
    for k in q:params[k]+=1
    if 'splits' in q:
        v=q['splits'][0];splitsets[v]+=1
        pm=re.search('/protocols/([0-9a-f-]{36})/',u.path);scope=protocols.get(pm[1],pm[1]) if pm else 'explore/global'
        scope_splits[scope][v]+=1
    if 'field' in q:predfields[q['field'][0]]+=1
    if 'q' in q and '/search' in u.path:queries[q['q'][0]]+=1

observed=set()
for w in [*presets,*layouts,*runs,*revisions,*exports]:observed.update(w['predicate_fields']);observed.update(w['split_fields'])
for split in splitsets:observed.update(fields(split))
for f in predfields:observed.add(f)
result={'scope':'read-only mounted current recovery mirror + retained checkpoints + saved snapshots + HTTP access log; no native MySQL read', 'project':ROOT.name,'engines':{'canonical':'DataJoint over native MySQL; science schema and recording_workspace','derived_query_metadata':'immutable SQLite EAV cache','durable_current_state':'SQLite compressed recovery mirror; authoritative MySQL current rows'}, 'current_table_counts':current,'current_presets':presets,'current_layouts':layouts,'last_run_records':runs,'current_bound_revisions':revisions,'export_recipes':exports,'query_snapshots':snapshots,'historical_backups_not_additional_actions':historical,'http_log':{'first':min(timestamps),'last':max(timestamps),'endpoint_request_counts':dict(counts),'endpoint_success_counts':dict(success),'successful_split_request_counts':dict(splitsets),'successful_split_counts_by_scope':{k:dict(v) for k,v in scope_splits.items()},'successful_explicit_field_parameter_counts':dict(predfields),'successful_search_text_counts':dict(queries),'query_parameter_name_counts':dict(params)},'candidate_observed_union':sorted(observed),'limitations':['HTTP counts include refreshes/retries and cannot identify human versus test/browser automation. They are request counts, not daily operation frequency.','POST bodies are absent: tree-pages and metadata preview requests do not expose fields in access log.','Last-run record overwrites older runs; 6 of 10 lack predicate/splits, so hashes do not recover those fields.','Recovery captures current bound revisions, not entire native SQL explorer/event history.','Five old query snapshots refer to deleted duplicate import SHA46ee..., and are frozen baselines, not current source population.','Exports and checkpoints are duplicate representations; not added to query usage counts.','Current _event skips tree-layout/search-query/preset/curation audit rows by design; their latest states are recovered through the mirror.','One current annotation row has zero tags; dense million-tag workload unobserved.']}
normalized=set(observed)
for v in list(normalized):
    if v.startswith('joint/'):
        normalized.update(urllib.parse.unquote(x) for x in v[6:].split('+'))
        normalized.remove(v)
normalized.discard('metadata/cell/properties/type')
normalized.add('cell type')
result['candidate_observed_normalized_underlying_fields']=sorted(normalized)
result['http_log']['successful_split_requests_total']=sum(splitsets.values())
result['input_receipts']=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [ROOT/'app-state.json',ROOT/pointer['store'],log]]
OUT.mkdir(exist_ok=True,parents=True);(OUT/'usage.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'counts':current,'observed_union':sorted(observed),'splits':dict(splitsets),'explicit_fields':dict(predfields),'search_texts':dict(queries)},indent=2))
