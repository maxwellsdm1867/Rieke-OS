import sys,os,time,json,statistics,threading,tempfile,signal,traceback,hashlib,datetime
from pathlib import Path
SOURCE=Path('/private/tmp/rieke-os-issues-20260930/repo');OUT=Path('/private/tmp/disco-everyday-bench-20261001/native');sys.path[:0]=[str(SOURCE/'python'),str(SOURCE/'docs/dev/scale-audit-2026-09-29')]
from benchmark_service_scale import fixture,uid
from workspace_projects import create_project
from recording_workspace import connect,workspace_tables
import workspace_native_mysql as native
from workspace_mysql_runtime import _probe,runtime_spec
from workspace_disk_index import DiskMetadataIndex
from workspace_api import create_app
from workspace_protocol_state import ProtocolStateReader
from werkzeug.serving import make_server
report={'head':'a8fac2c293ccf4fa73a4eb5e93673b41620b1d13','epochs':100000,'scope':'Actual native MySQL8.4.2 and current Flask/WorkspaceService with sealed synthetic100k metadata index; empty saved annotations/default curation; no SQL doubles, no H5/waveform I/O, no private files.','started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':[],'checks':[],'phases':{},'oracle_calls':0}
output=OUT/'native-metadata-100k.json';app=dj=index=server=None;project=None;start=time.perf_counter()
def save():output.write_text(json.dumps(report,indent=2,default=str))
def cap(signum,frame):signal.alarm(0);raise TimeoutError('Native metadata experiment300second cap')
signal.signal(signal.SIGALRM,cap);signal.alarm(300)
def log(stage):print(json.dumps({'stage':stage,'elapsed':time.perf_counter()-start}),flush=True);report['phase']=stage;save()
def phase(label,call):log(label);beg=time.perf_counter();v=call();report['phases'][label]=time.perf_counter()-beg;save();return v
original_oracle=ProtocolStateReader._oracle
def oracle(self,*args,**kwargs):report['oracle_calls']+=1;return original_oracle(self,*args,**kwargs)
# Observe only fallback oracle calls; the native contract does not inspect _oracle.
ProtocolStateReader._oracle=oracle
runtime=_probe(Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/mysql'),runtime_spec(SOURCE)[0]['mysql_version'])
native.native_binary=lambda name='mysqld':Path(runtime[name])
try:
 with tempfile.TemporaryDirectory(prefix='disco-native-metadata-') as temp:
  try:
   project=Path(create_project(Path(temp)/'projects','Disposable native metadata benchmark')['path'])
   service,protocol=phase('synthetic_model',lambda:fixture(100000))
   # Align own newly created project descriptor with the preexisting synthetic index identity.
   for relative in['project.json','catalog.json','database/service.json','storage.json','logs/storage/project-created.json']:
    p=project/relative;v=json.loads(p.read_text());v['project_uuid']=service.project['project_uuid']
    if 'managed_database' in v:v['managed_database']['project_uuid']=service.project['project_uuid']
    p.write_text(json.dumps(v,indent=2)+'\n')
   phase('owned_native_boot',lambda:native.ensure_native_database(project));dj=connect({'kind':'native-project'},project_dir=project)
   service.project_dir=project;service.project=json.loads((project/'project.json').read_text());service.config=json.loads((project/'catalog.json').read_text());service.dj=dj
   service.manifests={s['source_sha256']:{'source_path':'/synthetic/'+s['filename']} for s in service.sources}
   for entry in service.protocols.values():entry['definition']['project_uuid']=service.project['project_uuid']
   index=phase('existing_sealed_index_open',lambda:DiskMetadataIndex.open(Path('/private/tmp/disco-everyday-bench-20261001/metadata/100000/index.sqlite'),'everyday-100000',service.project['project_uuid']))
   service.disk_index=index;service.details=index.details
   Project,*_=workspace_tables(dj);Project.insert1({'project_uuid':service.project['project_uuid'],'name':service.project['name'],'directory':str(project)})
   app=phase('normal_create_app_empty_native_annotations',lambda:create_app(project,SOURCE/'.rieke-runtime/retinanalysis',service=service))
   reader=app.extensions['protocol_state_reader'];context=phase('native_context_first_proof',lambda:reader.native_context(protocol));report['native_contract']=reader._native_contract();report['native_context_ready']=context is not None;report['native_context_contract']=context and context['query_revision_contract'];report['annotation_preparation']=service.annotation_preparation
   if not context:raise AssertionError('Actual native context unavailable; stop and report fixture limitation')
   client=app.test_client();headers={'X-Workspace-Request':'1','Origin':'http://localhost:8766'};base='/api/protocols/'+protocol
   def get(path):
    r=client.get(path);v=r.get_json();assert r.status_code==200,(path,r.status_code,v);return v
   def post(path,body):
    r=client.post(path,json=body,headers=headers);v=r.get_json();assert r.status_code==200,(path,r.status_code,v);return v
   def timed(name,call,check):
    log(name);samples=[];before=report['oracle_calls'];value=None
    for i in range(3):
     began=time.perf_counter();value=call();samples.append(time.perf_counter()-began);assert check(value),(name,value)
    report['operations'].append({'name':name,'samples_seconds':samples,'median_seconds':statistics.median(samples),'maximum_seconds':max(samples),'oracle_calls':report['oracle_calls']-before,'bytes':len(json.dumps(value).encode()),'exact_oracle_passed':True});save();return value
   ids=list(service.rows);epoch=ids[0]
   timed('api_epoch_first_60',lambda:get(base+'/epochs?limit=60'),lambda v:v['total']==100000 and [r['epoch_uuid'] for r in v['epochs']]==ids[:60])
   timed('api_epoch_next_60',lambda:get(base+'/epochs?limit=60&offset=60'),lambda v:v['total']==100000 and [r['epoch_uuid'] for r in v['epochs']]==ids[60:120])
   body={'protocol_uuid':protocol,'splits':'date,cell,block','limit':60}
   tree=timed('api_tree_root',lambda:post('/api/tree-pages',body),lambda v:v['count']==100000 and len(v['branches'])==1)
   datebody={**body,'path':tree['branches'][0]['path'],'revision':tree['revision']}
   date=timed('api_tree_expand_date',lambda:post('/api/tree-pages',datebody),lambda v:v['total']==1000 and len(v['branches'])==60)
   cellbody={**body,'path':date['branches'][0]['path'],'revision':tree['revision']}
   cell=timed('api_tree_expand_cell',lambda:post('/api/tree-pages',cellbody),lambda v:v['selection']['count']==100 and len(v['branches'])==5)
   blockbody={**body,'path':cell['branches'][0]['path'],'revision':tree['revision']}
   timed('api_tree_expand_block',lambda:post('/api/tree-pages',blockbody),lambda v:v['total']==20 and len(v['epochs'])==20)
   timed('api_epoch_details',lambda:get('/api/epochs/'+epoch+'?protocol_uuid='+protocol),lambda v:v['epoch_uuid']==epoch and v['parameters']['seed']==0)
   timed('api_overview',lambda:get('/api/overview'),lambda v:v['counts']['epochs']==100000)
   pred={'field':'parameters/contrast','operator':'eq','value':.3}
   timed('api_contrast_filter_preview',lambda:post('/api/explore/preview',{'predicate':pred,'splits':'date,cell,block','summary_only':True}),lambda v:v['matched_count']==20000)
   report['backend_passed']=True;report['checks'].append({'name':'native_context_ready_without_contract_override','passed':True});report['checks'].append({'name':'zero_legacy_oracle_calls','passed':report['oracle_calls']==0});save()
   server=make_server('127.0.0.1',0,app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
   config={'epochs':100000,'source_head':report['head'],'protocol_uuid':protocol,'api_origin':'http://127.0.0.1:'+str(server.server_port),'catalog':index.catalog(),'scope':report['scope'],'pid':os.getpid()};(OUT/'native-metadata-browser-config.json').write_text(json.dumps(config,indent=2));log('native_browser_server_ready')
   deadline=time.monotonic()+150
   while not(OUT/'native-browser-done').exists() and time.monotonic()<deadline:time.sleep(.5)
   report['browser_done_signal']=(OUT/'native-browser-done').exists()
  finally:
   if server:server.shutdown();server.server_close()
   if app:
    scheduler=app.extensions.get('backup_scheduler')
    if scheduler:scheduler.flush();scheduler.close(flush=False)
    lock=app.extensions.get('app_state_session_lock')
    if lock:lock.close()
   if index:index.close()
   if dj:dj.conn().close()
   if project:report['owned_native_runtime_stopped']=native.stop_native_database(project)
except BaseException as e:report['error']=str(e);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
finally:
 signal.alarm(0);report['seconds']=time.perf_counter()-start;report['passed']=bool(report.get('backend_passed')) and report.get('owned_native_runtime_stopped') and not report.get('error');save();print(json.dumps({'done':True,'passed':report['passed'],'seconds':report['seconds']}),flush=True)
