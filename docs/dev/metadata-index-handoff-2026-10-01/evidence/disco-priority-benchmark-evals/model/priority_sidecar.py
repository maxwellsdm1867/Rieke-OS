"""Isolated A/B: selected hot dictionary, full native fields via deferred dictionaries.
Shared immutable proved core is excluded from this projection's build/storage cost.
No writes to native base, full typed sidecar, or application checkout.
"""
import json, os, resource, sqlite3, sys, time
from pathlib import Path
PREVIOUS=Path('/private/tmp/disco-real-million-20261001/typed')
sys.path.insert(0,str(PREVIOUS))
from typed_bounded import TypedBoundedSidecar
from typed_sidecar import attach_native, Budget
from typed_real_previous import CORE_FIELDS, canonical, equality_json, predicates, Decoder
DDL='''CREATE TABLE typed_values(value_id INTEGER PRIMARY KEY,field_no INTEGER NOT NULL,
kind TEXT NOT NULL,numeric_value,numeric_class TEXT,text_value TEXT,equality_json TEXT NOT NULL,value_json TEXT NOT NULL);'''
INDEXES=[('numeric','field_no,kind,numeric_value,value_id'),('text','field_no,kind,text_value,value_id'),('equality','field_no,equality_json,value_id'),('kind','field_no,kind,value_id')]

def identity(path):
 s=Path(path).stat();return [s.st_ino,s.st_size,s.st_mtime_ns]

def build(full_path,target_path,hot_fields,max_seconds=180):
 full_path,target_path=Path(full_path).resolve(),Path(target_path).resolve()
 if target_path.exists() or full_path==target_path:raise ValueError('Fresh separate target required')
 target_path.parent.mkdir(parents=True,exist_ok=True)
 start=time.perf_counter(); budget=Budget(target_path.parent,max_seconds=max_seconds)
 con=sqlite3.connect(target_path,uri=True);times={}
 try:
  con.execute('PRAGMA cache_size=-32768');con.execute('PRAGMA temp_store=FILE');con.execute('PRAGMA journal_mode=OFF');con.execute('PRAGMA synchronous=OFF')
  con.execute('ATTACH DATABASE ? AS full',(full_path.as_uri()+'?mode=ro&immutable=1',))
  receipts={key:json.loads(raw) for key,raw in con.execute('SELECT key,value_json FROM full.typed_receipt')}
  source=Path(receipts['source_path']);attach_native(con,source)
  fields=dict(con.execute('SELECT field_id,field_no FROM fields'))
  requested_hot_fields=list(hot_fields)
  if len(hot_fields)!=len(set(hot_fields)) or set(hot_fields)-set(fields):raise ValueError('Invalid hot field list')
  direct_core_fields=[field for field in hot_fields if receipts['core_safe'].get(field)]
  hot_fields=[field for field in hot_fields if field not in direct_core_fields]
  con.set_progress_handler(budget.sql_check,100000)
  con.executescript(DDL+'CREATE TABLE priority_receipt(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);')
  t=time.perf_counter()
  numbers=[fields[field] for field in hot_fields]
  if numbers:
   con.execute('INSERT INTO main.typed_values SELECT * FROM full.typed_values WHERE field_no IN ('+','.join('?' for _ in numbers)+')',numbers)
  con.commit();times['selected_dictionary_copy_seconds']=time.perf_counter()-t
  t=time.perf_counter()
  for name,columns in INDEXES:con.execute(f'CREATE INDEX typed_{name} ON typed_values({columns})')
  con.execute('ANALYZE main');con.commit();times['indexes_and_analyze_seconds']=time.perf_counter()-t
  extra={'core_path':str(full_path),'core_identity':identity(full_path),'hot_fields':hot_fields,'requested_hot_fields':requested_hot_fields,'direct_core_fields':direct_core_fields,'dictionary_policy':'selected hot fields plus deferred exact native dictionary per requested field'}
  for key,value in dict(receipts,**extra).items():con.execute('INSERT INTO priority_receipt VALUES (?,?)',(key,canonical(value)))
  con.commit()
  t=time.perf_counter();assert con.execute('PRAGMA main.quick_check').fetchone()[0]=='ok'
  count=con.execute('SELECT COUNT(*) FROM main.typed_values').fetchone()[0]
  byfield=dict(con.execute('SELECT field_no,COUNT(*) FROM main.typed_values GROUP BY field_no'))
  shared_sizes=dict(con.execute("SELECT name,SUM(pgsize) FROM dbstat('full') GROUP BY name"))
  dictionary_assets={'typed_values','typed_numeric','typed_text','typed_equality','typed_kind'}
  core_bytes=sum(n for table,n in shared_sizes.items() if table=='typed_core' or table.startswith('typed_') and table not in dictionary_assets|{'typed_receipt'})
  full_dictionary_bytes=sum(n for table,n in shared_sizes.items() if table in dictionary_assets)
  full_dictionary_rows=con.execute('SELECT COUNT(*) FROM full.typed_values').fetchone()[0]
  times['quick_check_and_sizes_seconds']=time.perf_counter()-t
  budget.check(True)
  return dict(all_passed=True,target=str(target_path),wall_seconds=time.perf_counter()-start,timings=times,
   added_bytes=target_path.stat().st_size,hot_fields=hot_fields,requested_hot_fields=requested_hot_fields,direct_core_fields=direct_core_fields,typed_dictionary_rows=count,full_dictionary_rows=full_dictionary_rows,field_rows=byfield,
   shared_core_storage_bytes=core_bytes,full_dictionary_storage_bytes=full_dictionary_bytes,full_sidecar_page_assets=shared_sizes,
   logical_standalone_core_plus_projection_bytes=core_bytes+target_path.stat().st_size,
   actual_auxiliary_files_bytes=full_path.stat().st_size+target_path.stat().st_size,
   physical_storage_warning='Core is attached from the intact full sidecar; no physical full-sidecar storage has been removed. Logical standalone estimate only, not a built standalone artifact.',
   shared_core_build='reused proved previous core; excluded from incremental build timing',
   full_typed_sidecar_bytes=full_path.stat().st_size,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
   source_identity_unchanged=identity(source)==receipts['source_identity'],core_identity_unchanged=identity(full_path)==extra['core_identity'])
 finally:con.close()

class PrioritySidecar(TypedBoundedSidecar):
 def __init__(self,path):
  self.path=Path(path).resolve();self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
  self.connection.execute('PRAGMA cache_size=-32768');self.connection.execute('PRAGMA temp_store=FILE')
  receipts={key:json.loads(raw) for key,raw in self.connection.execute('SELECT key,value_json FROM priority_receipt')}
  for name,key in [('source_path','source_identity'),('core_path','core_identity')]:
   if identity(receipts[name])!=receipts[key]:raise ValueError('Bound immutable input generation changed')
  attach_native(self.connection,receipts['source_path'])
  self.connection.execute('ATTACH DATABASE ? AS core',(Path(receipts['core_path']).as_uri()+'?mode=ro&immutable=1',))
  self.connection.execute('PRAGMA core.cache_size=-32768')
  self.connection.execute('CREATE TEMP VIEW typed_core AS SELECT * FROM core.typed_core')
  self.connection.execute('CREATE TEMP TABLE supplied_scope(epoch_id INTEGER PRIMARY KEY)')
  self.connection.executescript(DDL.replace('CREATE TABLE typed_values','CREATE TEMP TABLE deferred_values'))
  for name,columns in INDEXES:self.connection.execute(f'CREATE INDEX deferred_{name} ON deferred_values({columns})')
  self.fields=dict(self.connection.execute('SELECT field_id,field_no FROM fields'))
  self.definitions=[json.loads(raw) for raw, in self.connection.execute('SELECT definition_json FROM fields ORDER BY field_no')]
  self.wide_fields=set(receipts['wide_numeric_fields']);self.core_safe=receipts['core_safe']
  self.core_string_fields={field for field,safe in self.core_safe.items() if safe}
  self.validation_representatives=receipts['validation_representatives'];self.hot_fields=set(receipts['hot_fields'])
  self.deferred=set();self.materializations=[];self.decoder=Decoder()
 def _validate(self,predicate):
  # Exactly the previous representative validation, not a changed field policy.
  from typed_sidecar import TypedRealSidecar
  return TypedRealSidecar._validate(self,predicate)
 def _table(self,field):
  if field in self.hot_fields:return 'main.typed_values'
  number=self.fields[field]
  if field not in self.deferred:
   start=time.perf_counter();rows=0;batch=[]
   try:
    for value_id,raw in self.connection.execute('SELECT value_id,value_json FROM native.field_values WHERE field_no=?',[number]):
     value=json.loads(raw);kind=predicates.kind(value);numeric=numeric_class=None
     if kind=='number':
      numeric_class='integer' if type(value) is int else 'float'
      if type(value) is int and abs(value)>2**53-1:numeric_class='wide_integer'
      else:numeric=value
     batch.append((value_id,number,kind,numeric,numeric_class,value if kind=='string' else None,equality_json(value),raw));rows+=1
     if len(batch)>=2000:self.connection.executemany('INSERT INTO deferred_values VALUES (?,?,?,?,?,?,?,?)',batch);batch=[]
    if batch:self.connection.executemany('INSERT INTO deferred_values VALUES (?,?,?,?,?,?,?,?)',batch)
    self.connection.commit();self.deferred.add(field)
    self.materializations.append(dict(field=field,rows=rows,seconds=time.perf_counter()-start))
   except BaseException:
    self.connection.rollback();raise
  return 'deferred_values'
 def _leaf(self,node):
  field,op=node['field'],node['operator'];number=self.fields[field];column=CORE_FIELDS.get(field)
  if column and self.core_safe.get(field) and op in {'eq','exists','missing','is_null'}:
   if op=='exists':return '1',[]
   if op in {'missing','is_null'}:return '0',[]
   if predicates.kind(node['value'])=='string':return f'c.{column}=?',[node['value']]
  if op=='missing':return 'c.epoch_id NOT IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)',[number]
  if op=='exists':return 'c.epoch_id IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)',[number]
  table=self._table(field);args=[number]
  if op=='is_null':selector="v.kind='null'"
  elif op in {'eq','ne','in','not_in'}:
   choices=node['value'] if op in {'in','not_in'} else [node['value']]
   selector='v.equality_json IN ('+','.join('?' for _ in choices)+')' if choices else '0';args.extend(equality_json(value) for value in choices)
   if op in {'ne','not_in'}:selector='NOT ('+selector+')'
  elif op in {'gt','gte','lt','lte'} and number not in self.wide_fields:
   selector="v.kind='number' AND v.numeric_value "+{'gt':'>','gte':'>=','lt':'<','lte':'<='}[op]+' ?';args.append(node['value'])
  else:
   matches=[value_id for value_id,raw in self.connection.execute(f'SELECT value_id,value_json FROM {table} WHERE field_no=?',[number]) if predicates.matches(node,{field:json.loads(raw)})]
   selector='v.value_id IN ('+','.join('?' for _ in matches)+')' if matches else '0';args.extend(matches)
  return ('c.epoch_id IN (SELECT ev.epoch_id FROM '+table+' v JOIN epoch_values ev ON ev.field_no=v.field_no AND ev.value_id=v.value_id WHERE v.field_no=? AND ('+selector+'))'),args
 def preview(self,predicate=None,scope=None,facet_fields=(),limit=60,cursor=None):
  if len(facet_fields)>140 or len(set(facet_fields))!=len(facet_fields):raise ValueError('Facet fields must be unique native fields')
  where,args=self._where(predicate,scope)
  count=self.connection.execute('SELECT COUNT(*) FROM typed_core c WHERE '+where,args).fetchone()[0]
  page=self._page(where,args,cursor,limit);facets={};selective=isinstance(scope,dict) and bool(set(scope)&{'cell','block','group'})
  for field in facet_fields:
   if field not in self.fields:raise ValueError('Unknown native facet field')
   number=self.fields[field];table=self._table(field)
   if selective:
    joined=('FROM typed_core c CROSS JOIN epoch_values ev ON ev.epoch_id=c.epoch_id AND ev.field_no=? JOIN '+table+' v USING(value_id) WHERE '+where)
    present_sql='SELECT COUNT(*) FROM typed_core c CROSS JOIN epoch_values ev ON ev.epoch_id=c.epoch_id AND ev.field_no=? WHERE '+where
   else:
    joined='FROM typed_core c JOIN epoch_values ev USING(epoch_id) JOIN '+table+' v USING(value_id) WHERE ev.field_no=? AND ('+where+')'
    present_sql='SELECT COUNT(*) FROM typed_core c JOIN epoch_values ev USING(epoch_id) WHERE ev.field_no=? AND ('+where+')'
   buckets=self.connection.execute('SELECT v.value_json,v.kind,COUNT(*),MIN(c.sort_rank) '+joined+' GROUP BY v.equality_json ORDER BY MIN(c.sort_rank) LIMIT 61',[number]+args).fetchall()
   present=self.connection.execute(present_sql,[number]+args).fetchone()[0]
   facets[field]=dict(values=[dict(value=json.loads(raw),type=kind,count=n) for raw,kind,n,_ in buckets[:60]],missing_count=count-present,present_count=present,values_truncated=len(buckets)>60)
  return dict(count=count,**page,facets=facets)
