"""Read-only SRM storage/query audit. No app mutations; output goes to stdout."""
from pathlib import Path
import sys,json,subprocess,sqlite3,time,statistics,tracemalloc,urllib.request,hashlib,datetime
import pymysql
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'python'))
from workspace_state_snapshot import capture,serialized
ROOT=Path('/Users/maxwellsdm/Documents/RecordingWorkspace/RetinaSRM')
info=json.loads(subprocess.check_output(['docker','inspect','new_retinanalysis-db-1']))[0]
password=next(v.split('=',1)[1] for v in info['Config']['Env'] if v.startswith('MYSQL_ROOT_PASSWORD='))
report={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'project':str(ROOT)}
report['storage']={}
for name in ['database/mysql','raw-uploads','imports','cache/metadata','cache/source-projections','exports','backups']:
 files=[p for p in (ROOT/name).rglob('*') if p.is_file() and not p.is_symlink()]
 report['storage'][name]={'files':len(files),'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files)}
report['metadata_indexes']=[]
for p in sorted((ROOT/'cache/metadata').glob('*.sqlite')):
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as c:
  report['metadata_indexes'].append({'name':p.name,'bytes':p.stat().st_size,'epochs':c.execute('select count(*) from epochs').fetchone()[0],
   'row_json_bytes':c.execute('select sum(length(row_json)) from epochs').fetchone()[0],
   'detail_blob_bytes':c.execute('select sum(length(detail_blob)) from epochs').fetchone()[0]})
with pymysql.connect(host='127.0.0.1',port=3306,user='root',password=password,autocommit=False) as conn:
 with conn.cursor() as c:
  c.execute('SET SESSION TRANSACTION READ ONLY');conn.begin()
  c.execute('SELECT table_schema,table_name,table_rows,data_length,index_length FROM information_schema.tables WHERE table_schema IN (%s,%s)',('schema','recording_workspace'))
  report['sql_tables']=[dict(zip(['schema','table','estimated_rows','data_bytes','index_bytes'],r)) for r in c.fetchall()]
  c.execute("SELECT COUNT(*),SUM(JSON_LENGTH(recipe,'$.epochs')),SUM(JSON_STORAGE_SIZE(recipe)) FROM recording_workspace.explorer_revision")
  report['explorer_revisions']=dict(zip(['count','epoch_references','recipe_bytes'],map(int,c.fetchone())))
  c.execute("SELECT COUNT(DISTINCT revision_uuid) FROM recording_workspace.protocol_binding")
  report['active_bound_revisions']=c.fetchone()[0]
  c.execute('SELECT COUNT(*),SUM(JSON_STORAGE_SIZE(recipe)) FROM recording_workspace.dataset_revision')
  report['export_recipes']=dict(zip(['count','recipe_bytes'],map(int,c.fetchone())))
 class Adapter:
  def __init__(self):self.queries=[];self.bytes=0;self.rows=0
  def query(self,sql,args=None,as_dict=False):
   assert sql.lstrip().split()[0].upper() in {'SELECT','SHOW'}
   with conn.cursor(pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor) as c:
    c.execute(sql,args);result=c.fetchall()
   self.queries.append(sql);self.rows+=len(result);self.bytes+=len(json.dumps(result,default=str).encode())
   return type('Result',(),{'fetchall':lambda self:result})()
 captures=[]
 for _ in range(3):
  a=Adapter();t=time.perf_counter();state=capture(ROOT,a);duration=time.perf_counter()-t
  captures.append({'seconds':duration,'sql_queries':len(a.queries),'rows_fetched':a.rows,'json_bytes_fetched':a.bytes,'captured_bytes':len(serialized(state))})
 report['capture_only_samples']=captures
 tracemalloc.start();state=capture(ROOT,Adapter());report['capture_python_peak_bytes']=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
 conn.rollback()
report['exports']=[]
for p in sorted((ROOT/'exports').rglob('*.sqlite')):
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as c:
  stats=c.execute('select name,sum(pgsize) from dbstat group by name order by sum(pgsize) desc').fetchall()
  report['exports'].append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'table_bytes':dict(stats)})
report['snapshot']={'latest_bytes':(ROOT/'app-state.json').stat().st_size,'daily_files':len(list((ROOT/'backups/app-state').glob('*.sqlite')))}
d=json.loads((ROOT/'app-state.json').read_text());d['tables'].pop('dataset_revision',None)
report['snapshot']['without_export_recipes_bytes']=len(serialized(d))
def request(path,body=None):
 data=None if body is None else json.dumps(body).encode()
 req=urllib.request.Request('http://127.0.0.1:8766/api'+path,data=data,headers={'Content-Type':'application/json','X-Workspace-Request':'1','Origin':'http://localhost:8766'})
 t=time.perf_counter()
 with urllib.request.urlopen(req,timeout=30) as response:raw=response.read()
 return json.loads(raw),{'seconds':time.perf_counter()-t,'response_bytes':len(raw)}
overview,_=request('/overview');pid=overview['protocols'][0]['protocol_uuid'];page,_=request('/protocols/'+pid+'/epochs?limit=1');eid=page['epochs'][0]['epoch_uuid']
report['read_http_samples']={}
for label,path,body in [('epoch_detail','/epochs/'+eid,None),('annotation_read_post','/annotations/read',{'target_kind':'epoch','target_uuids':[eid]}),('epoch_page','/protocols/'+pid+'/epochs?limit=1',None),('overview','/overview',None)]:
 report['read_http_samples'][label]=[request(path,body)[1] for _ in range(3)]
print(json.dumps(report,indent=2))
