"""Persistent native tag lookup: tag-ten, tag-another-ten, filter-twenty and cell/epoch hierarchy.

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
    ap.add_argument('--samples',type=int,default=5);ap.add_argument('--targets',default='tag10_then10_filter20_and_cell_epoch_hierarchy')
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
    import importlib.util
    from workspace_annotations import SharedAnnotations,annotation_tables
    from workspace_curation import curation_tables
    sqlite_tag_calls={'membership_index':0,'refresh':0}
    original_membership=getattr(SharedAnnotations,'_membership_index',None)
    if original_membership is not None:
        def observed_membership(*args,**kwargs):
            sqlite_tag_calls['membership_index']+=1
            return original_membership(*args,**kwargs)
        SharedAnnotations._membership_index=observed_membership
    if importlib.util.find_spec('workspace_shared_tag_index') is not None:
        from workspace_shared_tag_index import SharedTagIndex
        original_refresh=SharedTagIndex.refresh
        def observed_refresh(*args,**kwargs):
            sqlite_tag_calls['refresh']+=1
            return original_refresh(*args,**kwargs)
        SharedTagIndex.refresh=observed_refresh
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
        with tempfile.TemporaryDirectory(prefix='rieke-native-tag-sequence-') as directory:
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
                # Construct only canonical fixture tables before application
                # startup. Normal startup then performs the actual populated
                # native lookup/dictionary migration once; all timed writes
                # retain the installed product triggers.
                ProfileTable,AnnotationTable=annotation_tables(dj)
                CurationTable,_=curation_tables(dj)
                derived_tables=dj.conn().query("SELECT table_name FROM information_schema.tables WHERE table_schema='recording_workspace' AND table_name IN ('app_shared_tag_lookup','app_shared_tag_dictionary','app_shared_tag_authors')").fetchall()
                assert not derived_tables,derived_tables
                authors=[uid(-100-i) for i in range(3)]
                author_names=['Same Scientist','Same Scientist','Scientist C'];stamp=dt.datetime(2026,9,29,12)
                ids=tuple(service.rows);ordinals={identity:i for i,identity in enumerate(ids)};cell_ordinals={identity:i for i,identity in enumerate(service.cells)}
                report['mysql_version']=dj.conn().query('SELECT VERSION()').fetchone()[0]
                seed=time.perf_counter();log(json.dumps({'stage':'seed','epochs':args.epochs,'source_root':str(root)}))
                with dj.conn().transaction:
                    ProfileTable.insert([{'project_uuid':project,'profile_uuid':author,'display_name':author_names[p],'created_at':stamp,'created_by':'workflow oracle'} for p,author in enumerate(authors)])
                    batch=[]
                    for kind,identities in [('epoch',ids),('cell',tuple(service.cells))]:
                        for ordinal,identity in enumerate(identities):
                            for p,author in enumerate(authors):
                                batch.append({'project_uuid':project,'target_kind':kind,'target_uuid':identity,'profile_uuid':author,
                                    'tags':tags(ordinal,p,cell=kind=='cell'),'author_name':author_names[p],'revision':1,'updated_at':stamp})
                                if len(batch)==500:AnnotationTable.insert(batch);batch=[]
                        if batch:AnnotationTable.insert(batch);batch=[]
                    for p,current in enumerate((protocol,other)):
                        for identity in ids:
                            batch.append({'project_uuid':project,'protocol_uuid':current,'epoch_uuid':identity,'included':True,
                                'tags':[f'dataset:{p}',*[f'dataset-tag:{i}' for i in range(4)]],'review_state':'unreviewed','revision':1,
                                'metadata_fingerprint':service._fingerprints[identity]})
                            if len(batch)==500:CurationTable.insert(batch);batch=[]
                        if batch:CurationTable.insert(batch);batch=[]
                report['seed_seconds']=time.perf_counter()-seed
                log(json.dumps({'stage':'populated_native_startup','epochs':args.epochs,'canonical_seed_seconds':report['seed_seconds']}))
                began=time.perf_counter()
                app=create_app(project_root,root/'.rieke-runtime/retinanalysis',service=service)
                report['populated_native_startup_seconds']=time.perf_counter()-began
                assert service._recovery_tracker.ready,service._recovery_tracker.reason
                store=app.extensions['curation_store'];shared=app.extensions['shared_annotations']
                report['fixture_construction']={'strategy':'canonical seed before normal app startup and populated native migration',
                    'native_derived_tables_absent_during_seed':not derived_tables,
                    'canonical_shared_records':(args.epochs+len(service.cells))*3,
                    'canonical_curation_records':args.epochs*2,
                    'product_triggers_disabled_during_timed_operations':False}
                check('populated_native_migration_ready_before_timed_operations',service.annotation_preparation.get('status')=='ready' and service.annotation_preparation.get('storage')=='native_sql')
                checkpoint=time.perf_counter();snapshot.save(project_root,dj.conn(),service=service);report['seed_checkpoint_seconds']=time.perf_counter()-checkpoint
                log(json.dumps({'stage':'timed_operations','epochs':args.epochs,'seed_seconds':report['seed_seconds']}))
                client=app.test_client();base=f'/api/protocols/{protocol}';headers={'X-Workspace-Request':'1','Origin':'http://localhost:8766'}


                import inspect
                import threading
                app_db_lock=inspect.getclosurevars(app.view_functions['annotation_batch_read']).nonlocals['db_lock']
                report['native_lookup_startup_preparation']=copy.deepcopy(getattr(service,'annotation_preparation',None))
                first=ids[:10];second=ids[100:110];selected=first+second;cell=service.rows[first[0]]['cell_uuid']
                children=tuple(key for key in ids if service.rows[key]['cell_uuid']==cell)
                assert len(children)==100 and service.rows[second[0]]['cell_uuid']!=cell
                epoch_marker='sequence-selected';cell_marker='sequence-cell'
                epoch_predicate={'all':[rule(epoch_marker,'epoch')]}
                cell_predicate={'all':[rule(cell_marker,'cell')]}
                hierarchy={'all':[rule(cell_marker,'cell'),rule(epoch_marker,'epoch')]}
                model={(kind,key,p):set() for kind,keys in [('epoch',selected),('cell',(cell,))] for key in keys for p in range(3)}
                revisions={key:1 for key in model}
                report['selected_epoch_uuids']={'first10':first,'second10':second,'cell':cell,'cell_children':children}
                report['backup_receipts']=[]
                def sql_status():
                    with app_db_lock:return {key:int(value) for key,value in dj.conn().query("SHOW SESSION STATUS WHERE Variable_name IN ('Bytes_sent','Questions')").fetchall()}
                def request(method,path,*,query=None,body=None):
                    response=client.get(path,query_string=query) if method=='GET' else client.post(path,json=body,headers=headers)
                    value=response.get_json()
                    if response.status_code!=200:raise AssertionError((method,path,response.status_code,value))
                    return value
                def measure(name,callback):
                    before=sql_status();began=time.perf_counter();value=callback();elapsed=time.perf_counter()-began;after=sql_status()
                    samples.setdefault(name,[]).append(elapsed);sql_samples.setdefault(name,[]).append({key:after[key]-before[key] for key in before})
                    return value,elapsed
                def wanted_tags(kind,key,p):
                    ordinal=ordinals[key] if kind=='epoch' else cell_ordinals[key]
                    return sorted([*tags(ordinal,p,cell=kind=='cell'),*model.get((kind,key,p),())])
                def validate_target(row,kind,key):
                    assert row['target_uuid']==key and row['target_kind']==kind
                    assert row['revisions']=={author:revisions.get((kind,key,p),1) for p,author in enumerate(authors)}
                    assert sorted((chip['tag'],chip['profile_uuid']) for chip in row['tags'])==sorted((tag,author) for p,author in enumerate(authors) for tag in wanted_tags(kind,key,p))
                def preflight(label,keys,p,*,timed=True):
                    call=lambda:request('POST','/api/annotations/read',body={'target_kind':'epoch','target_uuids':list(keys)})
                    value,_=measure(label,call) if timed else (call(),0)
                    assert set(value['targets'])==set(keys)
                    for key,row in value['targets'].items():validate_target(row,'epoch',key)
                    return {key:value['targets'][key]['revisions'][authors[p]] for key in keys}
                def change(label,kind,keys,p,marker,add,expected=None,*,timed=True):
                    body={'target_kind':kind,'target_uuids':list(keys),'profile_uuid':authors[p],
                        'tags_add':[marker] if add else [],'tags_remove':[] if add else [marker],
                        'expected_revisions':expected or {key:revisions[(kind,key,p)] for key in keys}}
                    call=lambda:request('POST','/api/annotations',body=body)
                    value,_=measure(label,call) if timed else (call(),0)
                    assert value['changed']==len(keys)
                    if 'persistence' in value:
                        assert value['persistence']['database']=='committed',value
                        report['backup_receipts'].append({'operation':label,'persistence':value['persistence']})
                    for key in keys:
                        revisions[(kind,key,p)]+=1
                        if add:model[(kind,key,p)].add(marker)
                        else:model[(kind,key,p)].remove(marker)
                    assert set(value['targets'])==set(keys)
                    for key,row in value['targets'].items():validate_target(row,kind,key)
                    # The oracle uses the application's actual SQL lock so the
                    # candidate's background mirror cannot race this connection.
                    with app_db_lock:
                        rows=(shared.Annotation&{'project_uuid':project,'target_kind':kind,'profile_uuid':authors[p]}&[{'target_uuid':key} for key in keys]).to_dicts()
                        assert {row['target_uuid'] for row in rows}==set(keys)
                        for row in rows:
                            key=row['target_uuid'];assert row['revision']==revisions[(kind,key,p)] and sorted(row['tags'])==wanted_tags(kind,key,p)
                    return value
                def query(predicate,**extra):return {'tag_predicate':json.dumps(predicate,separators=(',',':')),**extra}
                def page(label,predicate,wanted,*,offset=0,timed=True):
                    call=lambda:request('GET',base+'/epochs',query=query(predicate,limit=60,offset=offset,include_cells='true'))
                    value,elapsed=measure(label,call) if timed else (call(),0)
                    assert value['total']==len(wanted)
                    assert tuple(row['epoch_uuid'] for row in value['epochs'])==wanted[offset:offset+60]
                    counts={}
                    for key in wanted:
                        target_cell=service.rows[key]['cell_uuid'];counts[target_cell]=counts.get(target_cell,0)+1
                    assert {row['cell_uuid']:row['epochs'] for row in value['cells']}==counts
                    for row in value['epochs']:
                        key=row['epoch_uuid'];target_cell=service.rows[key]['cell_uuid']
                        for kind,field,target in [('epoch','epoch_tags',key),('cell','cell_tags',target_cell)]:
                            assert sorted((chip['tag'],chip['profile_uuid']) for chip in row['annotations'][field])==sorted((tag,author) for p,author in enumerate(authors) for tag in wanted_tags(kind,target,p))
                        assert row['curation']['revision']==1
                        assert sorted(row['curation']['tags'])==sorted(['dataset:0',*[f'dataset-tag:{j}' for j in range(4)]])
                    with app_db_lock:
                        exact,_=service._epoch_page_identities(protocol,query(predicate));assert tuple(exact)==wanted
                    return value,elapsed
                def child_sql():
                    with app_db_lock:
                        rows=(shared.Annotation&{'project_uuid':project,'target_kind':'epoch'}&[{'target_uuid':key} for key in children]).to_dicts()
                    return sorted((row['target_uuid'],row['profile_uuid'],row['revision'],tuple(sorted(row['tags'])),row['author_name'],str(row['updated_at'])) for row in rows)
                # Native lookup is persistent. The first filter is requested
                # only after the two timed writes, without warming a tag cache.
                prepare_project_annotations=None
                report['preparation_index_seconds']=0
                report['lookup_mode']='persistent_native_sql_no_post_seed_tag_cache_preparation'
                report['bundle_definitions']={
                    'tag10_then10_filter20_http_total':['first10_revision_preflight','first10_save','second10_revision_preflight','second10_save','filter20'],
                    'cell_tag_then_cell_filter_http_total':['cell_save','filter_cell100'],
                    'first10_selected_action_http_total':['first10_revision_preflight','first10_save'],
                    'second10_selected_action_http_total':['second10_revision_preflight','second10_save']}
                for iteration in range(args.samples):
                    p=iteration%3
                    expected=preflight('first10_revision_preflight',first,p)
                    change('first10_save','epoch',first,p,epoch_marker,True,expected)
                    expected=preflight('second10_revision_preflight',second,p)
                    change('second10_save','epoch',second,p,epoch_marker,True,expected)
                    value,_=page('filter20',epoch_predicate,selected)
                    before_children=child_sql()
                    # The rendered page already carries cell revisions, as the
                    # direct-cell editor does; no selected-epoch preflight.
                    cell_expected={cell:value['epochs'][0]['annotations']['revisions']['cell'][authors[p]]}
                    change('cell_save','cell',(cell,),p,cell_marker,True,cell_expected)
                    page('filter_cell100',cell_predicate,children)
                    page('filter_cell100_last_page',cell_predicate,children,offset=40,timed=False)
                    page('filter_cell_and_epoch10',hierarchy,first)
                    page('oracle_cell_marker_not_direct',{'all':[rule(cell_marker,'epoch')]},(),timed=False)
                    assert child_sql()==before_children,'Cell add changed child annotation records'
                    expected=preflight('remove_first10_revision_preflight',first,p)
                    change('remove_first10_save','epoch',first,p,epoch_marker,False,expected)
                    page('filter_hierarchy_after_epoch_remove',hierarchy,())
                    page('filter_remaining10',epoch_predicate,second)
                    expected=preflight('remove_second10_revision_preflight',second,p)
                    change('remove_second10_save','epoch',second,p,epoch_marker,False,expected)
                    page('filter_after_all_epoch_removals',epoch_predicate,())
                    before_children=child_sql()
                    change('remove_cell_save','cell',(cell,),p,cell_marker,False)
                    page('filter_after_cell_removal',cell_predicate,())
                    assert child_sql()==before_children,'Cell removal changed child annotation records'
                    with app_db_lock:assert len(shared.Annotation&{'project_uuid':project,'target_kind':'epoch'})==args.epochs*3
                    for label,parts in report['bundle_definitions'].items():samples.setdefault(label,[]).append(sum(samples[part][-1] for part in parts))
                    log(json.dumps({'stage':'sequence_cycle','epochs':args.epochs,'iteration':iteration+1}))
                def flush_backup():
                    scheduler=app.extensions.get('backup_scheduler')
                    if scheduler is not None:
                        scheduler.flush();report['final_backup_status']=scheduler.status()
                # Separate one-sample diagnostics; neither request warms the
                # measured write/filter sequence above.
                flush_backup()
                autocomplete_explain={};report['autocomplete_sql']={};report['autocomplete_requests']={}
                from collections import Counter,defaultdict
                expected_counts=Counter();expected_authors=defaultdict(set)
                for kind,count in (('epoch',args.epochs),('cell',len(service.cells))):
                    for ordinal in range(count):
                        target_tags=set()
                        for p in range(3):
                            seeded=tags(ordinal,p,cell=kind=='cell');target_tags.update(seeded)
                            for tag in seeded:expected_authors[tag].add(p)
                        expected_counts.update(target_tags)
                empty_candidates=sorted(expected_counts,key=lambda tag:(-expected_counts[tag],tag.casefold(),tag))
                for label,search in (('autocomplete_cold_diagnostic','gate'),('autocomplete_warm_diagnostic','gate'),('autocomplete_empty_diagnostic','')):
                    connection=dj.conn();original_query=connection.query;owner=threading.get_ident();selected_queries=[]
                    def trace_autocomplete_sql(statement,*positional,**keywords):
                        began=time.perf_counter();cursor=None
                        try:
                            cursor=original_query(statement,*positional,**keywords)
                            return cursor
                        finally:
                            if threading.get_ident()==owner and str(statement).lstrip().upper().startswith('SELECT') and any(table in str(statement) for table in ('`app_shared_tag_lookup`','`app_shared_tag_dictionary`','`app_shared_tag_authors`','`shared_annotation`')):
                                selected_queries.append({'sql':str(statement),'seconds':time.perf_counter()-began,'result_rows':getattr(cursor,'rowcount',None)})
                                autocomplete_explain[str(statement)]=positional[0] if positional else keywords.get('args')
                    connection.query=trace_autocomplete_sql
                    try:value,_=measure(label,lambda:request('GET','/api/annotation-tags',query={'q':search,'limit':12}))
                    finally:connection.query=original_query
                    report['autocomplete_sql'][label]=selected_queries
                    report['autocomplete_requests'][label]={'q':search,'limit':12,'total':value['total']}
                    if search:
                        expected=[{'tag':f'gate:{p}','count':(args.epochs+p+1)//(p+2),
                            'authors':[{'profile_uuid':authors[p],'display_name':author_names[p]}]} for p in range(3)]
                        expected_total=3
                    else:
                        expected=[{'tag':tag,'count':expected_counts[tag],
                            'authors':sorted([{'profile_uuid':authors[p],'display_name':author_names[p]} for p in expected_authors[tag]],key=lambda author:author['profile_uuid'])}
                            for tag in empty_candidates[:12]]
                        expected_total=len(empty_candidates)
                    assert value['tags']==expected and value['total']==expected_total,(label,value,expected)
                with app_db_lock:
                    report['autocomplete_query_plans']=[{'sql':statement,'explain':list(connection.query('EXPLAIN '+statement,parameters,as_dict=True,reconnect=False).fetchall())}
                        for statement,parameters in autocomplete_explain.items()]
                check('native_autocomplete_exact_counts_and_profile_authors',True)
                import re
                autocomplete_queries=[item for values in report['autocomplete_sql'].values() for item in values]
                membership_queries=[item for item in autocomplete_queries if '`app_shared_tag_lookup`' in item['sql']]
                check('autocomplete_has_no_membership_aggregation',all(
                    not re.search(r'\b(?:COUNT|SUM|MAX|MIN|AVG)\s*\(|\bGROUP\s+BY\b|\bDISTINCT\b',item['sql'],re.I)
                    and re.search(r'\bLIMIT\s+1\b',item['sql'],re.I)
                    and item['result_rows'] in (0,1) for item in membership_queries),
                    membership_selects=len(membership_queries),maximum_rows_per_seek=max((item['result_rows'] for item in membership_queries),default=0))
                dictionary_queries=[item for item in autocomplete_queries if '`app_shared_tag_dictionary`' in item['sql']]
                check('autocomplete_compact_dictionary_fetches_are_bounded',bool(dictionary_queries) and all(
                    re.search(r'\bCOUNT\s*\(',item['sql'],re.I) or re.search(r'\bLIMIT\b',item['sql'],re.I)
                    for item in dictionary_queries),dictionary_selects=len(dictionary_queries),
                    scope='Counts may scan matching compact entries; no unbounded dictionary rows are fetched for Python prefix filtering.')
                membership_plans=[row for item in report['autocomplete_query_plans'] if '`app_shared_tag_lookup`' in item['sql'] for row in item['explain']]
                check('autocomplete_membership_winner_seeks_are_indexed',all(row.get('key')=='by_tag' and row.get('type') in {'const','ref','range','eq_ref'} for row in membership_plans),plans=membership_plans)
                if args.profile:
                    for name,keys in [('first10',first),('second10',second)]:
                        expected=preflight('profile_'+name+'_preflight',keys,0,timed=False)
                        change('profile_'+name+'_save','epoch',keys,0,epoch_marker,True,expected,timed=False)
                    flush_backup()
                    import re
                    connection=dj.conn();original_query=connection.query;owner=threading.get_ident();sql_calls=[];lookup_selects=[]
                    def traced_query(statement,*positional,**keywords):
                        began=time.perf_counter()
                        try:return original_query(statement,*positional,**keywords)
                        finally:
                            is_filter=threading.get_ident()==owner
                            sql_calls.append({'thread':'filter' if is_filter else 'background','sql_shape':re.sub(r"'[^']*'","'?'",str(statement))[:240],'seconds':time.perf_counter()-began})
                            if is_filter and str(statement).lstrip().upper().startswith('SELECT') and '`app_shared_tag_lookup`' in str(statement):
                                lookup_selects.append((str(statement),positional[0] if positional else keywords.get('args')))
                    profiler=cProfile.Profile();connection.query=traced_query
                    try:profiled=profiler.runcall(lambda:request('GET',base+'/epochs',query=query(epoch_predicate,limit=60,offset=0,include_cells='true')))
                    finally:connection.query=original_query
                    assert profiled['total']==20 and tuple(row['epoch_uuid'] for row in profiled['epochs'])==selected
                    stats=pstats.Stats(profiler);rows=[]
                    for key,value in sorted(stats.stats.items(),key=lambda item:item[1][3],reverse=True):
                        path=Path(key[0]);rows.append({'file':str(path.relative_to(root)) if path.is_absolute() and path.is_relative_to(root) else key[0],
                            'line':key[1],'function':key[2],'primitive_calls':value[0],'calls':value[1],'self_seconds':value[2],'cumulative_seconds':value[3]})
                    report['filter20_cpu_profile']={'top_functions':rows[:100],'native_sql_calls':sql_calls,'limits':'Separate instrumented filter; background mirror flushed before profile. CPU cumulative times overlap.'}
                    assert lookup_selects,'The fresh filter did not execute a native tag lookup SELECT'
                    plans=[]
                    with app_db_lock:
                        for statement,parameters in lookup_selects:
                            explanation=list(connection.query('EXPLAIN '+statement,parameters,as_dict=True,reconnect=False).fetchall())
                            assert any(row.get('key')=='by_tag' and row.get('type') in ('ref','range','const','eq_ref') for row in explanation),explanation
                            plans.append({'sql':statement,'explain':explanation})
                    report['native_lookup_query_plans']=plans
                    check('actual_filter_uses_persistent_by_tag_sql_index',True,queries=len(plans))
                    page('profile_filter20_verify',epoch_predicate,selected,timed=False)
                    from workspace_annotation_preparation import prepare_project_annotations as prepare_native_lookup
                    flush_backup();began=time.perf_counter()
                    with app_db_lock:
                        checkpoint=prepare_native_lookup(service,store,shared,protocol_state=app.extensions.get('protocol_state_reader'))
                        assert checkpoint['status']=='ready' and checkpoint['storage']=='native_sql',checkpoint
                        shared.native_tag_lookup=None
                        reopened=prepare_native_lookup(service,store,shared,protocol_state=app.extensions.get('protocol_state_reader'),reuse=True)
                        assert reopened['status']=='ready' and reopened['storage']=='native_sql' and reopened['reused'],reopened
                    report['same_server_native_lookup_reuse']={'checkpoint':checkpoint,'reopened':reopened,'seconds':time.perf_counter()-began,
                        'scope':'Native lookup checkpoint followed by a fresh Python lookup adapter in the same server; not a MySQL-process restart.'}
                    page('same_server_native_reuse_filter20',epoch_predicate,selected)
                    check('persistent_native_lookup_reused_without_rebuild',True)
                    if prepare_project_annotations is not None:
                        flush_backup();began=time.perf_counter()
                        with app_db_lock:
                            checkpoint=prepare_project_annotations(service,store,shared,protocol_state=app.extensions.get('protocol_state_reader'))
                            assert checkpoint['status']=='ready' and checkpoint['checkpoint']['saved'],checkpoint
                            previous_builds=shared._shared_tag_index.stats['full_builds']
                            shared._shared_tag_index.close()
                            reopened=prepare_project_annotations(service,store,shared,protocol_state=app.extensions.get('protocol_state_reader'),reuse=True)
                            assert reopened['status']=='ready' and reopened['checkpoint_restore']['restored'],reopened
                            after_builds=shared._shared_tag_index.stats['full_builds']
                            assert after_builds in (0,previous_builds),(previous_builds,after_builds)
                        report['same_server_checkpoint_reopen']={'seconds':time.perf_counter()-began,'checkpoint':checkpoint,'reopened':reopened,'full_builds_before':previous_builds,'full_builds_after':after_builds,'scope':'Shared derived index closed and reopened within the same native server; not a native process restart.'}
                        page('same_server_reopened_filter20',epoch_predicate,selected)
                        check('same_server_checkpoint_restores_exact_twenty_without_rebuild',True)
                    for name,keys in [('first10',first),('second10',second)]:
                        change('profile_remove_'+name,'epoch',keys,0,epoch_marker,False,timed=False)
                # Untimed exactness checks run after the measured workflow.
                unicode_oracles=[
                    ('case_upper',{'all':[rule('QC','epoch')]},lambda i:i%2==0),
                    ('case_lower',{'all':[rule('qc','epoch')]},lambda i:i%2==1),
                    ('unicode_nfc',{'all':[rule('é','epoch')]},lambda i:i%3==0),
                    ('unicode_nfd',{'all':[rule('e\u0301','epoch')]},lambda i:i%3!=0),
                    ('or',{'any':[rule('QC','epoch'),rule('é','epoch')]},lambda i:i%2==0 or i%3==0),
                    ('not_with_inheritance',{'all':[rule('cell-common','cell'),{'not':rule('QC','epoch')}]},lambda i:i%2==1),
                    ('inherited_excluded_from_direct',{'all':[rule('cell-common','epoch')]},lambda i:False)]
                for label,predicate,accept in unicode_oracles:
                    wanted=tuple(identity for i,identity in enumerate(ids) if accept(i))
                    page('oracle_'+label,predicate,wanted,timed=False)
                    check('exact_native_'+label,True,count=len(wanted))
                report['sqlite_tag_cache_calls']=dict(sqlite_tag_calls)
                check('no_sqlite_tag_membership_or_refresh_used',not any(sqlite_tag_calls.values()),calls=sqlite_tag_calls)
                flush_backup()
                check('canonical_final_markers_removed',not any(model.values()))
                report['workflow_peak_rss_before_durable_oracle_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                began=time.perf_counter();state=snapshot.load(project_root/'app-state.json');report['durable_snapshot_verify_seconds']=time.perf_counter()-began
                saved={(row['target_kind'],row['target_uuid'],row['profile_uuid']):row for row in state['tables']['shared_annotation']}
                for (kind,key,p),revision in revisions.items():
                    row=saved[(kind,key,authors[p])];assert row['revision']==revision and sorted(row['tags'])==wanted_tags(kind,key,p)
                check('flushed_recovery_mirror_exact_revisions_and_removal',True,records=len(revisions))
                check('one_canonical_cell_record_no_child_copies',sum(row['target_kind']=='epoch' for row in saved.values())==args.epochs*3,child_epochs=len(children))
                check('independent_protocol_curation_untouched',len(state['tables']['curation'])==args.epochs*2 and all(row['revision']==1 for row in state['tables']['curation']))
                loaded={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name.startswith('workspace_') or name=='recording_workspace') and getattr(module,'__file__',None)}
                check('all_product_modules_loaded_from_selected_source',all(Path(path).is_relative_to(root) for path in loaded.values()));report['loaded_product_modules']=loaded
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
