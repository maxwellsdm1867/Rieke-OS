"""Reconcile native registered blocks with nonempty source projections, read only."""
import json, pathlib, signal
import pymysql

ROOT=pathlib.Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
OUT=pathlib.Path('/private/tmp/disco-real-data-evals-20261001/native')
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('15 second cap')))
signal.alarm(15)
credentials=json.loads((ROOT/'database/native-credentials.json').read_text())
catalog=json.loads((ROOT/'catalog.json').read_text())
conn=pymysql.connect(host=catalog['connection']['host'],port=catalog['connection']['port'],user='root',password=credentials['password'],connect_timeout=3,read_timeout=4,write_timeout=3,autocommit=False,cursorclass=pymysql.cursors.DictCursor)
del credentials
results={}
queries={
'empty_blocks': '''SELECT b.id AS block_id,b.h5_uuid AS block_uuid,b.experiment_id,b.parent_id AS group_id,b.protocol_id,p.name AS protocol_name,COUNT(e.id) AS epochs
FROM `schema`.epoch_block b LEFT JOIN `schema`.epoch e ON e.parent_id=b.id
LEFT JOIN `schema`.protocol p ON p.protocol_id=b.protocol_id
GROUP BY b.id,b.h5_uuid,b.experiment_id,b.parent_id,b.protocol_id,p.name HAVING COUNT(e.id)=0 ORDER BY b.experiment_id,b.id LIMIT 20''',
'block_counts_by_source': '''SELECT d.experiment_id,COUNT(*) AS registered_blocks,SUM(d.epochs=0) AS zero_epoch_blocks,SUM(d.epochs>0) AS nonempty_blocks,SUM(d.epochs) AS epochs
FROM (SELECT b.id,b.experiment_id,COUNT(e.id) AS epochs FROM `schema`.epoch_block b LEFT JOIN `schema`.epoch e ON e.parent_id=b.id GROUP BY b.id,b.experiment_id) d GROUP BY d.experiment_id ORDER BY d.experiment_id LIMIT 20''',
'sixth_protocol_relations': '''SELECT p.protocol_id,p.name,(SELECT COUNT(*) FROM `schema`.epoch_group g WHERE g.protocol_id=p.protocol_id) AS group_count,(SELECT COUNT(*) FROM `schema`.epoch_block b WHERE b.protocol_id=p.protocol_id) AS blocks,(SELECT COUNT(*) FROM `schema`.epoch e JOIN `schema`.epoch_block b ON b.id=e.parent_id WHERE b.protocol_id=p.protocol_id) AS epochs FROM `schema`.protocol p WHERE p.name='no_group_protocol' LIMIT 10''',
'unregistered_source_blocks': '''SELECT COUNT(*) AS blocks FROM `schema`.epoch_block b LEFT JOIN recording_workspace.source s ON s.experiment_id=b.experiment_id WHERE s.experiment_id IS NULL'''
}
try:
    with conn.cursor() as cur:
        cur.execute('SET SESSION MAX_EXECUTION_TIME=3000')
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        for key,sql in queries.items():
            cur.execute(sql)
            results[key]=cur.fetchall()
finally:
    conn.rollback();conn.close();signal.alarm(0)
(OUT/'block-reconciliation.json').write_text(json.dumps(results,indent=2,default=str))
print(json.dumps(results,default=str))
