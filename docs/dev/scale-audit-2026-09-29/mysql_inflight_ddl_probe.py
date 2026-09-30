"""Test counter and metadata visibility while real trigger DDL waits on MDL."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import tempfile
import threading
import time
import traceback

import pymysql
from workspace_projects import create_project
from workspace_native_mysql import ensure_native_database,stop_native_database,connection_parameters


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose unused receipt')
    root=Path(tempfile.mkdtemp(prefix='rieke-inflight-ddl-'));project=None;clients=[];threads=[];report={'cases':[],'release_ready':False}
    try:
        project=Path(create_project(root/'projects','Inflight DDL probe')['path']);ensure_native_database(project)
        def client():
            conn=pymysql.connect(**connection_parameters(project),autocommit=True);clients.append(conn);return conn
        primary=client();holder=client();dropper=client();writer=client();creator=client();inspector=client()
        def sql(conn,statement,args=None):
            with conn.cursor() as cur:cur.execute(statement,args);return cur.fetchall()
        report['mysql_version']=sql(primary,'SELECT VERSION()')[0][0]
        sql(primary,'CREATE DATABASE ddl_probe');sql(primary,'CREATE TABLE ddl_probe.source(id INT PRIMARY KEY,value INT) ENGINE=InnoDB');sql(primary,'CREATE TABLE ddl_probe.clock(value INT) ENGINE=InnoDB');sql(primary,'INSERT INTO ddl_probe.clock VALUES (0)')
        sql(primary,'INSERT INTO ddl_probe.source VALUES (1,0)')
        definition='CREATE TRIGGER ddl_probe.tracked AFTER UPDATE ON ddl_probe.source FOR EACH ROW UPDATE ddl_probe.clock SET value=value+1'
        sql(primary,definition)
        def counters():return dict(sql(primary,"SHOW GLOBAL STATUS WHERE Variable_name IN ('Com_create_trigger','Com_drop_trigger')"))
        report['counters_before']=counters()
        holder.begin();sql(holder,'SELECT * FROM ddl_probe.source')
        events={}
        def background(name,conn,statement):
            def run():
                start=time.perf_counter();events[name]={'started':start}
                try:events[name]['rows']=statement(conn) if callable(statement) else sql(conn,statement)
                except Exception as error:events[name]['error']=str(error)
                finally:events[name]['finished']=time.perf_counter();events[name]['seconds']=events[name]['finished']-start
            thread=threading.Thread(target=run,daemon=True);threads.append(thread);thread.start()
        background('drop',dropper,'DROP TRIGGER ddl_probe.tracked');time.sleep(.05)
        background('write',writer,'UPDATE ddl_probe.source SET value=99');time.sleep(.05)
        background('create',creator,definition);time.sleep(.05)
        report['counters_while_all_blocked']=counters()
        report['pending_mdl']=sql(primary,"SELECT OBJECT_TYPE,OBJECT_SCHEMA,OBJECT_NAME,LOCK_TYPE,LOCK_STATUS FROM performance_schema.metadata_locks WHERE OBJECT_SCHEMA='ddl_probe'")
        background('inspect',inspector,"SELECT TRIGGER_NAME,ACTION_STATEMENT,CREATED FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='ddl_probe'")
        time.sleep(.15)
        report['inspection_finished_before_release']='finished' in events['inspect']
        report['events_before_release']={name:dict(values) for name,values in events.items()}
        report['active_statement_instrumentation']=sql(primary,"SELECT NAME,ENABLED FROM performance_schema.setup_consumers WHERE NAME='events_statements_current'")
        report['active_ddl_statements']=sql(primary,"SELECT EVENT_NAME,END_EVENT_ID,SQL_TEXT FROM performance_schema.events_statements_current WHERE EVENT_NAME IN ('statement/sql/drop_trigger','statement/sql/create_trigger') AND END_EVENT_ID IS NULL")
        holder.rollback()
        for thread in threads:thread.join(timeout=5)
        report['events']=events;report['counters_after']=counters();report['final_source']=sql(primary,'SELECT * FROM ddl_probe.source');report['final_clock']=sql(primary,'SELECT * FROM ddl_probe.clock')
        report['all_threads_finished']=all(not thread.is_alive() for thread in threads)
        # PREPARE exposes the executing underlying DDL instrument, rather than
        # hiding it behind only a generic EXECUTE event.
        holder.begin();sql(holder,'SELECT * FROM ddl_probe.source')
        sql(dropper,"PREPARE pending_alter FROM 'ALTER TABLE ddl_probe.source ADD COLUMN extra_column INT NULL'")
        background('prepared_alter',dropper,'EXECUTE pending_alter');time.sleep(.1)
        report['prepared_alter_active']=sql(primary,"SELECT EVENT_NAME,END_EVENT_ID,SQL_TEXT FROM performance_schema.events_statements_current WHERE END_EVENT_ID IS NULL")
        report['instrumented_foreground']=sql(primary,"SELECT INSTRUMENTED,COUNT(*) FROM performance_schema.threads WHERE TYPE='FOREGROUND' GROUP BY INSTRUMENTED")
        report['required_consumers']=sql(primary,"SELECT NAME,ENABLED FROM performance_schema.setup_consumers WHERE NAME IN ('global_instrumentation','thread_instrumentation','events_statements_current')")
        report['ddl_instruments']=sql(primary,"SELECT NAME,ENABLED FROM performance_schema.setup_instruments WHERE NAME IN ('statement/sql/create_trigger','statement/sql/drop_trigger','statement/sql/create_table','statement/sql/drop_table','statement/sql/alter_table','statement/sql/rename_table','statement/sql/truncate','statement/sql/create_db','statement/sql/drop_db')")
        report['executor_instruments']=sql(primary,"SELECT NAME,ENABLED FROM performance_schema.setup_instruments WHERE NAME LIKE '%Execute%' OR NAME LIKE '%call%' OR NAME LIKE '%event%' OR NAME LIKE '%tablespace%'")
        report['tablespace_counters']=sql(primary,"SHOW GLOBAL STATUS WHERE Variable_name LIKE 'Com%tablespace%'")
        report['scheduler_settings']=sql(primary,'SELECT @@event_scheduler,@@log_bin')
        report['performance_schema_losses']=sql(primary,"SHOW GLOBAL STATUS WHERE Variable_name LIKE 'Performance_schema%lost'")
        report['uninstrumented_threads']=sql(primary,"SELECT NAME,TYPE,PROCESSLIST_USER FROM performance_schema.threads WHERE INSTRUMENTED='NO'")
        report['actual_connection_count']=sql(primary,"SHOW GLOBAL STATUS WHERE Variable_name IN ('Connections','Threads_connected')")
        report['instrumented_connection_population']=sql(primary,"SELECT NAME,PROCESSLIST_ID,PROCESSLIST_USER,PROCESSLIST_COMMAND,INSTRUMENTED FROM performance_schema.threads WHERE TYPE='FOREGROUND' AND PROCESSLIST_ID IS NOT NULL")
        holder.rollback()
        for thread in threads:thread.join(timeout=5)
        report['all_threads_finished']=all(not thread.is_alive() for thread in threads)
        holder.begin();sql(holder,'SELECT * FROM ddl_probe.source')
        from pymysql.constants import COMMAND
        dropper._execute_command(COMMAND.COM_STMT_PREPARE,'ALTER TABLE ddl_probe.source ADD COLUMN binary_column INT NULL')
        packet=dropper._read_packet();packet.check_error();packet.read_uint8();statement_id=packet.read_uint32()
        columns=packet.read_uint16();parameters=packet.read_uint16()
        if columns or parameters:raise AssertionError('Unexpected parameterless DDL preparation metadata')
        def binary_execute(conn):
            conn._execute_command(COMMAND.COM_STMT_EXECUTE,struct.pack('<IBI',statement_id,0,1));conn._read_query_result();return []
        background('binary_alter',dropper,binary_execute);time.sleep(.1)
        report['binary_alter_active']=sql(primary,"SELECT EVENT_NAME,END_EVENT_ID,SQL_TEXT FROM performance_schema.events_statements_current WHERE END_EVENT_ID IS NULL")
        holder.rollback()
        for thread in threads:thread.join(timeout=5)
        sql(primary,'CREATE PROCEDURE ddl_probe.procedure_alter() ALTER TABLE ddl_probe.source ADD COLUMN procedure_column INT NULL')
        holder.begin();sql(holder,'SELECT * FROM ddl_probe.source');background('procedure_alter',dropper,'CALL ddl_probe.procedure_alter()');time.sleep(.1)
        report['procedure_alter_active']=sql(primary,"SELECT EVENT_NAME,END_EVENT_ID,SQL_TEXT FROM performance_schema.events_statements_current WHERE END_EVENT_ID IS NULL")
        holder.rollback()
        for thread in threads:thread.join(timeout=5)
        report['all_threads_finished']=all(not thread.is_alive() for thread in threads)
    except Exception as error:report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:
        for conn in clients:
            try:conn.close()
            except Exception:pass
        clean=False
        if project is not None:
            try:clean=stop_native_database(project)
            except Exception as error:report['shutdown_error']=str(error)
        report['clean_native_shutdown']=clean
        if clean:shutil.rmtree(root)
        else:report['preserved_temporary_project']=str(root)
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n');print(json.dumps(report,default=str),flush=True)
    return int(bool(report.get('error')) or not clean or not report.get('all_threads_finished'))


if __name__=='__main__':raise SystemExit(main())
