import hashlib,json,sqlite3,statistics,sys,time,uuid
from pathlib import Path
count=int(sys.argv[1]);folder=Path(__file__).parent/str(count);db=folder/'index.sqlite'
connection=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
uid=lambda n:str(uuid.UUID(bytes=hashlib.sha256(str(n).encode()).digest()[:16]))
field=connection.execute('SELECT field_no FROM fields WHERE field_id=?',('parameters/contrast',)).fetchone()[0]
value=connection.execute('SELECT value_id FROM field_values WHERE field_no=? AND value_json=?',(field,'0.3')).fetchone()[0]
report={'epochs':count,'source_head':'a8fac2c293ccf4fa73a4eb5e93673b41620b1d13','scope':'Read-only indexed SQLite diagnostic control; not current application behavior. Same synthetic protocol insertion order/counts, bounded60decodedmetadata rows. No Python full-catalog projection, curation, global revisions, suggestions or H5 reads.','operations':[]}
def rows(sql,params=()):return [json.loads(r[0])for r in connection.execute(sql,params)]
def contrast():return {'count':connection.execute('SELECT COUNT(*) FROM epoch_values WHERE field_no=? AND value_id=?',(field,value)).fetchone()[0],'epochs':rows('SELECT e.row_json FROM epoch_values v JOIN epochs e ON e.epoch_id=v.epoch_id WHERE v.field_no=? AND v.value_id=? ORDER BY v.epoch_id LIMIT 60',(field,value))}
for name,call,oracle in [('epoch_page_60',lambda:rows('SELECT row_json FROM epochs ORDER BY epoch_id LIMIT 60'),lambda v:[r['epoch_uuid']for r in v]==[uid(i)for i in range(60)]),('contrast_count_page_60',contrast,lambda v:v['count']==count//5 and [r['epoch_uuid']for r in v['epochs']]==[uid(3+5*i)for i in range(60)])]:
    samples=[]
    for _ in range(6):
        beg=time.perf_counter();result=call();samples.append(time.perf_counter()-beg);assert oracle(result)
    report['operations'].append({'name':name,'first_seconds':samples[0],'warm_samples_seconds':samples[1:],'warm_median_seconds':statistics.median(samples[1:]),'warm_max_seconds':max(samples[1:]),'response_json_bytes':len(json.dumps(result,separators=(',',':')).encode()),'oracle_passed':True})
report['query_plans']={'epoch':[list(r)for r in connection.execute('EXPLAIN QUERY PLAN SELECT row_json FROM epochs ORDER BY epoch_id LIMIT 60')],'contrast':[list(r)for r in connection.execute('EXPLAIN QUERY PLAN SELECT e.row_json FROM epoch_values v JOIN epochs e ON e.epoch_id=v.epoch_id WHERE v.field_no=? AND v.value_id=? ORDER BY v.epoch_id LIMIT 60',(field,value))]}
connection.close();(folder/'sql-control.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
