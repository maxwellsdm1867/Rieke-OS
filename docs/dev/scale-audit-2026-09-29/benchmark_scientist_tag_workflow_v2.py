"""Native scientist tag/filter workflow against an explicitly selected source tree.

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
    ap.add_argument('--samples',type=int,default=20);ap.add_argument('--edit-count',type=int,default=10)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--profile',action='store_true')
    ap.add_argument('--page-cells',action='store_true',help='Validate optional filtered cell counts and run the new page-first workflow')
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
        'page_cells':args.page_cells,'baseline_harness_sha256':digest(Path(__file__).with_name('benchmark_scientist_tag_workflow.py'))}
    samples={};sql_samples={};app=None;dj=None;project_root=None;index=None;closed=False
    def check(name,condition,**detail):
        report['checks'].append({'name':name,'passed':bool(condition),**detail})
        if not condition:raise AssertionError(name)
    def log(message):print(message,flush=True)
    started=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='rieke-scientist-tag-workflow-') as directory:
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
                predicates={
                    'A':{'all':[rule('gate:0','epoch'),rule('gate:1','epoch'),rule('cell-common','cell'),{'not':rule('gate:2')}]},
                    'B':{'any':[rule('qc','epoch'),rule('cell-bucket:3','cell'),rule('é','epoch')]},
                    'C':{'all':[{'not':rule('QC')},rule('e\u0301','epoch'),rule('cell-common','cell')]},
                    'direct_inheritance_excluded':{'all':[rule('cell-common','epoch')]}}
                expected={
                    'A':tuple(ids[i] for i in range(args.epochs) if i%2==0 and i%3==0 and i%4!=0),
                    'B':tuple(ids[i] for i in range(args.epochs) if i%2==1 or (i//100)%5==3 or i%3==0),
                    'C':tuple(ids[i] for i in range(args.epochs) if i%2==1 and i%3!=0),
                    'direct_inheritance_excluded':()}
                edited=expected['A'][:args.edit_count];marker='workflow-selected';dataset_marker='workflow-dataset'
                predicates['edited']={'all':[rule(marker,'epoch'),*predicates['A']['all']]};expected['edited']=()
                report['filter_contract']={name:{'predicate':predicate,'expected_count':len(expected[name]),'membership_sha256':hashlib.sha256(''.join(expected[name]).encode()).hexdigest()} for name,predicate in predicates.items()}
                report['edited_epoch_uuids']=edited;shared_revisions={(key,p):1 for key in edited for p in range(3)};curation_revisions={key:1 for key in edited}
                shared_active=None;curation_active=False
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
                def query(name,**extra):
                    return {'tag_predicate':json.dumps(predicates[name],ensure_ascii=False,separators=(',',':')),
                        **({'include_cells':'true'} if args.page_cells and 'limit' in extra else {}),**extra}
                def validate_page(value,name,offset=0):
                    wanted=expected[name];shown=wanted[offset:offset+60]
                    assert value['total']==len(wanted) and tuple(row['epoch_uuid'] for row in value['epochs'])==shown,(name,value['total'],len(wanted))
                    if args.page_cells:
                        counts={}
                        for identity in wanted:
                            cell=uid(args.epochs+ordinals[identity]//100);counts[cell]=counts.get(cell,0)+1
                        assert {row['cell_uuid']:row['epochs'] for row in value['cells']}==counts,(name,'filtered cell counts')
                        assert len(value['cells'])==len(counts)
                    for row in value['epochs']:
                        identity=row['epoch_uuid'];i=ordinals[identity];wanted_chips=[]
                        for p,author in enumerate(authors):
                            values=tags(i,p)+([marker] if shared_active==p and identity in edited else [])
                            wanted_chips.extend((tag,author) for tag in values)
                        actual=sorted((item['tag'],item['profile_uuid']) for item in row['annotations']['epoch_tags'])
                        assert actual==sorted(wanted_chips),(name,identity,'author tag chips')
                        cell_i=cell_ordinals[service.rows[identity]['cell_uuid']]
                        wanted_inherited=sorted((tag,author) for p,author in enumerate(authors) for tag in tags(cell_i,p,cell=True))
                        assert sorted((item['tag'],item['profile_uuid']) for item in row['annotations']['cell_tags'])==wanted_inherited
                        assert row['curation']['revision']==curation_revisions.get(identity,1)
                        assert sorted(row['curation']['tags'])==sorted(['dataset:0',*[f'dataset-tag:{j}' for j in range(4)]]+([dataset_marker] if curation_active and identity in edited else []))
                def page(label,name,offset=0):
                    value,elapsed=measure(label,lambda:request('GET',base+'/epochs',query=query(name,limit=60,offset=offset)))
                    validate_page(value,name,offset);return value,elapsed
                def summary(label,name):
                    value,elapsed=measure(label,lambda:request('GET',base,query=query(name)))
                    assert value['counts']['epochs']==len(expected[name]),(name,value['counts'],len(expected[name]));return value,elapsed
                def bundle(label,name):
                    _,a=summary(label+'_summary',name);value,b=page(label+'_page',name);samples.setdefault(label+'_server_bundle',[]).append(a+b);return value
                def suggest(label,prefix):
                    value,elapsed=measure(label,lambda:request('GET','/api/annotation-tags',query={'q':prefix,'limit':12}))
                    if prefix=='gate':
                        wanted=[{'tag':f'gate:{p}','count':(args.epochs+p+1)//(p+2),'authors':[{'profile_uuid':authors[p],'display_name':author_names[p]}]} for p in range(3)]
                    elif prefix in ('qc','é','e\u0301','cell-common'):
                        all_authors=[{'profile_uuid':author,'display_name':name} for author,name in sorted(zip(authors,author_names))]
                        counts={'QC':(args.epochs+1)//2,'qc':args.epochs//2} if prefix=='qc' else {
                            prefix:(args.epochs+2)//3 if prefix=='é' else args.epochs-(args.epochs+2)//3 if prefix=='e\u0301' else (args.epochs+99)//100}
                        wanted=[{'tag':tag,'count':count,'authors':all_authors} for tag,count in sorted(counts.items(),key=lambda pair:(-pair[1],pair[0].casefold(),pair[0]))]
                    else:wanted=[] if shared_active is None else [{'tag':marker,'count':len(edited),'authors':[{'profile_uuid':authors[shared_active],'display_name':author_names[shared_active]}]}]
                    assert value['tags']==wanted and value['total']==len(wanted),(prefix,value,wanted)
                    return value
                for name in predicates:
                    if name=='edited':continue
                    page('cold_filter_'+name,name)
                    last=max(0,len(expected[name])-60);page('oracle_boundary_'+name,name,last)
                    exact,_=service._epoch_page_identities(protocol,query(name))
                    check('full_membership_'+name,tuple(exact)==expected[name],count=len(exact))
                suggest('suggestions_cold','gate')
                for _ in range(args.samples):suggest('suggestions_warm','gate')
                if args.page_cells:
                    for label,prefix in [('case','qc'),('unicode_nfc','é'),('unicode_nfd','e\u0301'),('inherited_targets','cell-common')]:
                        suggest('suggestions_first_'+label,prefix)
                    known_fields={'epoch','date','cell','block','block time','cell type','group label','group','protocol',
                        'parameters/contrast','parameters/seed','parameters/stimTime','parameters/currentMean',
                        'metadata/cell/properties/type','metadata/cell/label','metadata/block/parameters/amp'}
                    allowed_fields={'id','label','category','path','components','grouping_role','grouping_priority','grouping_hint'}
                    for iteration in range(args.samples+1):
                        value,_=measure('metadata_fields_cold' if iteration==0 else 'metadata_fields_warm',lambda:request('GET','/api/metadata/fields'))
                        assert {field['id'] for field in value['fields']}==known_fields
                        assert len(value['fields'])==len(known_fields) and all(set(field)<=allowed_fields for field in value['fields'])
                def shared_change(add,p,*,label=None):
                    nonlocal shared_active
                    body={'target_kind':'epoch','target_uuids':list(edited),'profile_uuid':authors[p],
                        'tags_add' if add else 'tags_remove':[marker],'expected_revisions':{key:shared_revisions[(key,p)] for key in edited}}
                    call=lambda:request('POST','/api/annotations',body=body)
                    value=measure(label,call)[0] if label else call()
                    assert value['changed']==len(edited)
                    for key in edited:shared_revisions[(key,p)]+=1
                    shared_active=p if add else None;expected['edited']=edited if add else ()
                def curation_change(add,current_page,*,label):
                    nonlocal curation_active
                    body={'epoch_uuids':list(edited),'query_revision':current_page['query_revision'],'expected_binding_version':0,
                        'expected_revisions':dict(curation_revisions),'changes':{'tags_add' if add else 'tags_remove':[dataset_marker]}}
                    measure(label,lambda:request('POST',base+'/curation',body=body))
                    for key in edited:curation_revisions[key]+=1
                    curation_active=add
                for iteration in range(args.samples):
                    before=time.perf_counter();bundle('filter_A','A');bundle('filter_B','B');current=bundle('return_A','A')
                    samples.setdefault('A_B_A_sequential_server_bundle',[]).append(sum(samples[key][-1] for key in ('filter_A_server_bundle','filter_B_server_bundle','return_A_server_bundle')))
                    p=iteration%3
                    shared_change(True,p,label='shared_add_durable_save');current=bundle('first_after_shared_add','A')
                    page('added_tag_filter','edited');suggest('suggestions_after_shared_add','workflow')
                    shared_change(False,p,label='shared_remove_durable_save');current=bundle('first_after_shared_remove','A')
                    page('removed_tag_filter','edited');suggest('suggestions_after_shared_remove','workflow')
                    curation_change(True,current,label='dataset_add_durable_save');current=bundle('first_after_dataset_add','A')
                    curation_change(False,current,label='dataset_remove_durable_save');bundle('first_after_dataset_remove','A')
                    samples.setdefault('complete_workflow_wall_with_oracles',[]).append(time.perf_counter()-before)
                    log(json.dumps({'stage':'cycle','epochs':args.epochs,'iteration':iteration+1,'seconds':samples['complete_workflow_wall_with_oracles'][-1]}))
                # This is measured separately: the first request after a save is
                # the visible page, before any summary/autocomplete can maintain
                # or warm the shared membership index for it.
                if args.page_cells:
                    def focused(label):
                        identity=edited[0];i=ordinals[identity]
                        value,_=measure(label,lambda:request('GET','/api/epochs/'+identity,query={'protocol_uuid':protocol}))
                        assert value['epoch_uuid']==identity and value['parameters']=={'contrast':(i%5)/10,'seed':i,'stimTime':1000,'currentMean':(i%3)*100}
                        assert value['curation']['revision']==curation_revisions[identity]
                        wanted=sorted((tag,author) for p,author in enumerate(authors) for tag in tags(i,p)+([marker] if shared_active==p else []))
                        assert sorted((item['tag'],item['profile_uuid']) for item in value['annotations']['epoch_tags'])==wanted
                    for iteration in range(args.samples):
                        page('page_first_filter_A','A');page('page_first_filter_B','B');current,_=page('page_first_return_A','A')
                        p=iteration%3
                        shared_change(True,p,label='page_first_shared_add_save')
                        current,_=page('page_first_after_shared_add','A')
                        focused('focused_metadata_after_shared_add')
                        suggest('page_first_suggestions_after_shared_add','workflow')
                        shared_change(False,p,label='page_first_shared_remove_save')
                        current,_=page('page_first_after_shared_remove','A')
                        focused('focused_metadata_after_shared_remove')
                        suggest('page_first_suggestions_after_shared_remove','workflow')
                        curation_change(True,current,label='page_first_dataset_add_save')
                        current,_=page('page_first_after_dataset_add','A')
                        focused('focused_metadata_after_dataset_add')
                        curation_change(False,current,label='page_first_dataset_remove_save')
                        page('page_first_after_dataset_remove','A')
                        focused('focused_metadata_after_dataset_remove')
                        log(json.dumps({'stage':'page_first_cycle','epochs':args.epochs,'iteration':iteration+1}))
                def profile(name,callback):
                    profiler=cProfile.Profile();value=profiler.runcall(callback);stats=pstats.Stats(profiler)
                    report.setdefault('cpu_profiles',{})[name]=[{'file':str(Path(key[0]).relative_to(root)) if Path(key[0]).is_absolute() and Path(key[0]).is_relative_to(root) else key[0],
                        'line':key[1],'function':key[2],'primitive_calls':value[0],'calls':value[1],'self_seconds':value[2],'cumulative_seconds':value[3]}
                        for key,value in sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True)[:40]]
                    return value
                if args.profile:
                    value=profile('warm_multitag_page',lambda:request('GET',base+'/epochs',query=query('A',limit=60)));validate_page(value,'A')
                    def post_save_loop():
                        shared_change(True,0)
                        value=request('GET',base,query=query('A'));assert value['counts']['epochs']==len(expected['A'])
                        result=request('GET',base+'/epochs',query=query('A',limit=60));validate_page(result,'A')
                        request('GET','/api/annotation-tags',query={'q':'workflow','limit':12})
                    profile('post_shared_save_summary_page_suggestions',post_save_loop);shared_change(False,0)
                check('final_exact_membership_restored',all(tuple(service._epoch_page_identities(protocol,query(name))[0])==expected[name] for name in predicates))
                other_page=request('GET',f'/api/protocols/{other}/epochs',query={'limit':60})
                check('other_protocol_curation_untouched',all(row['curation']['revision']==1 and 'dataset:1' in row['curation']['tags'] and dataset_marker not in row['curation']['tags'] for row in other_page['epochs']))
                report['workflow_peak_rss_before_durable_oracle_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                began=time.perf_counter();state=snapshot.load(project_root/'app-state.json');report['durable_snapshot_verify_seconds']=time.perf_counter()-began
                saved={(row['target_uuid'],row['profile_uuid']):row for row in state['tables']['shared_annotation'] if row['target_kind']=='epoch' and row['target_uuid'] in edited}
                check('durable_mirror_exact_tag_removal_and_author_revisions',all(sorted(saved[(key,authors[p])]['tags'])==sorted(tags(ordinals[key],p)) and saved[(key,authors[p])]['revision']==shared_revisions[(key,p)] for key in edited for p in range(3)))
                check('durable_mirror_keeps_two_protocol_scopes',len(state['tables']['curation'])==args.epochs*2)
                report['shared_index_stats']=getattr(getattr(shared,'_shared_tag_index',None),'stats',None)
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
    derived={
        'warm_page_only_A_B_A_inferred_from_summary_first':('filter_A_page','filter_B_page','return_A_page'),
        'shared_add_save_plus_warm_page_inferred':('shared_add_durable_save','first_after_shared_add_page'),
        'shared_remove_save_plus_warm_page_inferred':('shared_remove_durable_save','first_after_shared_remove_page'),
        'measured_page_first_A_B_A':('page_first_filter_A','page_first_filter_B','page_first_return_A'),
        'measured_shared_add_save_plus_first_page':('page_first_shared_add_save','page_first_after_shared_add'),
        'measured_shared_remove_save_plus_first_page':('page_first_shared_remove_save','page_first_after_shared_remove'),
        'measured_shared_add_save_page_focus':('page_first_shared_add_save','page_first_after_shared_add','focused_metadata_after_shared_add'),
        'measured_shared_remove_save_page_focus':('page_first_shared_remove_save','page_first_after_shared_remove','focused_metadata_after_shared_remove'),
        'measured_dataset_add_save_plus_first_page':('page_first_dataset_add_save','page_first_after_dataset_add'),
        'measured_dataset_remove_save_plus_first_page':('page_first_dataset_remove_save','page_first_after_dataset_remove')}
    report['derived_bundle_definitions']={name:list(keys) for name,keys in derived.items() if all(key in samples for key in keys)}
    for name,keys in report['derived_bundle_definitions'].items():
        lengths={len(samples[key]) for key in keys}
        if len(lengths)==1:samples[name]=[sum(values) for values in zip(*(samples[key] for key in keys))]
    report['operations']={name:{**percentiles(values),'sql_session_deltas':sql_samples.get(name,[])} for name,values in samples.items()}
    report['source_inventory_after']=source_inventory(root);report['source_unchanged']=report['source_inventory_before']==report['source_inventory_after']
    report['harness_unchanged']=digest(__file__)==report['harness_sha256']
    report['seconds']=time.perf_counter()-started;report['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();report['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['passed']=not report.get('error') and closed and report['source_unchanged'] and report['harness_unchanged'] and all(item['passed'] for item in report['checks'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');log(json.dumps({'stage':'done','epochs':args.epochs,'passed':report['passed'],'seconds':report['seconds'],'output':str(args.output)}))
    return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
