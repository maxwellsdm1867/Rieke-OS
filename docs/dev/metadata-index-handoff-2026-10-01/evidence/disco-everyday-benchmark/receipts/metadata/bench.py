from __future__ import annotations
import argparse, datetime, gc, hashlib, json, os, platform, resource, shutil, statistics, sys, threading, time, traceback
from pathlib import Path
SOURCE=Path('/private/tmp/rieke-os-issues-20260930/repo')
sys.path[:0]=[str(SOURCE/'python'),str(SOURCE/'python/tests'),str(SOURCE/'docs/dev/scale-audit-2026-09-29')]
import psutil
from benchmark_service_scale import fixture,Details
from workspace_disk_index import DiskMetadataIndex
from workspace_tree_pages import TreePages
from test_workspace_api import WorkspaceAPITests

parser=argparse.ArgumentParser();parser.add_argument('--epochs',type=int,required=True);parser.add_argument('--serve',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--diagnostics-only',action='store_true');args=parser.parse_args()
root=Path(__file__).parent;folder=root/str(args.epochs);folder.mkdir(exist_ok=True)
output=folder/'receipt.json';progress=folder/'progress.json';process=psutil.Process()
if args.diagnostics_only:output=folder/'diagnostics.json';progress=folder/'diagnostics-progress.json'
report={'epochs':args.epochs,'source_head':'a8fac2c293ccf4fa73a4eb5e93673b41620b1d13','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':platform.python_version(),'platform':platform.platform(),'scope':'Synthetic metadata: actual current WorkspaceService, sealed SQLite index and production Flask routes. API saved-curation/database hooks use existing transactional test SQL doubles with empty tables; no MySQL latency, H5 source I/O, waveforms, dense annotations or user files.','phases':[],'operations':[],'status':'running','resource_samples':[]}
lock=threading.RLock();phase='imports';phase_started=time.monotonic();start=phase_started;stopped=False
if args.resume:
    previous=json.loads(output.read_text());report['operations']=previous['operations'];report['prior_attempt']=str(folder/'prior-attempt.json');report['resume_reason']='Benchmark oracle expected private membership removed by actual HTTP route; corrected oracle uses matched_count.'
    (folder/'prior-attempt.json').write_text(json.dumps(previous,indent=2))
def rss():return process.memory_info().rss/1024**2
def save():
    with lock:
        output.with_suffix('.tmp').write_text(json.dumps(report,indent=2,default=str));output.with_suffix('.tmp').replace(output)
        progress.write_text(json.dumps({'phase':phase,'phase_seconds':time.monotonic()-phase_started,'rss_mib':rss(),'status':report['status'],'operations':len(report['operations'])}))
def enter(name):
    global phase,phase_started
    phase=name;phase_started=time.monotonic();save();print(json.dumps({'phase':name,'epochs':args.epochs,'rss_mib':rss()}),flush=True)
def watch():
    while not stopped:
        time.sleep(2)
        sample={'elapsed_seconds':time.monotonic()-start,'rss_mib':rss(),'rusage_maxrss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if platform.system()=='Darwin' else 1024),'available_mib':psutil.virtual_memory().available/1024**2,'disk_free_gib':shutil.disk_usage(folder).free/1024**3}
        with lock:report['resource_samples'].append(sample)
        reason=None
        if sample['rss_mib']>1700:reason='owned worker RSS exceeds 1700 MiB'
        elif sample['available_mib']<600:reason='system available memory below 600 MiB'
        elif sample['disk_free_gib']<4:reason='free disk below 4 GiB'
        elif phase=='index_build' and time.monotonic()-phase_started>240:reason='index build exceeded 240 seconds'
        elif phase!='browser_server' and time.monotonic()-start>600:reason='scale worker exceeded 600 seconds'
        if reason:
            report.update(status='resource_guard_stopped',stop_reason=reason,stop_phase=phase);save();print(json.dumps({'stopped':reason}),flush=True);os._exit(75)
        save()
threading.Thread(target=watch,daemon=True).start()

def record_phase(name,call):
    enter(name);beg=time.perf_counter();result=call();report['phases'].append({'name':name,'seconds':time.perf_counter()-beg,'rss_mib':rss()});save();return result
def timed(name,call,oracle,layer):
    if any(entry['name']==name for entry in report['operations']):
        value=call();assert oracle(value);return value
    enter(name);samples=[];sizes=[]
    for repeat in range(3 if args.epochs>=500000 and not args.diagnostics_only else 6):
        gc.collect();beg=time.perf_counter();value=call();elapsed=time.perf_counter()-beg
        assert oracle(value),(name,'oracle failed',str(value)[:500]);samples.append(elapsed);sizes.append(len(json.dumps(value,separators=(',',':'),default=str).encode()))
        save()
    record={'name':name,'layer':layer,'first_seconds':samples[0],'warm_samples_seconds':samples[1:],'warm_median_seconds':statistics.median(samples[1:]),'warm_max_seconds':max(samples[1:]),'response_json_bytes':sizes[-1],'response_json_bytes_samples':sizes,'rss_mib':rss(),'oracle_passed':True}
    report['operations'].append(record);save();print(json.dumps(record),flush=True);return value

api=None
try:
    service,protocol=record_phase('synthetic_model_generation',lambda:fixture(args.epochs))
    generation='everyday-'+str(args.epochs)
    report['index_existed_before_run']=(folder/'index.sqlite').exists()
    index=record_phase('index_build',lambda:DiskMetadataIndex.build(folder/'index.sqlite',service.rows,Details(service.rows),service.sources,generation,service.project['project_uuid']))
    report['index_bytes']=index.path.stat().st_size
    index.close()
    index=record_phase('persistent_index_reopen',lambda:DiskMetadataIndex.open(folder/'index.sqlite',generation,service.project['project_uuid']))
    service.disk_index,service.details=index,index.details
    api=WorkspaceAPITests();api.setUp();target=api.service
    for name in ('rows','details','cells','sources','_fingerprints','disk_index'):setattr(target,name,getattr(service,name))
    target.protocols={target.protocol_id:service.protocols[protocol]};target.protocols[target.protocol_id]['result']['protocol_uuid']=target.protocol_id
    target.protocols[target.protocol_id]['definition'].update(protocol_uuid=target.protocol_id,project_uuid=target.project['project_uuid'])
    target.ids=list(target.rows)[:2];target.cell_ids=list(target.cells)[:2]
    # Keep production index/project identity consistent with the actual test route provider.
    target.project=service.project;api.store.project_uuid=target.project['project_uuid']
    for source in target.sources:source.update(source_path=str(folder/source['filename']),counts={'epochs':args.epochs//10,'cells':args.epochs//1000})
    target.manifests={source['source_sha256']:{'source_path':source['source_path']} for source in target.sources}
    epoch=next(iter(target.rows));pred={'field':'parameters/contrast','operator':'eq','value':.3}
    pager=TreePages(target);base={'protocol_uuid':target.protocol_id,'splits':'date,cell,block','limit':60}
    if args.diagnostics_only:
        import cProfile,pstats,sqlite3
        diagnostics=[]
        for name,call in [('api_epoch_page_60',lambda:api.client.get(api.base+'/epochs?limit=60')),('api_contrast_preview',lambda:api.client.post('/api/explore/preview',json={'predicate':pred,'splits':'date,cell,block','summary_only':True},headers=api.headers))]:
            enter('profile_'+name);warm=call();assert warm.status_code==200,warm.get_json()
            profiler=cProfile.Profile();beg=time.perf_counter();profiler.enable();response=call();response.get_json();profiler.disable();assert response.status_code==200
            stats=pstats.Stats(profiler)
            diagnostics.append({'name':name,'profiled_wall_seconds':time.perf_counter()-beg,'top_cumulative':[{'file':Path(key[0]).name,'line':key[1],'function':key[2],'primitive_calls':val[0],'calls':val[1],'self_seconds':val[2],'cumulative_seconds':val[3]} for key,val in sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:30]]})
        report['profiles']=diagnostics
        connection=sqlite3.connect('file:'+str(index.path)+'?mode=ro',uri=True)
        field=connection.execute('SELECT field_no FROM fields WHERE field_id=?',('parameters/contrast',)).fetchone()[0]
        value=connection.execute('SELECT value_id FROM field_values WHERE field_no=? AND value_json=?',(field,'0.3')).fetchone()[0]
        expected=list(target.rows)[:60]
        wanted=[identity for identity,row in target.rows.items() if row['synthetic_index']%5==3][:60]
        report['sql_control_scope']='Diagnostic control only, not an application implementation. SELECT on actual sealed SQLite metadata index, indexed epoch_id order equals synthetic protocol insertion order. Contrast count and page use values_reverse(field_no,value_id,epoch_id). Includes row JSON decode; excludes global curation and recipe revisions.'
        def epoch_control():return [json.loads(row[0]) for row in connection.execute('SELECT row_json FROM epochs ORDER BY epoch_id LIMIT 60')]
        def contrast_control():
            count=connection.execute('SELECT COUNT(*) FROM epoch_values WHERE field_no=? AND value_id=?',(field,value)).fetchone()[0]
            rows=[json.loads(row[0]) for row in connection.execute('SELECT e.row_json FROM epoch_values v JOIN epochs e ON e.epoch_id=v.epoch_id WHERE v.field_no=? AND v.value_id=? ORDER BY v.epoch_id LIMIT 60',(field,value))]
            return {'count':count,'epochs':rows}
        timed('control_sql_epoch_first_60',epoch_control,lambda v:[row['epoch_uuid'] for row in v]==expected,'indexed SQLite diagnostic control')
        timed('control_sql_contrast_count_first_60',contrast_control,lambda v:v['count']==args.epochs//5 and [row['epoch_uuid'] for row in v['epochs']]==wanted,'indexed SQLite diagnostic control')
        report['query_plans']={'epoch':[list(row) for row in connection.execute('EXPLAIN QUERY PLAN SELECT row_json FROM epochs ORDER BY epoch_id LIMIT 60')],'contrast':[list(row) for row in connection.execute('EXPLAIN QUERY PLAN SELECT e.row_json FROM epoch_values v JOIN epochs e ON e.epoch_id=v.epoch_id WHERE v.field_no=? AND v.value_id=? ORDER BY v.epoch_id LIMIT 60',(field,value))]}
        connection.close();report.update(status='complete');save();stopped=True;api.doCleanups();index.close();os._exit(0)
    # Loopback server exposes the exact same production routes measured below.
    if args.serve:
        from werkzeug.serving import make_server
        server=make_server('127.0.0.1',0,api.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        config={'epochs':args.epochs,'source_head':report['source_head'],'protocol_uuid':target.protocol_id,'api_origin':'http://127.0.0.1:'+str(server.server_port),'catalog':index.catalog(),'scope':report['scope'],'pid':os.getpid()}
        (root/'browser-config.json').write_text(json.dumps(config,indent=2));print(json.dumps({'browser_ready':config['api_origin'],'config':str(root/'browser-config.json')}),flush=True)
    if args.epochs<500000:
        timed('service_epoch_first_60',lambda:target.epoch_page(target.protocol_id,limit=60),lambda v:v['total']==args.epochs and len(v['epochs'])==60,'service')
        timed('service_epoch_next_60',lambda:target.epoch_page(target.protocol_id,offset=60,limit=60),lambda v:v['total']==args.epochs and len(v['epochs'])==60 and v['offset']==60,'service')
        timed('service_exact_epoch_predicate',lambda:target.match_predicate({'field':'epoch','operator':'eq','value':epoch}),lambda v:len(v[1])==1 and epoch in v[1],'service')
        timed('service_contrast_preview_summary',lambda:target.explore_preview(pred,'date,cell,block',include_tree=False),lambda v:v['count']==args.epochs//5 if 'count' in v else len(v['membership'])==args.epochs//5,'service')
        timed('service_epoch_details',lambda:target.epoch(epoch),lambda v:v['epoch_uuid']==epoch,'service')
        timed('service_overview',target.overview,lambda v:v['counts']['epochs']==args.epochs,'service')
    def get(path):
        response=api.client.get(path);assert response.status_code==200,(path,response.status_code,response.get_json());return response.get_json()
    def post(path,body):
        response=api.client.post(path,json=body,headers=api.headers);assert response.status_code==200,(path,response.status_code,response.get_json());return response.get_json()
    layer='production Flask + JSON decode; empty-curation SQL doubles'
    timed('api_epoch_first_60',lambda:get(api.base+'/epochs?limit=60'),lambda v:v['total']==args.epochs and len(v['epochs'])==60,layer)
    timed('api_epoch_next_60',lambda:get(api.base+'/epochs?offset=60&limit=60'),lambda v:v['total']==args.epochs and len(v['epochs'])==60 and v['offset']==60,layer)
    tree=timed('api_tree_root',lambda:post('/api/tree-pages',base),lambda v:v['count']==args.epochs and len(v['branches'])==1,layer)
    date_body={**base,'path':tree['branches'][0]['path'],'revision':tree['revision']}
    date=timed('api_tree_expand_date',lambda:post('/api/tree-pages',date_body),lambda v:v['total']==args.epochs//100 and len(v['branches'])==60,layer)
    cell_body={**base,'path':date['branches'][0]['path'],'revision':tree['revision']}
    cell=timed('api_tree_expand_cell',lambda:post('/api/tree-pages',cell_body),lambda v:v['selection']['count']==100 and len(v['branches'])==5,layer)
    block_body={**base,'path':cell['branches'][0]['path'],'revision':tree['revision']}
    timed('api_tree_expand_block',lambda:post('/api/tree-pages',block_body),lambda v:v['total']==20 and len(v['epochs'])==20,layer)
    timed('api_exact_epoch_search_preview',lambda:post('/api/explore/preview',{'predicate':{'field':'epoch','operator':'eq','value':epoch},'splits':'date,cell,block','summary_only':True}),lambda v:v['matched_count']==1,layer)
    timed('api_contrast_filter_preview',lambda:post('/api/explore/preview',{'predicate':pred,'splits':'date,cell,block','summary_only':True}),lambda v:v['matched_count']==args.epochs//5,layer)
    timed('api_epoch_details',lambda:get('/api/epochs/'+epoch),lambda v:v['epoch_uuid']==epoch,layer)
    timed('api_overview',lambda:get('/api/overview'),lambda v:v['counts']['epochs']==args.epochs,layer)
    report.update(status='complete',nonmutating_tables=all(not t.rows for t in (api.curation,api.datasets,api.events)),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
    if args.serve:
        enter('browser_server')
        while not (root/'browser-done').exists():time.sleep(1)
        server.shutdown()
except BaseException as error:
    report.update(status='failed',error=str(error),traceback=traceback.format_exc());save();traceback.print_exc()
    if args.serve and 'server' in globals():
        enter('browser_server')
        while not (root/'browser-done').exists():time.sleep(1)
        server.shutdown()
    sys.exit(1)
finally:
    stopped=True
    if api:api.doCleanups()
