"""Read-only inspection of the mounted native catalog; never imports app bootstrap."""
import json, pathlib, signal, time
import pymysql

ROOT=pathlib.Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
OUT=pathlib.Path('/private/tmp/disco-real-data-evals-20261001/native')
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('60 second inspection cap')))
signal.alarm(60)
credentials=json.loads((ROOT/'database/native-credentials.json').read_text())
catalog=json.loads((ROOT/'catalog.json').read_text())
conn=pymysql.connect(host=catalog['connection']['host'],port=catalog['connection']['port'],user='root',password=credentials['password'],connect_timeout=3,read_timeout=5,write_timeout=3,autocommit=False,cursorclass=pymysql.cursors.DictCursor)
del credentials
results={'project_uuid':catalog['project_uuid'],'database_kind':'native-mysql','queries':{}}
def query(label,sql,args=None):
    started=time.monotonic()
    try:
        with conn.cursor() as cur:
            cur.execute(sql,args)
            results['queries'][label]={'rows':cur.fetchall(),'elapsed_seconds':round(time.monotonic()-started,4)}
    except pymysql.MySQLError as exc:
        results['queries'][label]={'error_code':exc.args[0],'elapsed_seconds':round(time.monotonic()-started,4)}
    return results['queries'][label].get('rows',[])
try:
    with conn.cursor() as cur:
        cur.execute('SET SESSION MAX_EXECUTION_TIME=3000')
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
    query('server','SELECT VERSION() AS version')
    query('tables',"SELECT table_schema,table_name,table_rows,data_length,index_length FROM information_schema.tables WHERE table_schema IN ('schema','recording_workspace') ORDER BY table_schema,table_name")
    query('columns',"SELECT table_schema,table_name,column_name,column_type,column_key FROM information_schema.columns WHERE table_schema IN ('schema','recording_workspace') ORDER BY table_schema,table_name,ordinal_position")
    counts={}
    for db,table in [('schema',x) for x in ['experiment','cell','epoch_group','epoch_block','epoch','protocol','response','stimulus','tags']]+[('recording_workspace',x) for x in ['source','annotation_profile','shared_annotation','curation','app_shared_tag_authors','app_shared_tag_dictionary','app_shared_tag_lookup','dataset_revision','explorer_revision','protocol_workspace']]:
        counts[f'{db}.{table}']=query(f'count:{db}.{table}',f'SELECT COUNT(*) AS row_count FROM `{db}`.`{table}`')
    query('source_manifest_fields','SELECT experiment_id, JSON_KEYS(manifest) AS manifest_keys FROM recording_workspace.source ORDER BY experiment_id LIMIT 20')
    query('source_coverage','SELECT s.source_sha256,s.experiment_uuid,s.experiment_id,(SELECT COUNT(*) FROM `schema`.epoch e WHERE e.experiment_id=s.experiment_id) AS epoch_count,(SELECT COUNT(*) FROM `schema`.cell c WHERE c.experiment_id=s.experiment_id) AS cell_count,(SELECT COUNT(*) FROM `schema`.epoch_block b WHERE b.experiment_id=s.experiment_id) AS block_count FROM recording_workspace.source s ORDER BY s.experiment_id LIMIT 20')
    query('protocol_epoch_distribution','SELECT p.name,COUNT(e.id) AS epoch_count,COUNT(DISTINCT b.id) AS block_count,COUNT(DISTINCT e.experiment_id) AS experiment_count FROM `schema`.protocol p LEFT JOIN `schema`.epoch_block b ON b.protocol_id=p.protocol_id LEFT JOIN `schema`.epoch e ON e.parent_id=b.id GROUP BY p.protocol_id,p.name ORDER BY epoch_count DESC LIMIT 30')
    query('cell_epoch_distribution','SELECT c.id AS cell_id,c.experiment_id,COUNT(e.id) AS epoch_count,COUNT(DISTINCT b.id) AS block_count FROM `schema`.cell c LEFT JOIN `schema`.epoch_group g ON g.parent_id=c.id LEFT JOIN `schema`.epoch_block b ON b.parent_id=g.id LEFT JOIN `schema`.epoch e ON e.parent_id=b.id GROUP BY c.id,c.experiment_id ORDER BY epoch_count DESC LIMIT 50')
    query('annotation_density','SELECT target_kind,COUNT(*) AS annotation_rows,COUNT(DISTINCT target_uuid) AS targets,COUNT(DISTINCT profile_uuid) AS profiles,COUNT(DISTINCT author_name) AS authors,SUM(JSON_LENGTH(tags)) AS tag_entries,MAX(JSON_LENGTH(tags)) AS max_tags FROM recording_workspace.shared_annotation GROUP BY target_kind LIMIT 10')
    query('curation_density','SELECT included,review_state,COUNT(*) AS epochs,SUM(JSON_LENGTH(tags)) AS tag_entries FROM recording_workspace.curation GROUP BY included,review_state LIMIT 10')
    query('legacy_tag_density','SELECT table_name,COUNT(*) AS tags,COUNT(DISTINCT table_id) AS targets,COUNT(DISTINCT user) AS authors,COUNT(DISTINCT tag) AS distinct_tag_values FROM `schema`.tags GROUP BY table_name LIMIT 20')
    query('epoch_metadata_size','SELECT COUNT(*) AS epoch_count,MIN(JSON_LENGTH(parameters)) AS parameter_fields_min,AVG(JSON_LENGTH(parameters)) AS parameter_fields_avg,MAX(JSON_LENGTH(parameters)) AS parameter_fields_max,AVG(OCTET_LENGTH(parameters)) AS parameter_bytes_avg,MAX(OCTET_LENGTH(parameters)) AS parameter_bytes_max,MIN(JSON_LENGTH(properties)) AS property_fields_min,AVG(JSON_LENGTH(properties)) AS property_fields_avg,MAX(JSON_LENGTH(properties)) AS property_fields_max FROM `schema`.epoch')
    for table,col in [('epoch','parameters'),('epoch','properties'),('epoch','attributes'),('epoch_block','parameters'),('cell','properties')]:
        query(f'field_presence:{table}.{col}',f"SELECT jt.field_name,COUNT(*) AS occurrences FROM `schema`.`{table}` t JOIN JSON_TABLE(JSON_KEYS(t.`{col}`), '$[*]' COLUMNS(field_name VARCHAR(255) PATH '$')) jt GROUP BY jt.field_name ORDER BY occurrences DESC,jt.field_name LIMIT 150")
    query('epoch_parameter_types_and_cardinality',"SELECT jt.field_name,JSON_TYPE(JSON_EXTRACT(e.parameters,CONCAT('$.',JSON_QUOTE(jt.field_name)))) AS json_type,COUNT(*) AS occurrences,COUNT(DISTINCT CAST(JSON_EXTRACT(e.parameters,CONCAT('$.',JSON_QUOTE(jt.field_name))) AS CHAR(4096))) AS distinct_values,AVG(JSON_LENGTH(JSON_EXTRACT(e.parameters,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS mean_json_length,MAX(JSON_LENGTH(JSON_EXTRACT(e.parameters,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS max_json_length FROM `schema`.epoch e JOIN JSON_TABLE(JSON_KEYS(e.parameters), '$[*]' COLUMNS(field_name VARCHAR(255) PATH '$')) jt GROUP BY jt.field_name,json_type ORDER BY jt.field_name,json_type LIMIT 150")
    query('property_shape',"SELECT jt.field_name,JSON_TYPE(JSON_EXTRACT(e.properties,CONCAT('$.',JSON_QUOTE(jt.field_name)))) AS json_type,COUNT(*) AS occurrences,AVG(JSON_LENGTH(JSON_EXTRACT(e.properties,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS mean_json_length,MAX(JSON_LENGTH(JSON_EXTRACT(e.properties,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS max_json_length,AVG(OCTET_LENGTH(JSON_EXTRACT(e.properties,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS mean_value_bytes,MAX(OCTET_LENGTH(JSON_EXTRACT(e.properties,CONCAT('$.',JSON_QUOTE(jt.field_name))))) AS max_value_bytes FROM `schema`.epoch e JOIN JSON_TABLE(JSON_KEYS(e.properties), '$[*]' COLUMNS(field_name VARCHAR(255) PATH '$')) jt GROUP BY jt.field_name,json_type ORDER BY jt.field_name,json_type LIMIT 30")
    query('stream_density','SELECT stream_count,COUNT(*) AS epochs FROM (SELECT e.id,COUNT(r.id) AS stream_count FROM `schema`.epoch e LEFT JOIN `schema`.response r ON r.parent_id=e.id GROUP BY e.id) d GROUP BY stream_count ORDER BY stream_count LIMIT 30')
    query('source_manifest_aggregates',"SELECT experiment_id,JSON_EXTRACT(manifest,'$.counts') AS counts,JSON_EXTRACT(manifest,'$.protocol_epoch_counts') AS protocol_epoch_counts,JSON_EXTRACT(manifest,'$.status') AS status,JSON_EXTRACT(manifest,'$.review_status') AS review_status FROM recording_workspace.source ORDER BY experiment_id LIMIT 20")
finally:
    conn.rollback()
    conn.close()
    signal.alarm(0)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'schema-profile.json').write_text(json.dumps(results,indent=2,default=str))
    print(json.dumps({'output':str(OUT/'schema-profile.json'),'queries':{k:v for k,v in results['queries'].items() if k not in ['tables','columns']}},default=str))
