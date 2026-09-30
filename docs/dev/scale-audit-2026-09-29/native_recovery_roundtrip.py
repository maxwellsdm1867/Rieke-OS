"""Independent native current-state recovery and actual SQL restore oracle.

Uses the production DataJoint bookkeeping table factories and real MySQL in an
owned disposable project. Source references and scientific values are synthetic;
this does not claim H5 parsing, browser, NAS or physical power-loss coverage.
"""
import argparse
import contextlib
import copy
import datetime as dt
import errno
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import traceback
from types import SimpleNamespace
import uuid
from unittest.mock import patch

import pymysql
from recording_workspace import connect,workspace_tables
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database,stop_native_database,connection_parameters,_owned_process
from workspace_annotations import annotation_tables
from workspace_curation import curation_tables
from workspace_datastores import lifecycle_table
from workspace_explorer import explorer_table,protocol_binding_table
from workspace_search_presets import preset_tables,query_run_table
from workspace_tree_layouts import layout_table
import workspace_recovery_generation as generation
import workspace_recovery_store as mirror
import workspace_state_snapshot as snapshot


def uid(value):return str(uuid.UUID(int=value))


class SecondConnection:
    """Independent PyMySQL client; no state or change behavior is simulated."""
    def __init__(self,root):self.root=root;self.in_transaction=False;self.reconnect()
    def reconnect(self):self._conn=pymysql.connect(**connection_parameters(self.root),autocommit=True)
    def query(self,statement,args=None,as_dict=False,reconnect=False):
        cursor=self._conn.cursor(pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor);cursor.execute(statement,args);return cursor
    @property
    @contextlib.contextmanager
    def transaction(self):
        self._conn.begin();self.in_transaction=True
        try:yield;self._conn.commit()
        except BaseException:self._conn.rollback();raise
        finally:self.in_transaction=False
    def close(self):self._conn.close()


def plain(value):
    return json.loads(json.dumps(value,ensure_ascii=False,default=lambda item:item.isoformat()))


def canonical(state):
    state=plain(state)
    for rows in state['tables'].values():rows.sort(key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False))
    return json.dumps(state,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


JSON_FIELDS={'shared_annotation':{'tags'},'curation':{'tags'},'protocol_workspace':{'definition'},
    'protocol_tree_layout':{'split_order'},'search_preset':{'predicate'},'search_preset_version':{'recipe'},
    'explorer_revision':{'summary','recipe'},'dataset_revision':{'recipe'},'search_query_last_run':{'result'},'source':{'manifest'}}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--retention-stress',action='store_true');ap.add_argument('--legacy-migrations',action='store_true');args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new receipt path')
    modules=(generation,mirror,snapshot);hashes=lambda:{module.__name__:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() for module in modules}
    report={'scope':__doc__,'source_hashes_before':hashes(),'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[],'release_ready':False}
    temporary=Path(tempfile.mkdtemp(prefix='rieke-native-recovery-')).resolve();root=None;dj=None;second=None;clean=False
    def check(name,passed,**detail):
        item={'name':name,'passed':bool(passed),**detail};report['cases'].append(item);print(json.dumps(item,default=str),flush=True)
        if not passed:raise AssertionError(name)
    try:
        root=Path(create_project(temporary/'projects','Independent recovery oracle')['path']);runtime=ensure_native_database(root)
        dj=connect({'kind':'native-project'},project_dir=root);connection=dj.conn();second=SecondConnection(root)
        project=json.loads((root/'project.json').read_text());project_id=project['project_uuid'];stamp=dt.datetime(2026,9,29,10,11,12)
        protocol,other_protocol,revision,old_revision,preset,profile,cell=map(uid,(10,11,20,21,30,40,50));epochs=[uid(100),uid(101)]
        Project,Source,Event,Workspace=workspace_tables(dj);Profile,Annotation=annotation_tables(dj);Curation,Dataset=curation_tables(dj)
        Preset,Version=preset_tables(dj)
        tables={'annotation_profile':Profile,'shared_annotation':Annotation,'curation':Curation,'protocol_workspace':Workspace,
            'data_store_state':lifecycle_table(dj,Event),'protocol_tree_layout':layout_table(dj),'search_preset':Preset,
            'search_preset_version':Version,'protocol_binding':protocol_binding_table(dj),'explorer_revision':explorer_table(dj),
            'dataset_revision':Dataset,'search_query_last_run':query_run_table(dj)}
        Project.insert1({'project_uuid':project_id,'name':project['name'],'directory':str(root)})
        definition={'format':'recording-protocol-workspace','version':1,'project_uuid':project_id,'protocol_uuid':protocol,
            'query':{'version':1,'all':[{'field':'EpochBlock.protocol_name','operator':'eq','value':'Synthetic'}]},'initial_revision_uuid':revision}
        (root/'protocols').mkdir(exist_ok=True);(root/'protocols'/(protocol+'.json')).write_text(json.dumps(definition))
        manifest={'source_path':'/synthetic/source.h5','metadata_path':'/synthetic/source.json','metadata_sha256':'b'*64,'parser_sha256':'c'*64,'adapter_version':2}
        source={'source_sha256':'a'*64,'project_uuid':project_id,'experiment_uuid':uid(200),'experiment_id':1,'manifest':manifest}
        Source.insert1(source)
        model={table:[] for table in snapshot.TABLES}
        for p in range(3):
            author=uid(40+p);name='Same display name' if p<2 else 'Third author'
            model['annotation_profile'].append(dict(project_uuid=project_id,profile_uuid=author,display_name=name,created_at=stamp,created_by='oracle'))
            for kind,target in [('cell',cell),*[('epoch',epoch) for epoch in epochs]]:
                model['shared_annotation'].append(dict(project_uuid=project_id,target_kind=kind,target_uuid=target,profile_uuid=author,
                    tags=['QC','qc','é','e\u0301','tag-'+str(p)]+(['pin-only'] if kind=='epoch' and p==0 else []),author_name=name,revision=1,updated_at=stamp))
        for protocol_id in (protocol,other_protocol):
            for epoch in epochs:model['curation'].append(dict(project_uuid=project_id,protocol_uuid=protocol_id,epoch_uuid=epoch,
                included=1,tags=['QC','independent-'+protocol_id],review_state='unreviewed',revision=1,metadata_fingerprint='d'*64))
        members=[{'uuid':epoch,'metadata_hash':'d'*64} for epoch in epochs]
        recipe={'revision_uuid':revision,'epochs':members,'predicate':{'field':'annotations/epoch/tags','operator':'contains','value':'pin-only'},
            'source_revisions':['a'*64],'typed':{'bool':True,'integer':1,'float':1.0,'null':None,'empty':[]}}
        model['protocol_workspace']=[dict(project_uuid=project_id,protocol_uuid=protocol,definition=definition)]
        model['data_store_state']=[dict(project_uuid=project_id,source_sha256='a'*64,version=1,frozen=0,archived=0,query_excluded=0,
            updated_at=stamp,actor='oracle',actor_kind='local_user',server_actor='oracle',reason='fixture')]
        model['protocol_tree_layout']=[dict(project_uuid=project_id,protocol_uuid=protocol,split_order=['cell_uuid','epoch_uuid'],version=1,updated_at=stamp,actor='oracle')]
        model['search_preset']=[dict(project_uuid=project_id,preset_uuid=preset,name='Pinned QC',description='fixture',predicate=recipe['predicate'],splits='cell_uuid',pinned=1,version=1,updated_at=stamp,actor='oracle')]
        model['search_preset_version']=[dict(project_uuid=project_id,preset_uuid=preset,version=version,recipe={'version':version,'predicate':recipe['predicate']}) for version in (0,1)]
        model['protocol_binding']=[dict(project_uuid=project_id,protocol_uuid=protocol,revision_uuid=revision,version=1,bound_at=stamp)]
        model['explorer_revision']=[dict(project_uuid=project_id,revision_uuid=value,created_at=stamp,name='Frozen pin',parent_revision_uuid=None,
            summary={'epoch_count':2},recipe={**recipe,'revision_uuid':value}) for value in (revision,old_revision)]
        model['dataset_revision']=[dict(project_uuid=project_id,dataset_uuid=uid(300),protocol_uuid=protocol,created_at=stamp,actor='oracle',
            recipe={'epochs':members,'typed':recipe['typed']},artifact_path='/synthetic/reference.zip',artifact_sha256='e'*64,epoch_count=2)]
        model['search_query_last_run']=[dict(project_uuid=project_id,query_sha256='f'*64,result={'epochs':2,'typed':recipe['typed']})]
        with connection.transaction:
            for table,rows in model.items():tables[table].insert(rows)
        model=plain(model);protocol_files={protocol+'.json':copy.deepcopy(definition)}
        def expected_state():
            current=copy.deepcopy(model)
            current['search_preset_version']=[row for row in current['search_preset_version'] if row['version']==current['search_preset'][0]['version']] if current['search_preset'] else []
            pinned={row['revision_uuid'] for row in current['protocol_binding']}
            pinned.update(value.get('initial_revision_uuid') for value in protocol_files.values())
            current['explorer_revision']=[row for row in current['explorer_revision'] if row['revision_uuid'] in pinned]
            return {'format':'rieke-app-state','version':1,'project':copy.deepcopy(project),'source_sha256s':['a'*64],
                'source_references':[{'source_sha256':'a'*64,**source['manifest']}], 'protocols':copy.deepcopy(protocol_files),'tables':current}
        service=SimpleNamespace();service_two=SimpleNamespace()
        def save(name,*,client=None,owner=None,incremental=None):
            client=connection if client is None else client;owner=service if owner is None else owner
            started=time.perf_counter();result=snapshot.save(root,client,service=owner,day='2026-09-29')
            loaded=snapshot.load(root/'app-state.json');wanted=expected_state()
            check(name,canonical(loaded)==canonical(wanted) and (incremental is None or result['incremental']==incremental),
                incremental=result['incremental'],seconds=time.perf_counter()-started)
            return result
        def update(table,index,field,value,*,client=second):
            row=model[table][index]
            names=[key['Column_name'] for key in sorted(connection.query(f"SHOW INDEX FROM recording_workspace.`{table}` WHERE Key_name='PRIMARY'",as_dict=True).fetchall(),key=lambda item:item['Seq_in_index'])]
            statement=f'UPDATE recording_workspace.`{table}` SET `{field}`=%s WHERE '+' AND '.join('`'+name+'`=%s' for name in names)
            stored=json.dumps(value,ensure_ascii=False) if field in JSON_FIELDS.get(table,set()) else value
            client.query(statement,(stored,*(row[name] for name in names)));row[field]=plain(value)
        save('initial_full_native_baseline',incremental=False)
        # Both clients establish their observers before testing reversed save order.
        service_two._recovery_tracker=generation.RecoveryTracker(second,project_id).bootstrap()
        check('second_native_tracker_ready',service_two._recovery_tracker.ready,reason=service_two._recovery_tracker.reason)
        save('baseline_after_second_client_bootstrap')
        update('shared_annotation',1,'tags',['qc','same revision edit']);save('same_revision_shared_sql_is_incremental',incremental=True)
        loaded=snapshot.load(root/'app-state.json')
        check('frozen_tag_pin_keeps_exact_members',loaded['tables']['explorer_revision'][0]['recipe']['epochs']==members and 'requery' not in loaded['tables']['explorer_revision'][0]['recipe'])
        changes=[('annotation_profile','display_name','Renamed profile'),('protocol_workspace','definition',{**definition,'external_note':'changed'}),
            ('data_store_state','reason','external reason'),('protocol_tree_layout','split_order',['epoch_uuid','cell_uuid']),
            ('search_preset','name','Renamed preset'),('search_preset_version','recipe',{'version':1,'changed':True}),
            ('protocol_binding','version',2),('explorer_revision','name','Renamed frozen pin'),('dataset_revision','actor','external author'),
            ('search_query_last_run','result',{'epochs':1,'typed':recipe['typed']})]
        full_tables={'search_preset','search_preset_version','protocol_binding','explorer_revision','dataset_revision'}
        for table,field,value in changes:
            index=1 if table=='search_preset_version' else 0;update(table,index,field,value)
            save('external_'+table+'_covered',incremental=table not in full_tables)
        update('curation',0,'tags',['curation','same version']);save('same_revision_curation_sql_is_incremental',incremental=True)
        update('shared_annotation',2,'target_uuid',uid(888));save('shared_target_key_move_is_incremental',incremental=True)
        update('curation',0,'protocol_uuid',uid(889));save('curation_protocol_key_move_is_incremental',incremental=True)
        update('shared_annotation',5,'project_uuid',uid(999));moved=model['shared_annotation'].pop(5)
        save('project_key_move_out_removes_recovery_row',incremental=True)
        second.query('UPDATE recording_workspace.shared_annotation SET project_uuid=%s WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',
            (project_id,uid(999),moved['target_kind'],moved['target_uuid'],moved['profile_uuid']))
        model['shared_annotation'].insert(5,{**moved,'project_uuid':project_id});save('project_key_move_back_restores_exact_row',incremental=True)
        update('shared_annotation',1,'tags',['client A committed'])
        update('shared_annotation',1,'tags',['client B committed later'])
        save('later_commit_saves_first',client=second,owner=service_two,incremental=True)
        save('earlier_request_saves_later_without_rewind',incremental=True)
        before=snapshot.load(root/'app-state.json');second._conn.begin()
        second.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE project_uuid=%s',(json.dumps(['must roll back']),project_id));second._conn.rollback()
        save('rolled_back_changes_do_not_enter_recovery',incremental=True)
        check('rollback_preserves_exact_mirror',canonical(snapshot.load(root/'app-state.json'))==canonical(before))
        # Failure occurs after SQL committed. The next different save must cover
        # both mutations; no production loader computes these expected values.
        update('shared_annotation',3,'tags',['SQL committed but backup failed'])
        original=mirror._write_rows
        def failed(*a,**kw):original(*a,**kw);raise OSError(errno.ENOSPC,'injected mirror disk full')
        with patch.object(mirror,'_write_rows',side_effect=failed):
            try:snapshot.save(root,connection,service=service,day='2026-09-29')
            except OSError:failed_as_expected=True
            else:failed_as_expected=False
        check('committed_sql_backup_failure_propagates',failed_as_expected and canonical(snapshot.load(root/'app-state.json'))==canonical(before))
        update('data_store_state',0,'reason','second mutation after failure');save('next_save_repairs_unprotected_gap',incremental=False)
        # A stale mirror must not use a pruned change feed as if it were complete.
        current=mirror.inspect(root);old_copy=temporary/'old-mirror.sqlite';shutil.copy2(current['path'],old_copy)
        update('shared_annotation',4,'tags',['after retained floor']);save('advance_and_prune_feed',incremental=True)
        service._recovery_tracker.prune(mirror.inspect(root)['header']['watermark'],keep_generations=0)
        shutil.copy2(old_copy,current['path']);save('old_mirror_below_prune_floor_forces_full',incremental=False)
        second.query('DELETE FROM recording_workspace.app_recovery_clock WHERE project_uuid=%s',(project_id,));save('missing_clock_forces_full',incremental=False)
        second.query('TRUNCATE TABLE recording_workspace.app_recovery_changes');save('feed_truncate_forces_full',incremental=False)
        source['manifest']['source_path']='/synthetic/relocated.h5'
        second.query('UPDATE recording_workspace.source SET manifest=%s WHERE source_sha256=%s',(json.dumps(source['manifest']),'a'*64));save('source_header_change_forces_full',incremental=False)
        project['name']='Updated project descriptor';(root/'project.json').write_text(json.dumps(project));save('project_file_change_forces_full',incremental=False)
        protocol_files[protocol+'.json']['note']='Updated protocol file';(root/'protocols'/(protocol+'.json')).write_text(json.dumps(protocol_files[protocol+'.json']));save('protocol_file_change_forces_full',incremental=False)
        if args.retention_stress:
            old_generation=mirror.inspect(root)['header']['watermark']['generation']
            doomed=model['shared_annotation'].pop();doomed_key=[doomed[name] for name in ('project_uuid','target_kind','target_uuid','profile_uuid')]
            second.query('DELETE FROM recording_workspace.shared_annotation WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',doomed_key)
            count=generation.RECOVERY_WINDOW+2*generation.TRIM_INTERVAL
            extras=[dict(project_uuid=project_id,target_kind='epoch',target_uuid=uid(10000+i),profile_uuid=profile,
                         tags=['QC','qc','é','e\u0301',f'retention-{i}'],author_name='Retention oracle',revision=1,updated_at=stamp.isoformat())
                    for i in range(count)]
            started=time.perf_counter()
            with second.transaction:
                with second._conn.cursor() as cursor:
                    for start in range(0,count,1000):
                        cursor.executemany('INSERT INTO recording_workspace.shared_annotation '
                            '(project_uuid,target_kind,target_uuid,profile_uuid,tags,author_name,revision,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                            [(row['project_uuid'],row['target_kind'],row['target_uuid'],row['profile_uuid'],json.dumps(row['tags'],ensure_ascii=False),row['author_name'],row['revision'],stamp)
                             for row in extras[start:start+1000]])
            model['shared_annotation'].extend(extras)
            floor=second.query('SELECT generation,retained_after FROM recording_workspace.app_recovery_clock WHERE project_uuid=%s',(project_id,)).fetchone()
            feed_count=second.query('SELECT COUNT(*) FROM recording_workspace.app_recovery_changes WHERE project_uuid=%s',(project_id,)).fetchone()[0]
            ring='slot' in {row[0] for row in second.query('SHOW COLUMNS FROM recording_workspace.app_recovery_changes').fetchall()}
            maximum=generation.RECOVERY_WINDOW if ring else generation.RECOVERY_WINDOW+generation.TRIM_INTERVAL-1
            check('trigger_retention_bounds_unsaved_feed_and_advances_floor',floor[1]>old_generation and feed_count<=maximum,
                  old_generation=old_generation,generation=floor[0],retained_after=floor[1],feed_rows=feed_count,inserted=count,seconds=time.perf_counter()-started)
            save('expired_delete_tombstone_requires_full_without_resurrecting_row',incremental=False)
            def delete_extras():
                with second._conn.cursor() as cursor:
                    for start in range(0,count,1000):
                        cursor.executemany('DELETE FROM recording_workspace.shared_annotation WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',
                            [(row['project_uuid'],row['target_kind'],row['target_uuid'],row['profile_uuid']) for row in extras[start:start+1000]])
            if ring:
                def ring_state():
                    clock=second.query('SELECT scope_epoch,generation,retained_after FROM recording_workspace.app_recovery_clock WHERE project_uuid=%s',(project_id,)).fetchall()
                    rows=second.query('SELECT slot,table_id,key_bytes,generation,deleted FROM recording_workspace.app_recovery_changes WHERE project_uuid=%s ORDER BY slot',(project_id,)).fetchall()
                    return hashlib.sha256(repr((clock,rows)).encode()).hexdigest()
                ring_before=ring_state();second._conn.begin();delete_extras()
                overwritten=ring_state()!=ring_before;second._conn.rollback()
                check('rolled_back_full_ring_overwrite_restores_every_slot_and_floor',overwritten and ring_state()==ring_before)
                save('ring_rollback_preserves_complete_scientific_state',incremental=True)
            with second.transaction:delete_extras()
            del model['shared_annotation'][-count:]
            save('expired_bulk_deletion_feed_requires_full_without_resurrection',incremental=False)
        if args.legacy_migrations:
            specs=generation.table_specs(connection)
            def trigger_rows():
                return second.query('SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT '
                    'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s ORDER BY TRIGGER_NAME',(generation.SCHEMA,),as_dict=True).fetchall()
            def install(trigger_name,trigger):
                second.query(f'CREATE TRIGGER recording_workspace.`{trigger_name}` AFTER {trigger["event"]} ON '
                    f'recording_workspace.`{trigger["table"]}` FOR EACH ROW {trigger["body"]}')
            for trim in (False,True):
                label='trimmed' if trim else 'untrimmed'
                for row in trigger_rows():
                    if row['TRIGGER_NAME'].startswith(generation.PREFIX):second.query(f'DROP TRIGGER recording_workspace.`{row["TRIGGER_NAME"]}`')
                second.query('DROP TABLE recording_workspace.app_recovery_changes')
                second.query('CREATE TABLE recording_workspace.app_recovery_changes (project_uuid varchar(36) NOT NULL,'
                    'table_id smallint unsigned NOT NULL,key_bytes varbinary(1024) NOT NULL,generation bigint unsigned NOT NULL,'
                    'deleted tinyint unsigned NOT NULL,PRIMARY KEY(project_uuid,table_id,key_bytes),'
                    'KEY generation_lookup(project_uuid,generation)) ENGINE=InnoDB')
                old=generation.manifest_from_specs(specs,legacy=trim)
                for name,trigger in old.items():install(name,trigger)
                update('shared_annotation',0,'tags',['QC','qc','é','e\u0301','legacy-'+label])
                save('legacy_'+label+'_migration_forces_exact_full_checkpoint',incremental=False)
                columns=second.query('SHOW COLUMNS FROM recording_workspace.app_recovery_changes').fetchall()
                check('legacy_'+label+'_feed_migrates_to_fixed_slots',any(row[0]=='slot' for row in columns))
            expected=generation.manifest_from_specs(specs);name=next(iter(expected));trigger=expected[name]
            second.query(f'DROP TRIGGER recording_workspace.`{name}`')
            install(name,{**trigger,'body':'BEGIN SET @recovery_oracle_unknown = 1; END'})
            before_triggers=trigger_rows();before_table=second.query("SELECT TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME='recording_workspace/app_recovery_changes'").fetchone()
            rejected=generation.RecoveryTracker(second,project_id).bootstrap()
            check('unknown_owned_trigger_body_refuses_without_replacing_tables_or_triggers',not rejected.ready and trigger_rows()==before_triggers and
                second.query("SELECT TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME='recording_workspace/app_recovery_changes'").fetchone()==before_table,
                reason=rejected.reason)
            second.query(f'DROP TRIGGER recording_workspace.`{name}`');install(name,trigger)
            save('known_trigger_repair_forces_exact_full_checkpoint',incremental=False)
        before_clock=connection.query('SELECT scope_epoch,generation FROM recording_workspace.app_recovery_clock WHERE project_uuid=%s',(project_id,)).fetchone()
        second._conn.begin()
        second.query('UPDATE recording_workspace.shared_annotation SET tags=%s WHERE project_uuid=%s',(json.dumps(['uncommitted at server crash']),project_id))
        owned=_owned_process(runtime)
        if owned is None:raise AssertionError('Owned disposable MySQL process is missing')
        owned.kill();owned.wait(timeout=10)
        with contextlib.suppress(Exception):second.close()
        with contextlib.suppress(Exception):connection.close()
        runtime=ensure_native_database(root);dj=connect({'kind':'native-project'},project_dir=root);connection=dj.conn(reset=True);second.reconnect()
        service=SimpleNamespace();service_two=SimpleNamespace()
        after_clock=connection.query('SELECT scope_epoch,generation FROM recording_workspace.app_recovery_clock WHERE project_uuid=%s',(project_id,)).fetchone()
        check('server_sigkill_rolls_back_source_and_recovery_clock_together',before_clock==after_clock)
        save('restart_forces_coherent_full_recovery_checkpoint',incremental=False)
        # Restore actual SQL after all current authored tables are cleared.
        desired=expected_state();restore_point=temporary/'restore-point.sqlite';shutil.copy2(mirror.inspect(root)['path'],restore_point)
        with second.transaction:
            for table in snapshot.TABLES:second.query(f'DELETE FROM recording_workspace.`{table}` WHERE project_uuid=%s',(project_id,))
        (root/'protocols'/(protocol+'.json')).write_text(json.dumps({'temporary':'must be replaced'}))
        with patch.object(snapshot,'query_service',side_effect=AssertionError('Explicit frozen members must never be requeried')):
            result=snapshot.restore(root,connection,restore_point)
        check('actual_sql_restore_exact_current_state',canonical(snapshot.load(root/'app-state.json'))==canonical(desired))
        actual={}
        for table in snapshot.TABLES:
            rows=connection.query(f'SELECT * FROM recording_workspace.`{table}` WHERE project_uuid=%s',(project_id,),as_dict=True).fetchall()
            actual[table]=[{key:json.loads(value) if key in JSON_FIELDS.get(table,set()) and isinstance(value,(str,bytes)) else value for key,value in row.items()} for row in rows]
        check('restored_native_rows_match_independent_oracle',canonical({**desired,'tables':actual})==canonical(desired))
        check('restored_protocol_file_exact',json.loads((root/'protocols'/(protocol+'.json')).read_text())==desired['protocols'][protocol+'.json'])
        check('no_op_save_remains_incremental',snapshot.save(root,connection,service=service,day='2026-09-29')['incremental'])
        report['storage']=mirror.storage(root);report['source_hashes_after']=hashes();report['source_unchanged']=report['source_hashes_before']==report['source_hashes_after']
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};print(traceback.format_exc(),flush=True)
    finally:
        if second is not None:
            with contextlib.suppress(Exception):second.close()
        if dj is not None:
            with contextlib.suppress(Exception):dj.conn().close()
        if root is not None:
            try:clean=stop_native_database(root)
            except Exception as error:report['shutdown_error']=str(error)
        report['clean_native_shutdown']=clean
        if clean:shutil.rmtree(temporary);report['temporary_project_removed']=True
        else:report['preserved_temporary_project']=str(temporary)
        report['passed']=not report.get('error') and clean and report.get('source_unchanged',False) and all(item['passed'] for item in report['cases'])
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n')
    return int(not report['passed'])


if __name__=='__main__':raise SystemExit(main())
