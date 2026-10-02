"""Query-only covering-index adjustment on an owned SQLite copy."""
import argparse,hashlib,json,shutil,statistics,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--database',type=Path,required=True);p.add_argument('--csv',type=Path,required=True)
p.add_argument('--baseline-receipt',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(Path(__file__).parent/'readmodel'))
from projection import AnalyticalProjection,identity
def file_hash(path):
 digest=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
 return digest.hexdigest()
before_hash=file_hash(a.database)
report={'scope':__doc__,'source_database_sha256_before':before_hash,'phases':{},'controls':[],'passed':False}
model=None
try:
 began=time.perf_counter();db=a.out/'metadata.sqlite';shutil.copy2(a.database,db);report['phases']['copy_seconds']=time.perf_counter()-began
 model=AnalyticalProjection('sqlite',db)
 def plan(field,filters):
  where,values=model._where(filters)
  sql=f'SELECT {field}_present AS present,{field}_kind AS kind,{field} AS value,COUNT(*) AS count FROM epochs'+where+f' GROUP BY {field}_present,{field}_kind,{field} ORDER BY {field}_present,{field}_kind,{field} LIMIT ?'
  return model.execute('EXPLAIN QUERY PLAN '+sql,values+[61]).fetchall()
 def controls(phase):
  for field in ('seed','currentMean'):
   for scope,filters in [('contrast',{'contrast':.3}),('unfiltered',{}),('cell100',{'cell_uuid':identity(1000000),'contrast':.3})]:
    times=[];hashes=[]
    for i in range(3):
     began=time.perf_counter();value=model.facets(field,filters);encoded=json.dumps(value,sort_keys=True,separators=(',',':')).encode();times.append(time.perf_counter()-began);hashes.append(hashlib.sha256(encoded).hexdigest())
    assert len(set(hashes))==1
    report['controls'].append({'phase':phase,'field':field,'scope':scope,'samples_seconds':times,'median_seconds':statistics.median(times),'sha256':hashes[0],'query_plan':plan(field,filters)})
 controls('before')
 began=time.perf_counter()
 for field in ('seed','currentMean'):
  model.execute(f'CREATE INDEX contrast_{field}_covering ON epochs(contrast_present,contrast_kind,contrast,{field}_present,{field}_kind,{field})')
 model.connection.commit();model.execute('ANALYZE');model.connection.commit()
 report['phases']['covering_index_build_and_analyze_seconds']=time.perf_counter()-began
 report['phases']['persisted_bytes']=db.stat().st_size
 controls('after');model.close();model=None
 for old,new in zip(report['controls'][:6],report['controls'][6:]):assert old['sha256']==new['sha256'],(old['field'],old['scope'])
 queryout=a.out/'queries'
 command=[sys.executable,'-B',str(Path(__file__).parent/'evaluate.py'),'--mode','sqlite','--epochs','1000000','--csv',str(a.csv),'--out',str(queryout),'--reuse-database',str(db),'--cap','180']
 with (a.out/'query.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 old=json.loads(a.baseline_receipt.read_text());new=json.loads((queryout/'receipt.json').read_text());assert old['passed'] and new['passed']
 for x,y in zip(old['operations'],new['operations']):assert x['name']==y['name'] and x['result_sha256']==y['result_sha256'],x['name']
 report['all_ten_original_query_hashes_unchanged']=True
 report['source_database_sha256_after']=file_hash(a.database)
 assert before_hash==report['source_database_sha256_after'],'Shared baseline database was modified'
 report['passed']=True
finally:
 if model:model.close()
 (a.out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if report['passed'] else 1)
