"""Native single, batch and inherited-cell tag actions against a selected source tree.

Every project/database is disposable. Acquisition metadata is synthetic; actual
MySQL, triggers, Flask routes, derived indexes and synchronous durable save hooks
are used. HTTP times include Flask serialization/client JSON decoding, exclude
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
    ap.add_argument('--samples',type=int,default=20);ap.add_argument('--targets',default='epoch:1,epoch:5,epoch:20,cell:1')
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',action='store_true')
    ap.add_argument('--page-cells',action='store_true',default=True)
    args=ap.parse_args()
    args.output=args.output.resolve();root=args.source_root.resolve(strict=True)
    if args.output.exists():ap.error('Choose an unused output receipt')
    if args.epochs<12 or args.samples<1:ap.error('Use at least12 epochs and one sample')
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
        with tempfile.TemporaryDirectory(prefix='rieke-tag-actions-') as directory:
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

                targets=[]
                for entry in args.targets.split(','):
                    kind,count=entry.split(':');count=int(count)
                    if kind not in ('epoch','cell') or count<1 or (kind=='cell' and count!=1):raise ValueError('Use epoch:N or cell:1')
                    selected=ids[:count] if kind=='epoch' else (next(iter(service.cells)),)
                    if len(selected)!=count:raise ValueError('Not enough targets')
                    targets.append({'name':f'{kind}_{count}','kind':kind,'ids':tuple(selected),'marker':f'action-{kind}-{count}'})
                report['targets']=[{**target,'child_epoch_count':sum(service.rows[key]['cell_uuid'] in target['ids'] for key in ids) if target['kind']=='cell' else len(target['ids'])} for target in targets]
                revisions={(target['kind'],identity,p):1 for target in targets for identity in target['ids'] for p in range(3)}
                active=None
                stable_predicate={'all':[rule('gate:0','epoch'),rule('gate:1','epoch'),rule('cell-common','cell'),{'not':rule('gate:2')}]}
                stable_expected=tuple(ids[i] for i in range(args.epochs) if i%2==0 and i%3==0 and i%4!=0)
                def sql_status():return {key:int(value) for key,value in dj.conn().query("SHOW SESSION STATUS WHERE Variable_name IN ('Rows_sent','Bytes_sent','Questions')").fetchall()}
                def request(method,path,*,query=None,body=None):
                    response=client.get(path,query_string=query) if method=='GET' else client.post(path,json=body,headers=headers)
                    value=response.get_json()
                    if response.status_code!=200:raise AssertionError((method,path,response.status_code,value))
                    return value
                def measure(name,callback):
                    before=sql_status();began=time.perf_counter();value=callback();elapsed=time.perf_counter()-began;after=sql_status()
                    samples.setdefault(name,[]).append(elapsed);sql_samples.setdefault(name,[]).append({key:after[key]-before[key] for key in before})
                    return value,elapsed
                def query(predicate,**extra):return {'tag_predicate':json.dumps(predicate,ensure_ascii=False,separators=(',',':')),**extra}
                def wanted_tags(kind,identity,p):
                    ordinal=ordinals[identity] if kind=='epoch' else cell_ordinals[identity]
                    result=tags(ordinal,p,cell=kind=='cell')
                    if active is not None and active[0]['kind']==kind and identity in active[0]['ids'] and active[1]==p:result=result+[active[0]['marker']]
                    return sorted(result)
                def validate_row(row):
                    identity=row['epoch_uuid'];cell=service.rows[identity]['cell_uuid']
                    for kind,field,key in [('epoch','epoch_tags',identity),('cell','cell_tags',cell)]:
                        wanted=sorted((tag,author) for p,author in enumerate(authors) for tag in wanted_tags(kind,key,p))
                        assert sorted((chip['tag'],chip['profile_uuid']) for chip in row['annotations'][field])==wanted,(identity,kind)
                    assert row['curation']['revision']==1
                    assert sorted(row['curation']['tags'])==sorted(['dataset:0',*[f'dataset-tag:{j}' for j in range(4)]])
                def page(label,predicate,wanted,offset=0,*,timed=True):
                    call=lambda:request('GET',base+'/epochs',query=query(predicate,limit=60,offset=offset,include_cells='true'))
                    value,elapsed=measure(label,call) if timed else (call(),0)
                    assert value['total']==len(wanted)
                    assert tuple(row['epoch_uuid'] for row in value['epochs'])==wanted[offset:offset+60]
                    counts={}
                    for key in wanted:
                        cell=service.rows[key]['cell_uuid'];counts[cell]=counts.get(cell,0)+1
                    assert {row['cell_uuid']:row['epochs'] for row in value['cells']}==counts
                    for row in value['epochs']:validate_row(row)
                    return value,elapsed
                def focused(label,identity):
                    value,elapsed=measure(label,lambda:request('GET','/api/epochs/'+identity,query={'protocol_uuid':protocol}))
                    assert value['epoch_uuid']==identity;validate_row(value);return value,elapsed
                def affected_ids(target):
                    return target['ids'] if target['kind']=='epoch' else tuple(key for key in ids if service.rows[key]['cell_uuid'] in target['ids'])
                def change(target,add,p,*,label=None):
                    nonlocal active
                    body={'target_kind':target['kind'],'target_uuids':list(target['ids']),'profile_uuid':authors[p],
                          'tags_add' if add else 'tags_remove':[target['marker']],
                          'expected_revisions':{key:revisions[(target['kind'],key,p)] for key in target['ids']}}
                    call=lambda:request('POST','/api/annotations',body=body)
                    value=measure(label,call)[0] if label else call()
                    assert value['changed']==len(target['ids'])
                    for key in target['ids']:revisions[(target['kind'],key,p)]+=1
                    active=(target,p) if add else None
                    return value
                def sql_rows(kind,keys):
                    rows=(shared.Annotation&{'project_uuid':project,'target_kind':kind}&[{'target_uuid':key} for key in keys]).to_dicts()
                    return sorted((row['target_uuid'],row['profile_uuid'],row['revision'],tuple(sorted(row['tags'])),row['author_name'],str(row['updated_at'])) for row in rows)
                initial_epoch_row_count=len(shared.Annotation&{'project_uuid':project,'target_kind':'epoch'})
                check('three_direct_annotation_rows_per_epoch',initial_epoch_row_count==args.epochs*3)
                page('cold_initial_shared_index',stable_predicate,stable_expected)
                exact,_=service._epoch_page_identities(protocol,query(stable_predicate));check('stable_filter_exact_membership',tuple(exact)==stable_expected,count=len(exact))
                # Warm the empty marker predicates once. Every later add/remove
                # must invalidate and recompute the affected predicate exactly.
                for target in targets:page('warm_empty_'+target['name'],{'all':[rule(target['marker'])]},(),timed=False)
                for target in targets:
                    wanted=affected_ids(target);focus=wanted[0];predicate={'all':[rule(target['marker'])]}
                    child_rows=sql_rows('epoch',wanted) if target['kind']=='cell' else None
                    for iteration in range(args.samples):
                        p=iteration%3
                        for add in (True,False):
                            label=target['name']+('_add' if add else '_remove')
                            change(target,add,p,label=label+'_durable_save')
                            page(label+'_first_stable_page',stable_predicate,stable_expected)
                            focused(label+'_focused_metadata',focus)
                            expected=wanted if add else ()
                            page(label+'_affected_filter',predicate,expected)
                            exact,_=service._epoch_page_identities(protocol,query(predicate));assert tuple(exact)==expected
                            if len(expected)>60:page(label+'_affected_last_page',predicate,expected,len(expected)-60,timed=False)
                            if target['kind']=='cell':
                                direct={'all':[rule(target['marker'],'epoch')]}
                                page(label+'_direct_epoch_excludes_inheritance',direct,(),timed=False)
                                assert sql_rows('epoch',wanted)==child_rows,'Cell edit changed child annotation rows'
                                assert len(shared.Annotation&{'project_uuid':project,'target_kind':'epoch'})==initial_epoch_row_count,'Cell edit created epoch annotation copies'
                            for key in target['ids']:
                                rows=(shared.Annotation&{'project_uuid':project,'target_kind':target['kind'],'target_uuid':key,'profile_uuid':authors[p]}).to_dicts()
                                assert len(rows)==1 and rows[0]['revision']==revisions[(target['kind'],key,p)]
                                assert sorted(rows[0]['tags'])==wanted_tags(target['kind'],key,p)
                            samples.setdefault(label+'_save_plus_first_page',[]).append(samples[label+'_durable_save'][-1]+samples[label+'_first_stable_page'][-1])
                            samples.setdefault(label+'_save_page_focus',[]).append(samples[label+'_save_plus_first_page'][-1]+samples[label+'_focused_metadata'][-1])
                        log(json.dumps({'stage':'action_cycle','epochs':args.epochs,'target':target['name'],'iteration':iteration+1}))
                    check('exact_add_remove_'+target['name'],True,samples=args.samples,targets=len(target['ids']),effective_epochs=len(wanted))
                    if target['kind']=='cell':check('cell_inheritance_without_child_annotation_copy',True,child_epochs=len(wanted),direct_rows_unchanged=len(child_rows))
                def profile_save(target,add):
                    import re
                    connection=dj.conn();original_query=connection.query;original_fsync=os.fsync;sql_calls=[];sync_calls=[]
                    def traced_query(statement,*positional,**keywords):
                        began=time.perf_counter()
                        try:return original_query(statement,*positional,**keywords)
                        finally:sql_calls.append({'sql_shape':re.sub(r"'[^']*'","'?'",str(statement))[:240],'seconds':time.perf_counter()-began})
                    def traced_fsync(descriptor):
                        began=time.perf_counter()
                        try:return original_fsync(descriptor)
                        finally:sync_calls.append(time.perf_counter()-began)
                    profiler=cProfile.Profile();connection.query=traced_query;os.fsync=traced_fsync
                    try:profiler.runcall(change,target,add,0)
                    finally:connection.query=original_query;os.fsync=original_fsync
                    stats=pstats.Stats(profiler);rows=[]
                    for key,value in sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True):
                        path=Path(key[0]);rows.append({'file':str(path.relative_to(root)) if path.is_absolute() and path.is_relative_to(root) else key[0],
                            'line':key[1],'function':key[2],'primitive_calls':value[0],'calls':value[1],'self_seconds':value[2],'cumulative_seconds':value[3]})
                    label=target['name']+('_add' if add else '_remove')
                    report.setdefault('cpu_profiles',{})[label]={'top_functions':rows[:100],
                        'sql_and_durability_functions':[row for row in rows if any(word in row['function'].lower() for word in ('fsync','commit','query','execute','capture','recovery','atomic_write'))],
                        'native_sql_calls':sql_calls,'python_fsync_calls_seconds':sync_calls,
                        'limits':'Separate instrumented sample. Native SQL timing wraps query dispatch; fetch costs appear in cProfile. Python fsync does not intercept SQLite internal fsync; SQLite commit time appears in cProfile.'}
                    page(label+'_profile_postcheck',stable_predicate,stable_expected,timed=False)
                if args.profile:
                    for target in targets:
                        for add in (True,False):profile_save(target,add)
                check('final_markers_removed',active is None)
                report['workflow_peak_rss_before_durable_oracle_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                began=time.perf_counter();state=snapshot.load(project_root/'app-state.json');report['durable_snapshot_verify_seconds']=time.perf_counter()-began
                saved={(row['target_kind'],row['target_uuid'],row['profile_uuid']):row for row in state['tables']['shared_annotation']}
                for (kind,key,p),revision in revisions.items():
                    row=saved[(kind,key,authors[p])]
                    assert row['revision']==revision and sorted(row['tags'])==wanted_tags(kind,key,p)
                check('durable_mirror_exact_targets_revisions_and_removal',True,records=len(revisions))
                check('durable_mirror_direct_row_count_unchanged',sum(row['target_kind']=='epoch' for row in saved.values())==args.epochs*3)
                check('independent_protocol_curation_untouched',len(state['tables']['curation'])==args.epochs*2 and all(row['revision']==1 for row in state['tables']['curation']))
                loaded={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name.startswith('workspace_') or name=='recording_workspace') and getattr(module,'__file__',None)}
                check('all_product_modules_loaded_from_selected_source',all(Path(path).is_relative_to(root) for path in loaded.values()))
                report['loaded_product_modules']=loaded
            finally:
                if app is not None:
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
