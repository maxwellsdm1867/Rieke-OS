"""Disposable same-server old/new trigger validation timing; no UI timing claim."""
import hashlib,json,statistics,tempfile,time,uuid
from pathlib import Path
import pymysql
from test_workspace_state_generation import NativeConnection
import workspace_native_tag_lookup as lookup_module
from workspace_projects import create_project
import workspace_native_mysql as native


def baseline_manifest():
    def valid(alias):
        tag=lookup_module._tag(alias)
        whitespace=[chr(n).encode('utf-8').hex() for n in range(0x3001) if chr(n).isspace()]
        ends=','.join('0x'+value for value in whitespace)
        controls=' OR '.join(f'LOCATE(CHAR({n}),{tag})>0' for n in range(32))
        invalid=(f"JSON_TYPE(JSON_EXTRACT({alias}.tags,CONCAT('$[',j.ordinal-1,']')))!='STRING' "
            f'OR CHAR_LENGTH({tag}) NOT BETWEEN 1 AND 255 OR BINARY LEFT({tag},1) IN ({ends}) '
            f'OR BINARY RIGHT({tag},1) IN ({ends}) OR {controls}')
        return (f"IF JSON_TYPE({alias}.tags)!='ARRAY' OR JSON_LENGTH({alias}.tags)>100 OR EXISTS ("
            f"SELECT 1 FROM JSON_TABLE({alias}.tags,'$[*]' COLUMNS(ordinal FOR ORDINALITY)) j WHERE {invalid}) "
            "THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid canonical shared annotation tags'; END IF;")
    def insert(alias):
        return (valid(alias)+f' INSERT INTO `{lookup_module.SCHEMA}`.`{lookup_module.TABLE}` ({",".join(lookup_module.COLUMNS)}) '
            f'SELECT {alias}.project_uuid,{alias}.target_kind,{alias}.target_uuid,{alias}.profile_uuid,'
            f"CAST({lookup_module._tag(alias)} AS BINARY) FROM JSON_TABLE({alias}.tags,'$[*]' "
            "COLUMNS(ordinal FOR ORDINALITY)) j;")
    delete,dirty=lookup_module._delete,lookup_module._dirty
    return {lookup_module.PREFIX+suffix:{'table':'shared_annotation','event':event,'timing':'AFTER','body':'BEGIN '+body+' END'}
        for suffix,event,body in [('ai','INSERT',insert('NEW')+' '+dirty('NEW')),
            ('au','UPDATE',delete('OLD')+' '+insert('NEW')+' '+dirty('OLD')+' '+dirty('NEW')),
            ('ad','DELETE',delete('OLD')+' '+dirty('OLD'))]}


def optimized_manifest():
    def valid(alias):
        tag='j.tag'
        whitespace=[chr(n).encode('utf-8').hex() for n in range(0x3001) if chr(n).isspace()]
        ends=','.join('0x'+value for value in whitespace)
        invalid=(f"JSON_TYPE(JSON_EXTRACT({alias}.tags,CONCAT('$[',j.ordinal-1,']')))!='STRING' "
            f'OR CHAR_LENGTH({tag}) NOT BETWEEN 1 AND 255 OR BINARY LEFT({tag},1) IN ({ends}) '
            f'OR BINARY RIGHT({tag},1) IN ({ends}) '
            f"OR REGEXP_LIKE({tag},CONVERT(0x5b002d1f5d USING utf8mb4),'c')")
        return (f"IF JSON_TYPE({alias}.tags)!='ARRAY' OR JSON_LENGTH({alias}.tags)>100 OR EXISTS ("
            f"SELECT 1 FROM JSON_TABLE({alias}.tags,'$[*]' COLUMNS(ordinal FOR ORDINALITY,"
            f"tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) j WHERE {invalid}) "
            "THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid canonical shared annotation tags'; END IF;")
    def insert(alias):
        return (valid(alias)+f' INSERT INTO `{lookup_module.SCHEMA}`.`{lookup_module.TABLE}` ({",".join(lookup_module.COLUMNS)}) '
            f'SELECT {alias}.project_uuid,{alias}.target_kind,{alias}.target_uuid,{alias}.profile_uuid,'
            f"CAST(j.tag AS BINARY) FROM JSON_TABLE({alias}.tags,'$[*]' "
            "COLUMNS(tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) j;")
    delete,dirty=lookup_module._delete,lookup_module._dirty
    return {lookup_module.PREFIX+suffix:{'table':'shared_annotation','event':event,'timing':'AFTER','body':'BEGIN '+body+' END'}
        for suffix,event,body in [('ai','INSERT',insert('NEW')+' '+dirty('NEW')),
            ('au','UPDATE',delete('OLD')+' '+insert('NEW')+' '+dirty('OLD')+' '+dirty('NEW')),
            ('ad','DELETE',delete('OLD')+' '+dirty('OLD'))]}


def run(output):
    report={'kind':'same-server-native-sql-trigger-microbenchmark','samples':10,'targets_per_transaction':10,
        'canonical_tags_per_row':6,'includes':'10 canonical UPDATE statements and native transaction commit; no HTTP/event/provenance reads'}
    with tempfile.TemporaryDirectory(prefix='rieke-tag-trigger-timing-') as directory:
        root=Path(create_project(Path(directory)/'projects','Private tag trigger timing')['path']);raw=None
        try:
            native.ensure_native_database(root);raw=pymysql.connect(**native.connection_parameters(root),autocommit=True);conn=NativeConnection(raw)
            conn.query('CREATE DATABASE recording_workspace')
            conn.query('CREATE TABLE recording_workspace.shared_annotation (project_uuid varchar(36),target_kind varchar(8),target_uuid varchar(36),profile_uuid varchar(36),tags JSON NOT NULL,revision INT NOT NULL,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid)) ENGINE=InnoDB')
            conn.query('CREATE TABLE recording_workspace.app_state_generation (project_uuid varchar(36),scope_kind varchar(32),scope_uuid varchar(36),generation BIGINT,PRIMARY KEY(project_uuid,scope_kind,scope_uuid)) ENGINE=InnoDB')
            project,profile=str(uuid.uuid4()),str(uuid.uuid4());all_ids=[str(uuid.uuid4()) for _ in range(1500)];ids=all_ids[:10]
            conn.query('INSERT INTO recording_workspace.app_state_generation VALUES (%s,%s,%s,0)',(project,'shared_annotations',project))
            for key in all_ids:conn.query('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,1)',(project,'epoch',key,profile,json.dumps(['all','bucket:7','ON','é','profile:0','review:0'])))
            proof={'project_uuid':project,'tables':{'shared_annotation':{'count':1500,'xor':'0'*64}}}
            lookup=lookup_module.bootstrap(conn,project,proof);assert lookup.ready,lookup.reason
            import runpy
            validation=runpy.run_path(str(Path(__file__).with_name('benchmark_tag_trigger_validation.py')))
            before=validation['optimized_manifest']()
            fixed={name:dict(spec) for name,spec in before.items()}
            for spec in fixed.values():
                for alias in ('OLD','NEW'):
                    for field in ('project_uuid','target_kind','target_uuid','profile_uuid'):
                        spec['body']=spec['body'].replace(field+'='+alias+'.'+field,field+'=CONVERT('+alias+'.'+field+' USING ascii) COLLATE ascii_bin')
            manifests={'before':before,'fixed_comparison':fixed}
            report['mysql_version']=conn.query('SELECT VERSION()').fetchone()[0]
            report['column_collations']=conn.query("SELECT TABLE_NAME,COLUMN_NAME,COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='recording_workspace' AND TABLE_NAME IN ('shared_annotation','app_shared_tag_lookup')",as_dict=True).fetchall()
            report['delete_plans']={}
            for variant in ('before','fixed_comparison'):
                delete=validation['historical_delete']('OLD')
                if variant=='fixed_comparison':
                    for field in ('project_uuid','target_kind','target_uuid','profile_uuid'):
                        delete=delete.replace(field+'=OLD.'+field,field+'=CONVERT(OLD.'+field+' USING ascii) COLLATE ascii_bin')
                for field in ('project_uuid','target_kind','target_uuid','profile_uuid'):delete=delete.replace('OLD.'+field,'p_'+field)
                declarations=','.join('IN p_'+field+' VARCHAR(36) CHARACTER SET utf8mb4' for field in ('project_uuid','target_kind','target_uuid','profile_uuid'))
                conn.query('CREATE PROCEDURE recording_workspace.plan_'+variant+'('+declarations+') BEGIN EXPLAIN FORMAT=JSON '+delete+' END')
                report['delete_plans'][variant]=json.loads(conn.query('CALL recording_workspace.plan_'+variant+'(%s,%s,%s,%s)',(project,'epoch',ids[0],profile)).fetchone()[0])

            for label,manifest in manifests.items():
                for name,spec in manifest.items():
                    conn.query('DROP TRIGGER recording_workspace.'+name)
                    conn.query('CREATE TRIGGER recording_workspace.'+name+' AFTER '+spec['event']+' ON recording_workspace.shared_annotation FOR EACH ROW '+spec['body'])
                report[label]={'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()}
                samples=[]
                before_reads=conn.query("SHOW SESSION STATUS WHERE Variable_name='Handler_read_next'").fetchone()[1]
                for sample in range(15):
                    values=json.dumps(['all','bucket:7','ON','é','profile:0','review:'+str(sample%2)])
                    started=time.perf_counter()
                    with conn.transaction:
                        for key in ids:conn.query('UPDATE recording_workspace.shared_annotation SET tags=%s,revision=revision+1 WHERE project_uuid=%s AND target_kind=%s AND target_uuid=%s AND profile_uuid=%s',(values,project,'epoch',key,profile))
                    elapsed=time.perf_counter()-started
                    if sample>=5:samples.append(elapsed)
                report[label]['handler_read_next']=int(conn.query("SHOW SESSION STATUS WHERE Variable_name='Handler_read_next'").fetchone()[1])-int(before_reads)
                report[label].update(seconds=samples,median_seconds=statistics.median(samples),p95_seconds=sorted(samples)[9])
                assert lookup.targets('review:1')==set()
            Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({label:{k:v for k,v in value.items() if k!='seconds'} for label,value in report.items() if isinstance(value,dict)}),flush=True)
        finally:
            if raw is not None:raw.close()
            native.stop_native_database(root)


if __name__=='__main__':
    import sys
    run(sys.argv[1])
