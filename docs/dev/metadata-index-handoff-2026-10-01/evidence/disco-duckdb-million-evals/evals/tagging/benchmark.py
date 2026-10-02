"""Focused native tagging routes against a SQL-backed million-epoch universe.

Not whole-app startup or the production protocol epoch endpoint. SharedAnnotations,
registered Flask routes, MySQL triggers, generation authority, recovery mirror and
BackupScheduler are production implementations. Metadata point lookups and native
membership-to-SQL joins are experimental read-model adapters. No authority contract
is replaced. Sparse annotations are deliberately separate from prior dense100k runs.
"""
import argparse
from collections.abc import Mapping
import datetime as dt
import hashlib
import json
from collections import OrderedDict
import os
from pathlib import Path
import resource
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import traceback


class SQLRows(Mapping):
    def __init__(self, connection, kind):
        self.connection, self.kind = connection, kind
        self.cache=OrderedDict()
        self.column = 'epoch_uuid' if kind == 'epoch' else 'cell_uuid'
        self.amount = connection.execute('SELECT COUNT(' + ('*' if kind == 'epoch' else 'DISTINCT cell_uuid') + ') FROM epochs').fetchone()[0]
    def __len__(self): return self.amount
    def __iter__(self):
        for row in self.connection.execute('SELECT DISTINCT ' + self.column + ' FROM epochs'):
            yield row[0]
    def __getitem__(self, identity):
        if identity in self.cache:
            self.cache.move_to_end(identity);return self.cache[identity]
        row = self.connection.execute('SELECT epoch_uuid,cell_uuid,cell_label,metadata_hash FROM epochs WHERE ' + self.column + '=? LIMIT 1', (identity,)).fetchone()
        if row is None: raise KeyError(identity)
        value=dict(zip(('epoch_uuid','cell_uuid','cell_label','metadata_hash'), row));self.cache[identity]=value
        while len(self.cache)>2048:self.cache.popitem(last=False)
        return value
    def __contains__(self, identity):
        try: self[identity]; return True
        except KeyError: return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--sqlite',type=Path,required=True)
    parser.add_argument('--duckdb',type=Path)
    parser.add_argument('--mysql-runtime-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=10)
    parser.add_argument('--cap-seconds',type=int,default=300)
    args=parser.parse_args()
    root=args.source_root.resolve(strict=True);out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    receipt=out/'receipt.json'
    if receipt.exists(): parser.error('Use an unused output directory')
    os.environ['RIEKE_PREFERENCES_DIR']=str(out/'preferences')
    os.environ['RIEKE_PROJECT_INDEX']=str(out/'preferences'/'projects.json')
    os.environ['RIEKE_USER_PREFERENCES_PATH']=str(out/'preferences.json')
    sys.dont_write_bytecode=True;sys.path[:0]=[str(root/'python'),str(root/'docs/dev/duckdb-million-evals-2026-10-01/readmodel')]
    from flask import Flask,jsonify,request
    from projection import identity
    from workspace_projects import create_project
    from recording_workspace import connect,workspace_tables
    import workspace_native_mysql as native
    from workspace_mysql_runtime import _probe,runtime_spec
    from workspace_service import WorkspaceService
    from workspace_annotations import SharedAnnotations,register_annotation_routes
    from workspace_curation import CurationStore,RevisionConflict
    from workspace_state_generation import bootstrap
    from workspace_annotation_preparation import prepare_project_annotations
    from workspace_state_snapshot import save as save_state
    from workspace_backup_scheduler import BackupScheduler
    runtime=_probe(args.mysql_runtime_root.resolve(strict=True),runtime_spec(root)[0]['mysql_version'])
    native.native_binary=lambda name='mysqld':Path(runtime[name])
    inventory=lambda:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'python').rglob('*.py'))}
    report={'scope':__doc__,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_inventory_before':inventory(),
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'samples':args.samples,'operations':{},'phases':{},'checks':[],'metadata_path':str(args.sqlite.resolve(strict=True)),
            'sparse_seed_epochs':1000,'profiles':3,'tags_per_seed_annotation':5,
            'timing_scope':'Flask test_client JSON including SQL transaction and post-commit recovery scheduling; excludes browser, network, setup and oracle validation. SQL join results explicitly experimental.',
            'full_create_app_run':False,'production_protocol_context_claim':False}
    report['sqlite_membership_fallback_calls']=0
    original_membership=SharedAnnotations._membership_index
    def observed_membership(owner,*arguments,**keywords):
        report['sqlite_membership_fallback_calls']+=1
        return original_membership(owner,*arguments,**keywords)
    # Observation only: do not change native availability or authority decisions.
    SharedAnnotations._membership_index=observed_membership
    started=time.perf_counter();database=duck=dj=project=scheduler=None;lock=threading.RLock()
    def save():receipt.write_text(json.dumps(report,indent=2,default=str))
    def phase(name, callback):
        print(json.dumps({'phase':name,'seconds':time.perf_counter()-started}),flush=True);report['phase']=name;save()
        begin=time.perf_counter();value=callback();report['phases'][name]=time.perf_counter()-begin;save();return value
    def check(name, condition):
        report['checks'].append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    def measure(name, callback):
        begin=time.perf_counter();value=callback();elapsed=time.perf_counter()-begin
        report['operations'].setdefault(name,{'samples_seconds':[]})['samples_seconds'].append(elapsed)
        return value
    def cap(signum, frame):signal.alarm(0);raise TimeoutError('Owned tagging worker cap reached')
    signal.signal(signal.SIGALRM,cap);signal.alarm(args.cap_seconds)
    try:
        database=sqlite3.connect('file:'+str(args.sqlite.resolve(strict=True))+'?mode=ro&immutable=1',uri=True,check_same_thread=False)
        if args.duckdb:
            import duckdb
            duck=duckdb.connect(str(args.duckdb.resolve(strict=True)),read_only=True)
            duck.execute('SET threads=2');duck.execute("SET memory_limit='512MB'")
            report['duckdb_version']=duckdb.__version__;report['duckdb_path']=str(args.duckdb.resolve(strict=True))
        rows=SQLRows(database,'epoch');cells=SQLRows(database,'cell');report['epochs']=len(rows);report['cells']=len(cells)
        check('actual_sql_metadata_contains_one_million_rows',len(rows)==1000000)
        if duck:check('actual_duck_metadata_contains_one_million_rows',duck.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]==len(rows))
        with tempfile.TemporaryDirectory(prefix='owned-native-tags-',dir=out) as directory:
            try:
                project=Path(create_project(Path(directory)/'projects','Disposable million-epoch tag benchmark')['path'])
                phase('owned_native_boot',lambda:native.ensure_native_database(project))
                dj=connect({'kind':'native-project'},project_dir=project)
                service=WorkspaceService.__new__(WorkspaceService);service._loaded=True;service.rows=rows;service.cells=cells
                service.project_dir=project;service.project=json.loads((project/'project.json').read_text());service.config=json.loads((project/'catalog.json').read_text());service.dj=dj;service.protocols={};service.disk_index=None
                Project,*_=workspace_tables(dj);Project.insert1({'project_uuid':service.project['project_uuid'],'name':service.project['name'],'directory':str(project)})
                shared=SharedAnnotations(service);curation=CurationStore(dj,service.project['project_uuid'])
                authors=[identity(900000000+i) for i in range(3)];stamp=dt.datetime(2026,10,1,12)
                def seed():
                    with dj.conn().transaction:
                        shared.Profile.insert([{'project_uuid':service.project['project_uuid'],'profile_uuid':a,'display_name':f'Scientist {i}','created_at':stamp,'created_by':'owned benchmark'} for i,a in enumerate(authors)])
                        for offset in range(0,1000,100):
                            shared.Annotation.insert([{'project_uuid':service.project['project_uuid'],'target_kind':'epoch','target_uuid':identity(k),'profile_uuid':a,'author_name':f'Scientist {i}',
                                'tags':['all','QC' if k%2==0 else 'qc','é' if k%3==0 else 'e\u0301',f'author:{i}',f'bucket:{k%17}'],'revision':1,'updated_at':stamp}
                                for k in range(offset,offset+100) for i,a in enumerate(authors)])
                phase('sparse_canonical_seed',seed)
                report['canonical_seed_records']=3000;report['seed_density']=.001;report['mysql_version']=dj.conn().query('SELECT VERSION()').fetchone()[0]
                shared.state_generation=phase('production_generation_bootstrap',lambda:bootstrap(dj.conn(),service.project['project_uuid']))
                curation.state_generation=shared.state_generation
                phase('initial_production_recovery_checkpoint',lambda:save_state(project,dj.conn(),service=service))
                prep=phase('production_native_lookup_preparation',lambda:prepare_project_annotations(service,curation,shared,protocol_state=None))
                report['annotation_preparation']=prep;check('production_native_lookup_ready',prep['status']=='ready' and shared.native_tag_lookup.ready)
                scheduler=BackupScheduler(lambda:save_state(project,dj.conn(),service=service),lock)
                shared.on_commit=scheduler.request
                app=Flask(__name__);register_annotation_routes(app,service,shared,lock)
                @app.errorhandler(RevisionConflict)
                def conflict(error):return jsonify(error=str(error),current=error.current),409
                @app.errorhandler(ValueError)
                def invalid(error):return jsonify(error=str(error)),400
                @app.after_request
                def persistence(response):
                    if request.endpoint=='annotation_update' and 200<=response.status_code<300:
                        value=response.get_json();value['persistence']={'database':'committed','backup':scheduler.status()};response.set_data(app.json.dumps(value))
                    return response
                client=app.test_client();first=[identity(i) for i in range(10)];second=[identity(100+i) for i in range(10)];selected=first+second
                previously_unannotated=[identity(999900+i) for i in range(10)];fresh_revisions={key:0 for key in previously_unannotated}
                cell=rows[first[0]]['cell_uuid'];children=[r[0] for r in database.execute('SELECT epoch_uuid FROM epochs WHERE cell_uuid=? ORDER BY date,start_time,epoch_uuid',(cell,))]
                check('cell_has_exactly_one_hundred_children',len(children)==100)
                profile=authors[0];marker='sequence-selected';cellmarker='sequence-cell'; revisions={key:1 for key in selected};cell_revision=0
                def req(method,path,body=None,expected=200):
                    response=client.post(path,json=body) if method=='POST' else client.get(path)
                    value=response.get_json();assert response.status_code==expected,(path,response.status_code,value);return value
                def read(keys):return req('POST','/api/annotations/read',{'target_kind':'epoch','target_uuids':keys})
                def change(kind,keys,tag,add,expected):return req('POST','/api/annotations',{'target_kind':kind,'target_uuids':keys,'profile_uuid':profile,
                    'tags_add':[tag] if add else [],'tags_remove':[] if add else [tag],'expected_revisions':expected})
                def canonical_check(keys,tag,present,wanted_revisions):
                    with lock:
                        persisted=(shared.Annotation&{'project_uuid':service.project['project_uuid'],'target_kind':'epoch','profile_uuid':profile}&[{'target_uuid':key} for key in keys]).to_dicts()
                        return (len(persisted)==len(keys) and all(row['revision']==wanted_revisions[row['target_uuid']] and (tag in row['tags'])==present for row in persisted))
                def children_signature():
                    with lock:
                        persisted=(shared.Annotation&{'project_uuid':service.project['project_uuid'],'target_kind':'epoch'}&[{'target_uuid':key} for key in children]).to_dicts()
                        return sorted((row['target_uuid'],row['profile_uuid'],row['revision'],tuple(sorted(row['tags']))) for row in persisted)
                def joined(tag,kinds,metadata=None):
                    metadata=metadata or database
                    with lock:
                        before=shared.generation_token();targets=shared.native_tag_lookup.targets(tag,kinds)
                        direct=[key for kind,key in targets if kind=='epoch'];inherited=[key for kind,key in targets if kind=='cell']
                        predicates=[];values=[]
                        for column,keys in [('epoch_uuid',direct),('cell_uuid',inherited)]:
                            if keys:predicates.append(column+' IN ('+','.join('?' for _ in keys)+')');values.extend(keys)
                        result=[r[0] for r in metadata.execute('SELECT epoch_uuid FROM epochs WHERE '+(' OR '.join(predicates) if predicates else '0')+' ORDER BY date,start_time,epoch_uuid',values).fetchall()]
                        assert shared.generation_token()==before
                        return result
                for iteration in range(args.samples):
                    # Bundle starts from a known persisted revision; validation runs outside timers.
                    for label,keys in [('first10',first),('second10',second)]:
                        with lock:opening_generation=shared.generation_token()
                        begin=time.perf_counter();value=measure('revision_preflight_'+label,lambda keys=keys:read(keys))
                        expected={key:value['targets'][key]['revisions'][profile] for key in keys}
                        result=measure('tag_'+label,lambda keys=keys,expected=expected:change('epoch',keys,marker,True,expected))
                        report['operations'].setdefault('tag_'+label+'_including_preflight',{'samples_seconds':[]})['samples_seconds'].append(time.perf_counter()-begin)
                        check(f'tag_{label}_{iteration}_committed',result['changed']==10 and result['persistence']['database']=='committed')
                        for key in keys:revisions[key]+=1
                        check(f'tag_{label}_{iteration}_canonical_oracle',canonical_check(keys,marker,True,revisions))
                        with lock:closing_generation=shared.generation_token()
                        check(f'tag_{label}_{iteration}_native_generation_advanced',closing_generation is not None and opening_generation is not None and closing_generation.authority==opening_generation.authority and closing_generation.shared_generation>opening_generation.shared_generation)
                    exact=measure('experimental_native_lookup_sql_filter20',lambda:joined(marker,('epoch',)))
                    check(f'filter20_exact_{iteration}',set(exact)==set(selected) and len(exact)==20)
                    if duck:
                        alternative=measure('experimental_native_lookup_duck_filter20',lambda:joined(marker,('epoch',),duck))
                        check(f'duck_filter20_exact_parity_{iteration}',alternative==exact)
                    previous_children=children_signature()
                    result=measure('tag_cell_one_record',lambda:change('cell',[cell],cellmarker,True,{cell:cell_revision}));cell_revision+=1
                    check(f'cell_tag_one_canonical_record_{iteration}',result['changed']==1)
                    check(f'cell_tag_does_not_write_children_{iteration}',previous_children==children_signature())
                    inherited=measure('experimental_native_lookup_sql_cell_filter100',lambda:joined(cellmarker,('cell',)))
                    check(f'cell_filter100_exact_{iteration}',inherited==children)
                    if duck:
                        alternative=measure('experimental_native_lookup_duck_cell_filter100',lambda:joined(cellmarker,('cell',),duck))
                        check(f'duck_cell100_exact_parity_{iteration}',alternative==inherited)
                    predicate={'all':[{'field':'annotations/cell/tags','operator':'contains','value':cellmarker},
                                      {'field':'annotations/epoch/tags','operator':'contains','value':marker}]}
                    scoped_rows=[rows[key] for key in children]
                    with lock:
                        hierarchy=measure('production_native_hierarchy_filter_scoped100',lambda:shared.filter_epoch_ids(scoped_rows,{'tag_predicate':json.dumps(predicate)}))
                    check(f'production_hierarchy_cell_epoch_intersection_{iteration}',hierarchy is not None and set(hierarchy[0])==set(first) and len(hierarchy[0])==10)
                    autocomplete=measure('autocomplete_prefix',lambda:req('GET','/api/annotation-tags?q=sequence&limit=30'))
                    check(f'autocomplete_exact_counts_{iteration}',{row['tag']:row['count'] for row in autocomplete['tags']}=={marker:20,cellmarker:1})
                    result=measure('remove_epoch20',lambda:change('epoch',selected,marker,False,dict(revisions)))
                    check(f'remove20_committed_{iteration}',result['changed']==20)
                    for key in selected:revisions[key]+=1
                    check(f'remove20_canonical_oracle_{iteration}',canonical_check(selected,marker,False,revisions))
                    result=measure('remove_cell_tag',lambda:change('cell',[cell],cellmarker,False,{cell:cell_revision}));cell_revision+=1
                    check(f'cell_tag_removed_{iteration}',result['changed']==1 and joined(cellmarker,('cell',))==[])
                    check(f'epoch_tag_removed_{iteration}',joined(marker,('epoch',))==[])
                    fresh=measure('revision_preflight_previously_unannotated10',lambda:read(previously_unannotated))
                    fresh_expected={key:fresh['targets'][key]['revisions'].get(profile,0) for key in previously_unannotated}
                    result=measure('tag_previously_unannotated10',lambda:change('epoch',previously_unannotated,'fresh-epoch',True,fresh_expected))
                    for key in previously_unannotated:fresh_revisions[key]+=1
                    check(f'fresh10_exact_canonical_{iteration}',result['changed']==10 and canonical_check(previously_unannotated,'fresh-epoch',True,fresh_revisions))
                    result=measure('remove_previously_unannotated10',lambda:change('epoch',previously_unannotated,'fresh-epoch',False,dict(fresh_revisions)))
                    for key in previously_unannotated:fresh_revisions[key]+=1
                    check(f'fresh10_removed_canonical_{iteration}',result['changed']==10 and canonical_check(previously_unannotated,'fresh-epoch',False,fresh_revisions))
                    save()
                # Exact-case/Unicode identities and optimistic conflict: transaction must not partially commit.
                lookup=shared.native_tag_lookup
                with lock:
                    check('case_sensitive_QC_vs_qc',lookup.targets('QC',('epoch',))!=lookup.targets('qc',('epoch',)))
                    check('unicode_composed_vs_decomposed_exact',lookup.targets('é',('epoch',))!=lookup.targets('e\u0301',('epoch',)))
                    before=shared.generation_token();old=read(first)
                    bad={key:old['targets'][key]['revisions'][profile] for key in first};bad[first[-1]]-=1
                    req('POST','/api/annotations',{'target_kind':'epoch','target_uuids':first,'profile_uuid':profile,'tags_add':['must-not-commit'],'tags_remove':[],'expected_revisions':bad},expected=409)
                    check('revision_conflict_has_no_partial_write',shared.generation_token()==before and read(first)==old and not lookup.targets('must-not-commit'))
                    req('POST','/api/annotations/read',{'target_kind':'epoch','target_uuids':[identity(-99999999)]},expected=400)
                    check('unregistered_target_rejected_without_generation_change',shared.generation_token()==before)
                phase('final_production_recovery_flush',scheduler.flush)
                check('recovery_scheduler_current',scheduler.status()['status']=='current')
                from workspace_state_snapshot import load
                recovered=load(project/'app-state.json');report['recovery_shape']=list(recovered) if isinstance(recovered,dict) else type(recovered).__name__
                with lock:
                    canonical=shared.Annotation.to_dicts()
                def content(record):return {key:record[key] for key in ('project_uuid','target_kind','target_uuid','profile_uuid','tags','author_name','revision')}
                sortkey=lambda row:(row['target_kind'],row['target_uuid'],row['profile_uuid'])
                check('recovery_exactly_matches_canonical_annotation_content',sorted(map(content,canonical),key=sortkey)==sorted(map(content,recovered['tables']['shared_annotation']),key=sortkey))
                report['native_authority_ready']=shared.generation_token() is not None
                check('zero_sqlite_membership_fallback_calls',report['sqlite_membership_fallback_calls']==0)
                report['row_cache_entries']=len(rows.cache)
                report['successful_operations']=True
            finally:
                with lock:
                    if scheduler:scheduler.close(flush=False)
                    if dj:dj.conn().close()
                if project:report['owned_native_runtime_stopped']=native.stop_native_database(project)
    except BaseException as error:
        report['error']=str(error);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
    finally:
        signal.alarm(0)
        if database:database.close()
        if duck:duck.close()
        SharedAnnotations._membership_index=original_membership
        for value in report['operations'].values():
            samples=value['samples_seconds'];value.update(first_seconds=samples[0],median_seconds=statistics.median(samples),warm_median_seconds=statistics.median(samples[1:]) if len(samples)>1 else None,maximum_seconds=max(samples))
        report['seconds']=time.perf_counter()-started;report['peak_worker_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['source_inventory_after']=inventory();report['source_unchanged']=report['source_inventory_before']==report['source_inventory_after']
        report['passed']=bool(report.get('successful_operations') and report.get('owned_native_runtime_stopped') and report['source_unchanged'] and all(c['passed'] for c in report['checks']) and not report.get('error'))
        save();print(json.dumps({'passed':report['passed'],'seconds':report['seconds']}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
