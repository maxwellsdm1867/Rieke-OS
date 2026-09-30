"""Native single-epoch and single-cell writes without post-seed index preparation.

Every project/database is disposable. Acquisition metadata is synthetic; actual
MySQL, triggers, Flask routes, derived indexes and each version's save hooks
are used. Native SQL commits are checked immediately; any background recovery
mirror is explicitly flushed before its final oracle. HTTP times include Flask serialization/client JSON decoding, exclude
oracle work, and do not model browser concurrency/rendering. Sequential bundle
times are sums of their separately measured requests. Profiles are separate.
"""
import argparse
import copy
import cProfile
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import pstats
import resource
import statistics
import sys
import tempfile
import time
import traceback


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def percentiles(values):
    ordered=sorted(values)
    return {'samples_seconds':values,'p50_seconds':statistics.median(values),'p95_seconds':ordered[math.ceil(.95*len(ordered))-1],
            'p99_seconds':ordered[math.ceil(.99*len(ordered))-1],'maximum_seconds':max(values),'quantile_method':'nearest_rank'}
def rule(tag,scope='effective'):return {'field':'annotations/'+scope+'/tags','operator':'contains','value':tag}
def tags(ordinal,profile,*,cell=False):
    if cell:return ['cell-common',f'cell-bucket:{ordinal%5}',f'cell-author:{profile}','Inherited' if profile==0 else 'inherited',f'cell-type:{ordinal%2}']
    return ['all',f'gate:{profile}' if ordinal%(profile+2)==0 else f'rest:{profile}','QC' if ordinal%2==0 else 'qc',
            'é' if ordinal%3==0 else 'e\u0301',f'bucket:{ordinal%17}']
def source_inventory(root):
    return {str(path.relative_to(root)):digest(path) for path in sorted((root/'python').rglob('*.py'))}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source-root',type=Path,required=True)
    ap.add_argument('--mysql-runtime-root',type=Path,required=True);ap.add_argument('--epochs',type=int,required=True)
    ap.add_argument('--samples',type=int,default=20);ap.add_argument('--targets',default='epoch:1,cell:1')
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',action='store_true')
    ap.add_argument('--page-cells',action='store_true',default=True)
    args=ap.parse_args()
    args.output=args.output.resolve();root=args.source_root.resolve(strict=True)
    if args.output.exists():ap.error('Choose an unused output receipt')
    if args.epochs<200 or args.samples<1:ap.error('Use at least200 epochs and one sample')
    # Product and fixture imports must come from the selected immutable tree.
    sys.path[:0]=[str(root/'python'),str(root/'docs/dev/scale-audit-2026-09-29')]
    os.chdir(root)
    from benchmark_service_scale import fixture,Details,uid
    import benchmark_service_scale
    from recording_workspace import connect,workspace_tables
    from workspace_projects import create_project
    import workspace_native_mysql as native
    from workspace_mysql_runtime import _probe,runtime_spec
    from workspace_disk_index import DiskMetadataIndex
    from workspace_api import create_app
    import workspace_state_snapshot as snapshot
    runtime=_probe(args.mysql_runtime_root.resolve(strict=True),runtime_spec(root)[0]['mysql_version'])
    def runtime_binary(name='mysqld'):
        if name not in {'mysqld','mysql','mysqldump'}:raise ValueError('Unsupported native executable')
        return Path(runtime[name])
    native.native_binary=runtime_binary
    report={'scope':__doc__,'epochs':args.epochs,'profiles':3,'tags_per_annotation':5,'protocols':2,'samples':args.samples,
        'source_root':str(root),'source_inventory_before':source_inventory(root),'fixture_module':str(Path(benchmark_service_scale.__file__).resolve()),
        'harness_sha256':digest(__file__),'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'release_ready':False,'operations':{},'checks':[],
        'page_cells':True,'target_specification':args.targets,'baseline_harness_sha256':digest(Path(__file__).with_name('benchmark_scientist_tag_workflow.py'))}
    samples={};sql_samples={};app=None;dj=None;project_root=None;index=None;closed=False
    def check(name,condition,**detail):
        report['checks'].append({'name':name,'passed':bool(condition),**detail})
        if not condition:raise AssertionError(name)
    def log(message):print(message,flush=True)
    started=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='rieke-single-tag-write-') as directory:
            project_root=Path(create_project(Path(directory)/'projects','Disposable scientist tag workflow')['path'])
            try:
                native.ensure_native_database(project_root);dj=connect({'kind':'native-project'},project_dir=project_root)
                service,protocol=fixture(args.epochs);service.project_dir=project_root
                service.project=json.loads((project_root/'project.json').read_text());service.config=json.loads((project_root/'catalog.json').read_text());service.dj=dj
                service.manifests={item['source_sha256']:{'source_path':'/synthetic/'+item['filename']} for item in service.sources}
                other=uid(-3);service.protocols[other]=copy.deepcopy(service.protocols[protocol])
                service.protocols[other]['definition']['protocol_uuid']=other;service.protocols[other]['result']['protocol_uuid']=other
                for value in service.protocols.values():
                    value['definition']['project_uuid']=service.project['project_uuid']
                    value['definition']['query']={'version':1,'all':[{'field':'EpochBlock.protocol_name','operator':'eq','value':'Synthetic'}]}
                index=DiskMetadataIndex.build(project_root/'cache'/'metadata.sqlite',service.rows,Details(service.rows),service.sources,'tag-workflow-fixture-v1',service.project['project_uuid'])
                service.disk_index=index;service.details=index.details
                Project,_,_,_=workspace_tables(dj);project=service.project['project_uuid']
                Project.insert1({'project_uuid':project,'name':service.project['name'],'directory':str(project_root)})
                app=create_app(project_root,root/'.rieke-runtime/retinanalysis',service=service)
                assert service._recovery_tracker.ready,service._recovery_tracker.reason
                store=app.extensions['curation_store'];shared=app.extensions['shared_annotations'];authors=[uid(-100-i) for i in range(3)]
                author_names=['Same Scientist','Same Scientist','Scientist C'];stamp=dt.datetime(2026,9,29,12)
                ids=tuple(service.rows);ordinals={identity:i for i,identity in enumerate(ids)};cell_ordinals={identity:i for i,identity in enumerate(service.cells)}
                report['mysql_version']=dj.conn().query('SELECT VERSION()').fetchone()[0]
                seed=time.perf_counter();log(json.dumps({'stage':'seed','epochs':args.epochs,'source_root':str(root)}))
                with dj.conn().transaction:
                    shared.Profile.insert([{'project_uuid':project,'profile_uuid':author,'display_name':author_names[p],'created_at':stamp,'created_by':'workflow oracle'} for p,author in enumerate(authors)])
                    batch=[]
                    for kind,identities in [('epoch',ids),('cell',tuple(service.cells))]:
                        for ordinal,identity in enumerate(identities):
                            for p,author in enumerate(authors):
                                batch.append({'project_uuid':project,'target_kind':kind,'target_uuid':identity,'profile_uuid':author,
                                    'tags':tags(ordinal,p,cell=kind=='cell'),'author_name':author_names[p],'revision':1,'updated_at':stamp})
                                if len(batch)==500:shared.Annotation.insert(batch);batch=[]
                        if batch:shared.Annotation.insert(batch);batch=[]
                    for p,current in enumerate((protocol,other)):
                        for identity in ids:
                            batch.append({'project_uuid':project,'protocol_uuid':current,'epoch_uuid':identity,'included':True,
                                'tags':[f'dataset:{p}',*[f'dataset-tag:{i}' for i in range(4)]],'review_state':'unreviewed','revision':1,
                                'metadata_fingerprint':service._fingerprints[identity]})
                            if len(batch)==500:store.Curation.insert(batch);batch=[]
                        if batch:store.Curation.insert(batch);batch=[]
                report['seed_seconds']=time.perf_counter()-seed
                checkpoint=time.perf_counter();snapshot.save(project_root,dj.conn(),service=service);report['seed_checkpoint_seconds']=time.perf_counter()-checkpoint
                log(json.dumps({'stage':'timed_operations','epochs':args.epochs,'seed_seconds':report['seed_seconds']}))
                client=app.test_client();base=f'/api/protocols/{protocol}';headers={'X-Workspace-Request':'1','Origin':'http://localhost:8766'}



                import inspect,threading
                from workspace_shared_tag_index import SharedTagIndex
                lock=inspect.getclosurevars(app.view_functions['annotation_batch_read']).nonlocals['db_lock']
                connection=dj.conn();owner=threading.get_ident();recording=False;trace={}
                original_start=connection.start_transaction;original_commit=connection.commit_transaction
                original_event=shared._event;original_membership=shared._membership_index;original_refresh=SharedTagIndex.refresh
                def current():return recording and threading.get_ident()==owner
                def start_txn():
                    began=time.perf_counter();value=original_start()
                    if current():trace['transaction_started']=began;trace['begins']+=1
                    return value
                def commit_txn():
                    began=time.perf_counter();value=original_commit()
                    if current():
                        trace['commit_seconds'].append(time.perf_counter()-began)
                        trace['transaction_seconds'].append(time.perf_counter()-trace['transaction_started']);trace['commits']+=1
                    return value
                def event(*args,**kwargs):
                    if current():
                        assert connection.in_transaction and trace['begins']==1 and trace['commits']==0
                        trace['events_inside_transaction']+=1
                    return original_event(*args,**kwargs)
                def membership(*args,**kwargs):
                    if current():trace['membership_calls']+=1
                    return original_membership(*args,**kwargs)
                def refresh(*args,**kwargs):
                    if current():trace['index_refresh_calls']+=1
                    return original_refresh(*args,**kwargs)
                connection.start_transaction=start_txn;connection.commit_transaction=commit_txn
                shared._event=event;shared._membership_index=membership;SharedTagIndex.refresh=refresh
                with lock:
                    values=connection.query('SELECT @@innodb_flush_log_at_trx_commit,@@sync_binlog,@@log_bin').fetchone()
                report['mysql_durability']={'innodb_flush_log_at_trx_commit':int(values[0]),'sync_binlog':int(values[1]),'log_bin':bool(values[2])}
                epoch=ids[0];cell=service.rows[epoch]['cell_uuid'];children=tuple(key for key in ids if service.rows[key]['cell_uuid']==cell)
                targets={'epoch':epoch,'cell':cell};revisions={(kind,p):1 for kind in targets for p in range(3)};active={};marker='single-write-marker'
                report['post_traces']=[];report['backup_receipts']=[]
                index_before=getattr(shared,'_shared_tag_index',None)
                report['index_before_posts']={'present':index_before is not None,'stats':dict(index_before.stats) if index_before else None,'post_seed_preparation':False}
                def wanted(kind,p):return sorted(tags(ordinals[epoch] if kind=='epoch' else cell_ordinals[cell],p,cell=kind=='cell')+([marker] if active.get(kind)==p else []))
                def child_rows():
                    with lock:rows=(shared.Annotation&{'project_uuid':project,'target_kind':'epoch'}&[{'target_uuid':key} for key in children]).to_dicts()
                    return sorted((row['target_uuid'],row['profile_uuid'],row['revision'],tuple(sorted(row['tags'])),str(row['updated_at'])) for row in rows)
                def post(label,kind,p,add):
                    nonlocal recording,trace
                    key=targets[kind];before_children=child_rows() if kind=='cell' else None
                    body={'target_kind':kind,'target_uuids':[key],'profile_uuid':authors[p],
                        'tags_add':[marker] if add else [],'tags_remove':[] if add else [marker],
                        'expected_revisions':{key:revisions[(kind,p)]}}
                    trace={'operation':label,'begins':0,'commits':0,'events_inside_transaction':0,'membership_calls':0,'index_refresh_calls':0,'commit_seconds':[],'transaction_seconds':[]}
                    recording=True;began=time.perf_counter()
                    try:response=client.post('/api/annotations',json=body,headers=headers);value=response.get_json()
                    finally:elapsed=time.perf_counter()-began;recording=False
                    assert response.status_code==200 and value['changed']==1,(response.status_code,value)
                    assert value['persistence']['database']=='committed'
                    assert trace['begins']==trace['commits']==trace['events_inside_transaction']==1,trace
                    assert trace['membership_calls']==trace['index_refresh_calls']==0,trace
                    trace.pop('transaction_started',None);report['post_traces'].append(trace);report['backup_receipts'].append(value['persistence'])
                    samples.setdefault(label,[]).append(elapsed)
                    samples.setdefault(label+'_sql_transaction',[]).append(trace['transaction_seconds'][0]);samples.setdefault(label+'_commit_roundtrip',[]).append(trace['commit_seconds'][0])
                    revisions[(kind,p)]+=1
                    if add:active[kind]=p
                    else:active.pop(kind,None)
                    receipt=value['targets'][key]
                    assert receipt['revisions']=={author:revisions[(kind,q)] for q,author in enumerate(authors)}
                    assert sorted((v['tag'],v['profile_uuid']) for v in receipt['tags'])==sorted((tag,author) for q,author in enumerate(authors) for tag in wanted(kind,q))
                    with lock:
                        rows=(shared.Annotation&{'project_uuid':project,'target_kind':kind,'target_uuid':key,'profile_uuid':authors[p]}).to_dicts()
                        events=(shared.Event&{'event_uuid':value['event_uuid']}).to_dicts()
                    assert len(rows)==len(events)==1 and rows[0]['revision']==revisions[(kind,p)] and sorted(rows[0]['tags'])==wanted(kind,p)
                    assert events[0]['action']=='shared_annotations_updated' and events[0]['payload']['target_count']==1
                    assert events[0]['payload']['after'][0]['target_uuid']==key and events[0]['payload']['after'][0]['revision']==revisions[(kind,p)]
                    if kind=='cell':assert child_rows()==before_children,'Cell save rewrote child annotation rows'
                # Both first writes happen before repeated samples, with no
                # post-seed index rebuild or filter request anywhere in this run.
                for kind in targets:post(kind+'_first_add',kind,0,True)
                for kind in targets:post(kind+'_first_remove',kind,0,False)
                log(json.dumps({'stage':'first_writes','epochs':args.epochs,'epoch_ms':samples['epoch_first_add'][0]*1000,'cell_ms':samples['cell_first_add'][0]*1000}))
                for kind in targets:
                    for iteration in range(args.samples):
                        post(kind+'_add',kind,iteration%3,True);post(kind+'_remove',kind,iteration%3,False)
                    log(json.dumps({'stage':'single_target_complete','epochs':args.epochs,'target':kind,'samples':args.samples}))
                connection.start_transaction=original_start;connection.commit_transaction=original_commit
                shared._event=original_event;shared._membership_index=original_membership;SharedTagIndex.refresh=original_refresh
                check('no_membership_index_or_refresh_during_any_post',all(row['membership_calls']==row['index_refresh_calls']==0 for row in report['post_traces']),posts=len(report['post_traces']))
                check('annotation_event_committed_in_same_transaction',all(row['begins']==row['commits']==row['events_inside_transaction']==1 for row in report['post_traces']))
                after_index=getattr(shared,'_shared_tag_index',None);report['index_after_posts']={'stats':dict(after_index.stats) if after_index else None}
                scheduler=app.extensions['backup_scheduler'];scheduler.flush();report['final_backup_status']=scheduler.status()
                state=snapshot.load(project_root/'app-state.json');saved={(row['target_kind'],row['target_uuid'],row['profile_uuid']):row for row in state['tables']['shared_annotation']}
                for (kind,p),revision in revisions.items():
                    row=saved[(kind,targets[kind],authors[p])];assert row['revision']==revision and sorted(row['tags'])==wanted(kind,p)
                check('final_recovery_mirror_exact_tags_and_revisions',True)
                check('cell_has_one_canonical_record_per_author_no_child_copies',sum(row['target_kind']=='epoch' for row in saved.values())==args.epochs*3,child_epochs=len(children))
                check('other_protocol_curation_untouched',len(state['tables']['curation'])==args.epochs*2 and all(row['revision']==1 for row in state['tables']['curation']))
                loaded={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name.startswith('workspace_') or name=='recording_workspace') and getattr(module,'__file__',None)}
                check('all_product_modules_from_selected_source',all(Path(path).is_relative_to(root) for path in loaded.values()));report['loaded_product_modules']=loaded
            finally:
                if app is not None:
                    scheduler=app.extensions.get('backup_scheduler')
                    if scheduler is not None:
                        scheduler.flush()
                        close=getattr(scheduler,'close',None)
                        if close is not None:close(flush=False)
                    shared=app.extensions.get('shared_annotations');derived=getattr(shared,'_shared_tag_index',None)
                    if derived is not None:derived.close()
                    lock=app.extensions.get('app_state_session_lock')
                    if lock is not None:lock.close()
                if index is not None:index.close()
                if dj is not None:dj.conn().close()
                if project_root is not None:closed=native.stop_native_database(project_root)
                report['owned_native_runtime_stopped']=closed
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};log(traceback.format_exc())
    report['operations']={name:{**percentiles(values),'sql_session_deltas':sql_samples.get(name,[])} for name,values in samples.items()}
    report['source_inventory_after']=source_inventory(root);report['source_unchanged']=report['source_inventory_before']==report['source_inventory_after']
    report['harness_unchanged']=digest(__file__)==report['harness_sha256']
    report['seconds']=time.perf_counter()-started;report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();report['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['passed']=not report.get('error') and closed and report['source_unchanged'] and report['harness_unchanged'] and all(item['passed'] for item in report['checks'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');log(json.dumps({'stage':'done','epochs':args.epochs,'passed':report['passed'],'seconds':report['seconds'],'output':str(args.output)}))
    return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
