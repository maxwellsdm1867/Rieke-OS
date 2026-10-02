import sys,os,time,json,statistics,threading,tempfile,signal,traceback,hashlib,datetime,argparse,subprocess,shutil
from pathlib import Path
parser=argparse.ArgumentParser(description="Real native everyday-action evaluation; disposable data only")
parser.add_argument('--source-root',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--mysql-runtime-root',type=Path,required=True)
parser.add_argument('--index',type=Path,required=True)
parser.add_argument('--samples',type=int,default=10)
parser.add_argument('--serve-browser',action='store_true')
parser.add_argument('--browser-wait-seconds',type=int,default=150)
parser.add_argument('--cap-seconds',type=int,default=300)
args=parser.parse_args()
SOURCE=args.source_root.resolve(strict=True);OUT=args.output_dir.resolve();OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'native-metadata-100k.json').exists():parser.error('Choose an unused output directory')
if args.samples<1:parser.error('samples must be positive')
os.environ['RIEKE_PREFERENCES_DIR']=str(OUT/'preferences')
os.environ['RIEKE_PROJECT_INDEX']=str(OUT/'preferences'/'project-index.json')
os.environ['RIEKE_USER_PREFERENCES_PATH']=str(OUT/'preferences.json')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(SOURCE/'python'),str(SOURCE/'docs/dev/scale-audit-2026-09-29')]
def inventory():return {str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((SOURCE/'python').rglob('*.py'))}
source_inventory_before=inventory()
source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
source_diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff','--','python','workspace-app/src'],cwd=SOURCE)).hexdigest()
from benchmark_service_scale import fixture,uid
from workspace_projects import create_project
from recording_workspace import connect,workspace_tables
import workspace_native_mysql as native
from workspace_mysql_runtime import _probe,runtime_spec
from workspace_disk_index import DiskMetadataIndex
from workspace_api import create_app
from workspace_protocol_state import ProtocolStateReader
from werkzeug.serving import make_server
report={'head':source_head,'source_root':str(SOURCE),'source_inventory_before':source_inventory_before,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'samples':args.samples,'epochs':100000,'scope':'Actual native MySQL8.4.2 and current Flask/WorkspaceService with sealed synthetic100k metadata index; empty saved annotations/default curation; no SQL doubles, no H5/waveform I/O, no private files.','started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'operations':[],'checks':[],'phases':{},'oracle_calls':0}
report['product_diff_sha256']=source_diff_sha256
output=OUT/'native-metadata-100k.json';app=dj=index=server=None;project=None;start=time.perf_counter()
def save():output.write_text(json.dumps(report,indent=2,default=str))
def cap(signum,frame):signal.alarm(0);raise TimeoutError(f'Native metadata experiment {args.cap_seconds} second cap')
signal.signal(signal.SIGALRM,cap);signal.alarm(args.cap_seconds)
def log(stage):print(json.dumps({'stage':stage,'elapsed':time.perf_counter()-start}),flush=True);report['phase']=stage;save()
def phase(label,call):log(label);beg=time.perf_counter();v=call();report['phases'][label]=time.perf_counter()-beg;save();return v
original_oracle=ProtocolStateReader._oracle
def oracle(self,*args,**kwargs):report['oracle_calls']+=1;return original_oracle(self,*args,**kwargs)
# Observe only fallback oracle calls; the native contract does not inspect _oracle.
ProtocolStateReader._oracle=oracle
runtime=_probe(args.mysql_runtime_root.resolve(strict=True),runtime_spec(SOURCE)[0]['mysql_version'])
native.native_binary=lambda name='mysqld':Path(runtime[name])
try:
 with tempfile.TemporaryDirectory(prefix='owned-project-',dir=OUT) as temp:
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
   copied_index=OUT/'fixture-index'/'index.sqlite';copied_index.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(args.index.resolve(strict=True),copied_index);shutil.copy2(str(args.index.resolve(strict=True))+'.sha256.json',str(copied_index)+'.sha256.json')
   report['fixture_index_sha256']=hashlib.sha256(copied_index.read_bytes()).hexdigest()
   index=phase('existing_sealed_index_open',lambda:DiskMetadataIndex.open(copied_index,'everyday-100000',service.project['project_uuid']))
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
    for i in range(args.samples):
     began=time.perf_counter();value=call();samples.append(time.perf_counter()-began);assert check(value),(name,value)
    report['operations'].append({'name':name,'samples_seconds':samples,'first_seconds':samples[0],'warm_median_seconds':statistics.median(samples[1:]) if len(samples)>1 else None,'median_seconds':statistics.median(samples),'maximum_seconds':max(samples),'oracle_calls':report['oracle_calls']-before,'bytes':len(json.dumps(value).encode()),'exact_oracle_passed':True});save();return value
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
   timed('api_tree_expand_block',lambda:post('/api/tree-pages',blockbody),lambda v:v['total']==20 and [r['epoch_uuid'] for r in v['epochs']]==[key for key,row in service.rows.items() if row['block_uuid']==v['epochs'][0]['block_uuid']])
   timed('api_epoch_details',lambda:get('/api/epochs/'+epoch+'?protocol_uuid='+protocol),lambda v:v['epoch_uuid']==epoch and v['parameters']=={'contrast':0.,'seed':0,'stimTime':1000,'currentMean':0})
   timed('api_overview',lambda:get('/api/overview'),lambda v:v['counts']['epochs']==100000)
   pred={'field':'parameters/contrast','operator':'eq','value':.3}
   timed('api_contrast_filter_preview',lambda:post('/api/explore/preview',{'predicate':pred,'splits':'date,cell,block','summary_only':True}),lambda v:v['matched_count']==20000)
   report['backend_passed']=True;report['checks'].append({'name':'native_context_ready_without_contract_override','passed':True});report['checks'].append({'name':'zero_legacy_oracle_calls','passed':report['oracle_calls']==0});save()
   if args.serve_browser:
    server=make_server('127.0.0.1',0,app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
    config={'epochs':100000,'source_head':report['head'],'protocol_uuid':protocol,'api_origin':'http://127.0.0.1:'+str(server.server_port),'catalog':index.catalog(),'scope':report['scope'],'pid':os.getpid()};(OUT/'native-metadata-browser-config.json').write_text(json.dumps(config,indent=2));log('native_browser_server_ready')
    deadline=time.monotonic()+args.browser_wait_seconds
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
 signal.alarm(0);report['seconds']=time.perf_counter()-start;report['source_inventory_after']=inventory();report['source_unchanged']=source_inventory_before==report['source_inventory_after'];report['passed']=report['source_unchanged'] and report.get('oracle_calls')==0 and bool(report.get('backend_passed')) and report.get('owned_native_runtime_stopped') and not report.get('error');save();print(json.dumps({'done':True,'passed':report['passed'],'seconds':report['seconds']}),flush=True)
