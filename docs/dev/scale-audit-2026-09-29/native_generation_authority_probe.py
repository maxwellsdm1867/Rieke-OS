"""Independent native checks of the production generation authority.

Only creates its own disposable project; intentionally kills only the verified
owned MySQL child. Minimal source tables exercise the real production triggers.
This does not certify DataJoint/service integration or artifact restore.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import time
import traceback
import uuid

import pymysql
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database, stop_native_database, connection_parameters, _owned_process
import workspace_state_generation as generation


class Connection:
    """Only adapt cursor/result spelling; no generation behavior is emulated."""
    def __init__(self, project):
        self.project=project;self.in_transaction=False;self.reconnect()
    def reconnect(self):
        self._conn=pymysql.connect(**connection_parameters(self.project),autocommit=True)
    def query(self,sql,args=(),as_dict=False,reconnect=False):
        cursor=self._conn.cursor(pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor)
        cursor.execute(sql,args);return cursor
    def close(self):
        self._conn.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose an unused output file')
    root=Path(tempfile.mkdtemp(prefix='rieke-native-authority-'));project=None;connections=[]
    before_hash=hashlib.sha256(Path(generation.__file__).read_bytes()).hexdigest()
    report={'scope':'Production authority + native SQL; minimal source table adapter; not service/restore certification',
            'source_sha256_before':before_hash,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'cases':[],'release_ready':False}
    def check(name,condition,**extra):
        row={'name':name,'passed':bool(condition),**extra};report['cases'].append(row);print(json.dumps(row,default=str),flush=True)
        if not condition:raise AssertionError(name)
    try:
        project=Path(create_project(root/'projects','Native authority probe')['path']);runtime=ensure_native_database(project)
        connection=Connection(project);other=Connection(project);connections=[connection,other]
        sql=lambda statement,params=():connection.query(statement,params).fetchall()
        external=lambda statement,params=():other.query(statement,params).fetchall()
        project_id=str(uuid.UUID(int=1));project_two=str(uuid.UUID(int=2));protocol=str(uuid.UUID(int=3));protocol_two=str(uuid.UUID(int=4))
        epoch=str(uuid.UUID(int=5));epoch_two=str(uuid.UUID(int=6));profile=str(uuid.UUID(int=7));profile_two=str(uuid.UUID(int=8))
        report['mysql_version']=sql('SELECT VERSION()')[0][0]
        sql('CREATE DATABASE IF NOT EXISTS recording_workspace')
        definitions={
            'curation':'project_uuid VARCHAR(36),protocol_uuid VARCHAR(36),epoch_uuid VARCHAR(36),tags JSON,revision INT UNSIGNED,PRIMARY KEY(project_uuid,protocol_uuid,epoch_uuid)',
            'shared_annotation':'project_uuid VARCHAR(36),target_kind VARCHAR(16),target_uuid VARCHAR(36),profile_uuid VARCHAR(36),tags JSON,author_name VARCHAR(120),revision INT UNSIGNED,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid)',
            'annotation_profile':'project_uuid VARCHAR(36),profile_uuid VARCHAR(36),display_name VARCHAR(120),PRIMARY KEY(project_uuid,profile_uuid)',
        }
        for table,definition in definitions.items():sql(f'CREATE TABLE recording_workspace.{table} ({definition}) ENGINE=InnoDB')
        authority=generation.bootstrap(connection,project_id);other_authority=generation.bootstrap(other,project_id)
        check('bootstrap',authority.ready and other_authority.ready,reason=authority.reason)
        external("SELECT GET_LOCK('rieke_state_generation_v1',0)")
        def release_bootstrap():
            time.sleep(.1);external("SELECT RELEASE_LOCK('rieke_state_generation_v1')")
        releaser=threading.Thread(target=release_bootstrap,daemon=True);releaser.start();started=time.perf_counter()
        try:contended=generation.bootstrap(connection,project_id)
        finally:releaser.join(timeout=5)
        check('concurrent_bootstrap_waits_and_recovers',contended.ready and time.perf_counter()-started>=.08,reason=contended.reason)
        def token(ident=protocol):
            value=authority.token(ident)
            if value is None:raise AssertionError('Authority unavailable: '+str(authority.reason))
            return value
        def head(value):return (value.protocol_epoch,value.protocol_generation)
        initial=token();check('second_connection_agrees_on_scope',head(initial)==head(other_authority.token(protocol)))
        external('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',(project_id,protocol,epoch,json.dumps(['QC','qc','é','e\u0301','first'])))
        inserted=token();check('curation_insert',head(initial)!=head(inserted))
        external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['QC','qc','é','e\u0301','other']),))
        updated=token();check('same_revision_external_update',head(inserted)!=head(updated) and sql('SELECT revision FROM recording_workspace.curation')==((1,),))
        external('REPLACE INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',(project_id,protocol,epoch,json.dumps(['replacement'])))
        replaced=token();check('replace_delete_and_insert',replaced.protocol_generation==updated.protocol_generation+2)
        old_two=token(protocol_two)
        external('UPDATE recording_workspace.curation SET protocol_uuid=%s',(protocol_two,))
        moved=token();new_two=token(protocol_two);check('protocol_key_move_invalidates_both',head(moved)!=head(replaced) and head(old_two)!=head(new_two))
        third=generation.bootstrap(other,project_two);old_project=token(protocol_two);new_project=third.token(protocol_two)
        external('UPDATE recording_workspace.curation SET project_uuid=%s',(project_two,))
        check('project_key_move_invalidates_both',head(old_project)!=head(token(protocol_two)) and head(new_project)!=head(third.token(protocol_two)))
        external('UPDATE recording_workspace.curation SET project_uuid=%s,protocol_uuid=%s',(project_id,protocol))
        before=token();rows=sql('SELECT * FROM recording_workspace.curation');other._conn.begin()
        external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['rolled back']),))
        during=token();other._conn.rollback()
        check('rollback_preserves_visible_counter_and_rows',before==during==token() and rows==sql('SELECT * FROM recording_workspace.curation'))
        before=token();external('DELETE FROM recording_workspace.curation');check('delete_last_row',head(before)!=head(token()))
        external('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',(project_id,protocol,epoch,json.dumps(['restored'])))
        # Shared/profile updates and old-key tombstones share project commit order.
        before=token();external('INSERT INTO recording_workspace.annotation_profile VALUES (%s,%s,%s)',(project_id,profile,'same name'))
        after=token();check('profile_insert',before.shared_generation<after.shared_generation)
        external('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,%s,1)',(project_id,'epoch',epoch,profile,json.dumps(['QC','qc','é','e\u0301','shared']),'original author'))
        shared=authority.token();external('UPDATE recording_workspace.shared_annotation SET tags=%s',(json.dumps(['QC','changed']),))
        feed=authority.shared_changes(shared)
        check('shared_same_revision_delta',feed is not None and len(feed[0])==1 and not feed[0][0]['deleted'])
        shared=authority.token();external('UPDATE recording_workspace.shared_annotation SET target_uuid=%s,profile_uuid=%s',(epoch_two,profile_two))
        feed=authority.shared_changes(shared);keyed={(row['target_uuid'],row['profile_uuid']):row['deleted'] for row in feed[0]}
        check('target_profile_key_move_tombstone',keyed=={(epoch,profile):1,(epoch_two,profile_two):0})
        shared=authority.token();external('DELETE FROM recording_workspace.shared_annotation');feed=authority.shared_changes(shared)
        check('shared_delete_tombstone',feed is not None and len(feed[0])==1 and feed[0][0]['deleted']==1)
        # A before/after feed fence must reject a write occurring after fetch.
        shared=authority.token();original_rows=authority._rows;injected=[False]
        def raced_rows(statement,params=()):
            rows=original_rows(statement,params)
            if 'SELECT target_kind,target_uuid' in statement and not injected[0]:
                injected[0]=True;external('UPDATE recording_workspace.annotation_profile SET display_name=%s',('renamed',))
            return rows
        authority._rows=raced_rows
        try:check('concurrent_feed_write_rejected',authority.shared_changes(shared) is None and injected[0])
        finally:authority._rows=original_rows
        name=generation.PREFIX+'curation_au';expected=generation.MANIFEST[name]
        before=token();rows=sql('SELECT tags FROM recording_workspace.curation')
        external(f'DROP TRIGGER recording_workspace.{name}')
        external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['hidden write']),))
        external(f'CREATE TRIGGER recording_workspace.{name} AFTER UPDATE ON recording_workspace.curation FOR EACH ROW {expected["body"]}')
        after=token();check('drop_recreate_trigger_hidden_write_invalidates',head(before)==head(after) and before.authority!=after.authority and rows!=sql('SELECT tags FROM recording_workspace.curation'))
        before=token();external('FLUSH STATUS');check('flush_status_preserves_token',before==token())
        external('DROP TRIGGER recording_workspace.'+name);check('missing_trigger_fails_closed',authority.token(protocol) is None)
        external(f'CREATE TRIGGER recording_workspace.{name} AFTER UPDATE ON recording_workspace.curation FOR EACH ROW {expected["body"]}')
        before=token();external('TRUNCATE TABLE recording_workspace.curation');after=token();check('source_truncate_invalidates',before.authority!=after.authority and head(before)==head(after))
        before=token();external('ALTER TABLE recording_workspace.curation ADD COLUMN extra_probe INT NULL');after=token()
        check('source_alter_invalidates',before.authority!=after.authority and head(before)==head(after))
        external('ALTER TABLE recording_workspace.curation DROP COLUMN extra_probe')
        before=token();external('RENAME TABLE recording_workspace.curation TO recording_workspace.curation_moved')
        check('source_rename_away_fails_closed',authority.token(protocol) is None)
        external('RENAME TABLE recording_workspace.curation_moved TO recording_workspace.curation');after=token()
        check('source_rename_roundtrip_invalidates',before.authority!=after.authority and head(before)==head(after))
        before=token();external('DROP TABLE recording_workspace.curation')
        check('source_drop_fails_closed',authority.token(protocol) is None)
        external('CREATE TABLE recording_workspace.curation ('+definitions['curation']+') ENGINE=InnoDB')
        check('source_recreate_without_triggers_fails_closed',authority.token(protocol) is None)
        authority.bootstrap();after=token();check('source_recreate_and_rebootstrap_invalidates',before.authority!=after.authority and head(before)==head(after))
        external('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,%s,1)',(project_id,protocol,epoch,json.dumps(['before reset'])))
        before=token();external('DELETE FROM recording_workspace.app_state_generation WHERE project_uuid=%s AND scope_kind=%s AND scope_uuid=%s',(project_id,'protocol_curation',protocol))
        after=token();check('missing_counter_fresh_epoch',before.protocol_epoch!=after.protocol_epoch)
        before=token();external('TRUNCATE TABLE recording_workspace.app_state_generation');after=token();check('counter_truncate_invalidates',before.authority!=after.authority and before.protocol_epoch!=after.protocol_epoch)
        before=token();external('TRUNCATE TABLE recording_workspace.app_annotation_changes');after=token();check('feed_truncate_invalidates',before.authority!=after.authority)
        # Attest real executor visibility, not just eventual counter changes.
        holder=Connection(project);ddl=Connection(project);connections.extend([holder,ddl])
        def blocked(name,run):
            before=token();holder._conn.begin();holder.query('SELECT * FROM recording_workspace.curation').fetchall()
            outcome={}
            def work():
                try:run()
                except Exception as error:outcome['error']=str(error)
            worker=threading.Thread(target=work,daemon=True);worker.start()
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    pending=sql("SELECT COUNT(*) FROM performance_schema.metadata_locks WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s AND LOCK_STATUS='PENDING'",('recording_workspace','curation'))[0][0]
                    if pending:break
                    time.sleep(.005)
                check(name+'_blocked_fails_closed',bool(pending) and authority.token(protocol) is None,reason=authority.reason)
            finally:holder._conn.rollback();worker.join(timeout=5)
            check(name+'_clears_to_fresh_authority',not worker.is_alive() and not outcome and before.authority!=token().authority,outcome=outcome)
        blocked('ordinary_alter',lambda:ddl.query('ALTER TABLE recording_workspace.curation ADD COLUMN ordinary_guard INT NULL'))
        ddl.query("PREPARE authority_pending FROM 'ALTER TABLE recording_workspace.curation ADD COLUMN prepared_guard INT NULL'")
        blocked('sql_prepared_alter',lambda:ddl.query('EXECUTE authority_pending'));ddl.query('DEALLOCATE PREPARE authority_pending')
        from pymysql.constants import COMMAND
        ddl._conn._execute_command(COMMAND.COM_STMT_PREPARE,'ALTER TABLE recording_workspace.curation ADD COLUMN binary_guard INT NULL')
        packet=ddl._conn._read_packet();packet.check_error();packet.read_uint8();statement_id=packet.read_uint32()
        if packet.read_uint16() or packet.read_uint16():raise AssertionError('Unexpected DDL preparation parameters')
        def binary_execute():
            ddl._conn._execute_command(COMMAND.COM_STMT_EXECUTE,struct.pack('<IBI',statement_id,0,1));ddl._conn._read_query_result()
        blocked('binary_prepared_alter',binary_execute)
        ddl.query('CREATE PROCEDURE recording_workspace.guard_alter() ALTER TABLE recording_workspace.curation ADD COLUMN procedure_guard INT NULL')
        blocked('procedure_alter',lambda:ddl.query('CALL recording_workspace.guard_alter()'))
        # The short mutation transaction must hold real metadata/counter locks.
        for mode in ('metadata','counter'):
            before=token();connection._conn.begin();connection.in_transaction=True
            outcome={};worker=None
            try:
                authority.assert_current_locked(before)
                def work():
                    try:
                        if mode=='metadata':ddl.query('ALTER TABLE recording_workspace.curation ADD COLUMN locked_guard INT NULL')
                        else:ddl.query('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['external waited for counter']),))
                    except Exception as error:outcome['error']=str(error)
                worker=threading.Thread(target=work,daemon=True);worker.start();deadline=time.monotonic()+5;pending=0
                while time.monotonic()<deadline:
                    if mode=='metadata':pending=sql("SELECT COUNT(*) FROM performance_schema.metadata_locks WHERE OBJECT_SCHEMA=%s AND OBJECT_NAME=%s AND LOCK_STATUS='PENDING'",('recording_workspace','curation'))[0][0]
                    else:pending=sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits')[0][0]
                    if pending:break
                    time.sleep(.005)
                check('mutation_'+mode+'_lock_blocks_external_change',bool(pending) and worker.is_alive())
                connection._conn.commit()
            finally:
                connection._conn.rollback();connection.in_transaction=False
                if worker is not None:worker.join(timeout=5)
            check('mutation_'+mode+'_lock_releases_after_commit',worker is not None and not worker.is_alive() and not outcome and token()!=before,outcome=outcome)
        before=token();external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['newer than expected']),))
        connection._conn.begin();connection.in_transaction=True;conflict=False
        try:
            from workspace_curation import RevisionConflict
            try:authority.assert_current_locked(before)
            except RevisionConflict:conflict=True
        finally:connection._conn.rollback();connection.in_transaction=False
        check('mutation_stale_generation_rejected',conflict)
        for consumer in ('global_instrumentation','thread_instrumentation','events_statements_current'):
            before=token();external("UPDATE performance_schema.setup_consumers SET ENABLED='NO' WHERE NAME=%s",(consumer,))
            try:check('disabled_consumer_'+consumer,authority.token(protocol) is None,reason=authority.reason)
            finally:external("UPDATE performance_schema.setup_consumers SET ENABLED='YES' WHERE NAME=%s",(consumer,))
            check('reenabled_consumer_fresh_epoch_'+consumer,before.authority!=token().authority)
        for instrument in ('statement/sql/alter_table','statement/sql/execute_sql','statement/com/Execute','statement/sql/call_procedure'):
            before=token();external("UPDATE performance_schema.setup_instruments SET ENABLED='NO' WHERE NAME=%s",(instrument,))
            try:check('disabled_instrument_'+instrument,authority.token(protocol) is None,reason=authority.reason)
            finally:external("UPDATE performance_schema.setup_instruments SET ENABLED='YES' WHERE NAME=%s",(instrument,))
            check('reenabled_instrument_fresh_epoch_'+instrument,before.authority!=token().authority)
        other_id=external('SELECT CONNECTION_ID()')[0][0];before=token()
        sql("UPDATE performance_schema.threads SET INSTRUMENTED='NO' WHERE PROCESSLIST_ID=%s",(other_id,))
        try:check('uninstrumented_foreground_fails_closed',authority.token(protocol) is None,reason=authority.reason)
        finally:sql("UPDATE performance_schema.threads SET INSTRUMENTED='YES' WHERE PROCESSLIST_ID=%s",(other_id,))
        check('reinstrumented_foreground_fresh_epoch',before.authority!=token().authority)
        before=token();hidden=None
        actors=sql('SELECT HOST,USER,ROLE,ENABLED,HISTORY FROM performance_schema.setup_actors')
        try:
            external("UPDATE performance_schema.setup_actors SET ENABLED='NO' WHERE HOST=%s AND USER=%s AND ROLE=%s",('%','%','%'))
            hidden=Connection(project)
            check('setup_actors_excluded_new_connection_fails_closed',authority.token(protocol) is None,reason=authority.reason)
        finally:
            if hidden is not None:hidden.close()
            for host,user,role,enabled,history in actors:
                external('UPDATE performance_schema.setup_actors SET ENABLED=%s,HISTORY=%s WHERE HOST=%s AND USER=%s AND ROLE=%s',(enabled,history,host,user,role))
        check('setup_actors_repaired_fresh_authority',before.authority!=token().authority)
        # A future event is deliberately configured but never runs; its mere
        # presence must conservatively disable native cache authority.
        before=token();external('CREATE EVENT recording_workspace.authority_event ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 DAY DO SET @authority_probe=1')
        try:check('configured_event_fails_closed',authority.token(protocol) is None,reason=authority.reason)
        finally:external('DROP EVENT recording_workspace.authority_event')
        check('removed_event_fresh_authority',before.authority!=token().authority)
        external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['durable committed']),));committed=token();committed_rows=sql('SELECT * FROM recording_workspace.curation')
        other._conn.begin();external('UPDATE recording_workspace.curation SET tags=%s',(json.dumps(['must disappear after SIGKILL']),))
        owned=_owned_process(runtime)
        if owned is None:raise AssertionError('Owned disposable server missing')
        owned.kill();owned.wait(timeout=10)
        for client in connections:
            try:client.close()
            except Exception:pass
        runtime=ensure_native_database(project)
        for client in connections:client.reconnect()
        after=token();check('sigkill_rollback_and_committed_durability',sql('SELECT * FROM recording_workspace.curation')==committed_rows and head(after)==head(committed) and after.authority!=committed.authority)
        before=token();check('clean_shutdown',stop_native_database(project))
        for client in connections:
            try:client.close()
            except Exception:pass
        runtime=ensure_native_database(project)
        for client in connections:client.reconnect()
        after=token();check('clean_restart_invalidates_authority_preserves_data',after.authority!=before.authority and head(after)==head(before) and sql('SELECT * FROM recording_workspace.curation')==committed_rows)
        timings=[]
        for _ in range(20):
            start=time.perf_counter();token();timings.append(time.perf_counter()-start)
        report['warm_token_seconds']={'samples':len(timings),'p50':sorted(timings)[9],'p95':sorted(timings)[18],'maximum':max(timings)}
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()};print(traceback.format_exc(),flush=True)
    finally:
        for client in connections:
            try:client.close()
            except Exception:pass
        clean=False
        if project is not None:
            try:clean=stop_native_database(project)
            except Exception as error:report['shutdown_error']=str(error)
        report['clean_native_shutdown']=clean
        if clean:shutil.rmtree(root);report['temporary_project_removed']=True
        else:report['temporary_project_preserved']=str(root)
        report['source_sha256_after']=hashlib.sha256(Path(generation.__file__).read_bytes()).hexdigest()
        report['source_unchanged']=report['source_sha256_after']==before_hash
        report['passed']=not report.get('error') and clean and report['source_unchanged'] and all(row['passed'] for row in report['cases'])
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n')
    return int(not report['passed'])


if __name__=='__main__':raise SystemExit(main())
