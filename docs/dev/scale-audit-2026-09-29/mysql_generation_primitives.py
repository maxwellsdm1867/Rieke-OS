"""Probe actual MySQL generation/DDL semantics in an owned disposable server.

This validates native primitives, not the application's forthcoming authority
module. Never accepts an existing project or database address.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import pymysql
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database,stop_native_database,connection_parameters

DB='rieke_generation_probe'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--recreate-attempts',type=int,default=100)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose an unused output file')
    report={'scope':'Disposable native SQL primitive probes; not application authority/cache certification','cases':[]}
    root=Path(tempfile.mkdtemp(prefix='rieke-generation-primitives-'));project=None;connection=None
    def emit(name,**values):
        record={'name':name,**values};report['cases'].append(record);print(json.dumps(record,default=str),flush=True)
    try:
        project=Path(create_project(root/'projects','Generation primitives')['path'])
        ensure_native_database(project)
        connection=pymysql.connect(**connection_parameters(project),autocommit=True)
        def sql(statement,args=None):
            with connection.cursor() as cursor:
                cursor.execute(statement,args);return cursor.fetchall()
        report['mysql_version']=sql('SELECT VERSION()')[0][0]
        sql(f'CREATE DATABASE `{DB}`')
        source_sql=f'''CREATE TABLE `{DB}`.`source` (
            project_uuid VARCHAR(36) NOT NULL, protocol_uuid VARCHAR(36) NOT NULL,
            epoch_uuid VARCHAR(36) NOT NULL, tags JSON NOT NULL, revision INT UNSIGNED NOT NULL,
            PRIMARY KEY(project_uuid,protocol_uuid,epoch_uuid)) ENGINE=InnoDB'''
        clock_sql=f'''CREATE TABLE `{DB}`.`clock` (
            project_uuid VARCHAR(36) NOT NULL, protocol_uuid VARCHAR(36) NOT NULL,
            generation BIGINT UNSIGNED NOT NULL, PRIMARY KEY(project_uuid,protocol_uuid)) ENGINE=InnoDB'''
        sql(source_sql);sql(clock_sql)
        def bump(prefix):
            return f'INSERT INTO `{DB}`.`clock` VALUES ({prefix}.project_uuid,{prefix}.protocol_uuid,1) ON DUPLICATE KEY UPDATE generation=generation+1;'
        definitions={
            'insert':f'CREATE TRIGGER `{DB}`.`bump_insert` AFTER INSERT ON `{DB}`.`source` FOR EACH ROW BEGIN {bump("NEW")} END',
            'update':f'CREATE TRIGGER `{DB}`.`bump_update` AFTER UPDATE ON `{DB}`.`source` FOR EACH ROW BEGIN {bump("OLD")} IF OLD.project_uuid<>NEW.project_uuid OR OLD.protocol_uuid<>NEW.protocol_uuid THEN {bump("NEW")} END IF; END',
            'delete':f'CREATE TRIGGER `{DB}`.`bump_delete` AFTER DELETE ON `{DB}`.`source` FOR EACH ROW BEGIN {bump("OLD")} END',
        }
        for definition in definitions.values():sql(definition)
        def ddl_status(conn=None):
            with (conn or connection).cursor() as cursor:
                cursor.execute("SHOW GLOBAL STATUS WHERE Variable_name IN ('Com_create_trigger','Com_drop_trigger','Com_create_table','Com_drop_table','Com_alter_table','Com_rename_table','Com_truncate','Com_create_db','Com_drop_db')")
                return {name:int(value) for name,value in cursor.fetchall()}
        def clock():return sql(f'SELECT project_uuid,protocol_uuid,generation FROM `{DB}`.`clock` ORDER BY project_uuid,protocol_uuid')
        def table_id(table):return sql('SELECT TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME=%s',(DB+'/'+table,))[0][0]
        def triggers():return sql('SELECT TRIGGER_NAME,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT,CREATED,DEFINER FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s ORDER BY TRIGGER_NAME',(DB,))
        def source():return sql(f'SELECT project_uuid,protocol_uuid,epoch_uuid,tags,revision FROM `{DB}`.`source` ORDER BY project_uuid,protocol_uuid,epoch_uuid')
        def insert():sql(f'INSERT INTO `{DB}`.`source` VALUES (%s,%s,%s,%s,1)',('project-A','protocol-A','epoch-A',json.dumps(['QC','tag-A'])))
        insert();emit('insert',clock=clock(),source=source())
        previous=clock();sql(f'UPDATE `{DB}`.`source` SET tags=%s',(json.dumps(['QC','tag-B']),))
        emit('same_revision_update',clock_before=previous,clock_after=clock(),source=source())
        previous=clock();sql(f'REPLACE INTO `{DB}`.`source` VALUES (%s,%s,%s,%s,1)',('project-A','protocol-A','epoch-A',json.dumps(['QC','tag-C'])))
        emit('replace',clock_before=previous,clock_after=clock())
        previous=clock();sql(f'UPDATE `{DB}`.`source` SET project_uuid=%s,protocol_uuid=%s',('project-B','protocol-B'))
        emit('project_and_protocol_move',clock_before=previous,clock_after=clock())
        previous=clock();before=source();connection.begin();sql(f'UPDATE `{DB}`.`source` SET tags=%s',(json.dumps(['rollback']),));inside=clock();connection.rollback()
        emit('rollback',clock_before=previous,clock_inside=inside,clock_after=clock(),source_preserved=source()==before)
        previous=clock();sql(f'DELETE FROM `{DB}`.`source`');emit('delete_last_row',clock_before=previous,clock_after=clock(),source=source())
        insert();previous=clock();old_table_id=table_id('source');old_triggers=triggers()
        sql(f'TRUNCATE TABLE `{DB}`.`source`')
        emit('truncate_source',clock_unchanged=clock()==previous,table_id_before=old_table_id,table_id_after=table_id('source'),triggers_unchanged=triggers()==old_triggers)
        insert();previous=clock();old_table_id=table_id('source')
        sql(f'DROP TABLE `{DB}`.`source`');sql(source_sql)
        for definition in definitions.values():sql(definition)
        emit('drop_recreate_source',clock_unchanged=clock()==previous,table_id_before=old_table_id,table_id_after=table_id('source'))
        insert()
        # The exposed CREATED timestamp may be too coarse to establish that
        # coverage never disappeared between reads, even with identical bodies.
        collision=None;durations=[]
        for attempt in range(args.recreate_attempts):
            sql(f'DROP TRIGGER `{DB}`.`bump_update`');sql(definitions['update'])
            before=triggers();previous=clock();rows_before=source();ddl_before=ddl_status();tick=time.perf_counter()
            sql(f'DROP TRIGGER `{DB}`.`bump_update`')
            sql(f'UPDATE `{DB}`.`source` SET tags=%s',(json.dumps(['QC',f'untracked-{attempt}']),))
            sql(definitions['update']);elapsed=time.perf_counter()-tick;durations.append(elapsed)
            after=triggers()
            if before==after:
                collision={'attempt':attempt+1,'seconds':elapsed,'trigger_signature_unchanged':True,
                    'source_table_id':table_id('source'),'clock_unchanged':clock()==previous,
                    'source_changed':source()!=rows_before,'trigger_metadata':after,
                    'ddl_before':ddl_before,'ddl_after':ddl_status()}
                break
        emit('drop_recreate_trigger_coverage_gap',attempts=len(durations),collision=collision,
             minimum_seconds=min(durations) if durations else None,
             conclusion='A matching metadata signature hid a missed write' if collision else 'No metadata-signature collision observed; absence is not a proof of continuous trigger coverage')
        before=ddl_status();sql('FLUSH STATUS');emit('flush_status_same_connection',before=before,after=ddl_status())
        other=pymysql.connect(**connection_parameters(project),autocommit=True)
        try:
            before=ddl_status()
            with other.cursor() as cursor:cursor.execute('FLUSH STATUS')
            emit('flush_status_other_connection',before=before,after=ddl_status())
            before=ddl_status()
            with other.cursor() as cursor:
                cursor.execute(f'CREATE TABLE `{DB}`.`scratch` (id INT PRIMARY KEY) ENGINE=InnoDB')
                cursor.execute(f'DROP TABLE `{DB}`.`scratch`')
            live=ddl_status()
        finally:other.close()
        emit('other_connection_disconnect',before=before,while_connected=live,after_disconnect=ddl_status())
        for kind,statement in [('drop_trigger',f'DROP TRIGGER `{DB}`.`bump_update`'),('create_trigger',definitions['update']),('alter_table',f'ALTER TABLE `{DB}`.`source` ADD COLUMN probe_column INT NULL')]:
            before=ddl_status();error=None;prepared=False
            try:
                sql('PREPARE ddl_probe FROM %s',(statement,));prepared=True;sql('EXECUTE ddl_probe')
            except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
            finally:
                if prepared:sql('DEALLOCATE PREPARE ddl_probe')
            emit('prepared_'+kind,before=before,after=ddl_status(),error=error)
        if not any(row[0]=='bump_update' for row in triggers()):sql(definitions['update'])
        old=table_id('clock');sql(f'TRUNCATE TABLE `{DB}`.`clock`');emit('truncate_generation_table',table_id_before=old,table_id_after=table_id('clock'),clock=clock(),source_count=len(source()))
        sql(f'UPDATE `{DB}`.`source` SET tags=%s',(json.dumps(['QC','after-clock-reset']),))
        emit('write_after_missing_generation_row',clock=clock())
        sql(f'DELETE FROM `{DB}`.`clock`');emit('delete_generation_row',table_id=table_id('clock'),clock=clock(),source_count=len(source()))
        report['trigger_created_column']=sql('SELECT DATA_TYPE,DATETIME_PRECISION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s',('information_schema','TRIGGERS','CREATED'))
    except Exception as error:
        import traceback
        report['error']={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
        print(traceback.format_exc(),flush=True)
    finally:
        if connection is not None:connection.close()
        clean=False
        if project is not None:
            try:clean=stop_native_database(project)
            except Exception as error:report['shutdown_error']=str(error)
        report['clean_native_shutdown']=clean
        if clean:shutil.rmtree(root);report['temporary_project_removed']=True
        else:report['temporary_project_preserved']=str(root)
        report['release_ready']=False
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n')
    return int(bool(report.get('error')) or not clean)


if __name__=='__main__':raise SystemExit(main())
