"""Previous typed experiment's auxiliary indexes with one shared immutable base.

Native tables stay in the sealed source file. This packaging saves a second full
copy; it does not replace original metadata, predicate semantics or JSON DTOs.
"""
from __future__ import annotations
import json, os, resource, shutil, sqlite3, time
from pathlib import Path
from typed_real_previous import (TypedReal, ORIGINAL_TABLES, CORE_COLUMNS, CORE_FIELDS,
                                canonical, equality_json, predicates, Decoder, file_sha)


def attach_native(connection, source_path):
    source = Path(source_path).resolve()
    connection.execute('ATTACH DATABASE ? AS native', (source.as_uri()+'?mode=ro&immutable=1',))
    for table in ORIGINAL_TABLES:
        connection.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM native.{table}')
    connection.execute('PRAGMA native.cache_size=-32768')


class Budget:
    def __init__(self, directory, max_seconds=300, min_free_gib=4, max_rss_gib=1):
        self.directory = directory
        self.started = time.perf_counter()
        self.max_seconds = max_seconds
        self.min_free = min_free_gib * 1024**3
        self.max_rss = max_rss_gib * 1024**3
        self.reason = None
        self.last = 0
    def check(self, force=False):
        now = time.perf_counter()
        if not force and now-self.last < .5:
            return 0
        self.last = now
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if now-self.started > self.max_seconds:
            self.reason = 'phase time budget exceeded'
        elif usage > self.max_rss:
            self.reason = 'RSS budget exceeded'
        elif shutil.disk_usage(self.directory).free < self.min_free:
            self.reason = 'free disk reserve reached'
        if self.reason:
            raise RuntimeError(self.reason)
        return 0
    def sql_check(self):
        try: return self.check()
        except RuntimeError: return 1


def build(source_db, target_db, *, max_seconds=300, min_free_gib=4, max_rss_gib=1, progress=None):
    source_db, target_db = Path(source_db).resolve(), Path(target_db).resolve()
    if source_db == target_db or target_db.exists():
        raise ValueError('Requires a fresh sidecar path distinct from source')
    target_db.parent.mkdir(parents=True, exist_ok=True)
    source_stat = source_db.stat()
    target = sqlite3.connect(target_db, uri=True)
    budget = Budget(target_db.parent, max_seconds, min_free_gib, max_rss_gib)
    timings, kinds, wide_fields, representatives = {}, {}, set(), {}
    def mark(label, start):
        timings[label] = time.perf_counter()-start
        if progress: progress({'phase': label, 'seconds': timings[label], 'bytes': target_db.stat().st_size})
        budget.check(True)
    try:
        target.execute('PRAGMA cache_size=-32768')
        target.execute('PRAGMA temp_store=FILE')
        target.execute('PRAGMA journal_mode=OFF')
        target.execute('PRAGMA synchronous=OFF')
        attach_native(target, source_db)
        target.set_progress_handler(budget.sql_check, 100000)
        target.executescript('''
            CREATE TABLE typed_core(
                epoch_id INTEGER PRIMARY KEY,sort_rank INTEGER,epoch_uuid TEXT NOT NULL,
                source_sha256 TEXT,cell_uuid TEXT,block_uuid TEXT,group_uuid TEXT,
                protocol_name TEXT,date TEXT,start_time TEXT,block_start_time TEXT,
                epoch_number INTEGER,duration_seconds REAL,cell_label TEXT,cell_type TEXT,group_label TEXT);
            CREATE TABLE typed_values(
                value_id INTEGER PRIMARY KEY,field_no INTEGER NOT NULL,
                kind TEXT NOT NULL,numeric_value,numeric_class TEXT,text_value TEXT,
                equality_json TEXT NOT NULL,value_json TEXT NOT NULL);
            CREATE TABLE typed_receipt(key TEXT PRIMARY KEY,value_json TEXT NOT NULL);
        ''')
        start = time.perf_counter()
        batch=[]
        for epoch_id, raw in target.execute('SELECT epoch_id,row_json FROM native.epochs ORDER BY epoch_id'):
            row=json.loads(raw)
            batch.append([epoch_id, None]+[row.get(name) for name in CORE_COLUMNS])
            if len(batch)>=2000:
                target.executemany('INSERT INTO typed_core VALUES ('+','.join('?' for _ in range(16))+')',batch)
                batch.clear(); budget.check()
        if batch: target.executemany('INSERT INTO typed_core VALUES ('+','.join('?' for _ in range(16))+')',batch)
        target.commit(); mark('core_extract_seconds',start)
        start=time.perf_counter()
        # Only short chronology columns are sorted, never the multi-KB row JSON.
        target.execute('CREATE TABLE typed_ranks AS SELECT epoch_id,ROW_NUMBER() OVER (ORDER BY COALESCE(date,\'\'),COALESCE(start_time,\'\'),epoch_uuid) AS sort_rank FROM typed_core')
        target.execute('CREATE UNIQUE INDEX typed_ranks_id ON typed_ranks(epoch_id)')
        target.execute('UPDATE typed_core SET sort_rank=(SELECT sort_rank FROM typed_ranks r WHERE r.epoch_id=typed_core.epoch_id)')
        target.execute('DROP TABLE typed_ranks')
        target.commit(); mark('chronology_assign_seconds',start)
        start=time.perf_counter(); batch=[]
        for value_id, field_no, raw in target.execute('SELECT value_id,field_no,value_json FROM native.field_values ORDER BY value_id'):
            value=json.loads(raw); kind=predicates.kind(value); kinds[kind]=kinds.get(kind,0)+1
            numeric=numeric_class=None; text=value if kind=='string' else None
            if kind=='number':
                numeric_class='integer' if type(value) is int else 'float'
                if type(value) is int and abs(value)>2**53-1:
                    numeric_class='wide_integer';wide_fields.add(field_no)
                else: numeric=value
            batch.append((value_id,field_no,kind,numeric,numeric_class,text,equality_json(value),raw))
            # validate() only inspects observed value and array-element kinds.
            # Preserve one actual value for each such kind, avoiding million-ID
            # dictionary scans when predicates are validated at query time.
            samples=representatives.setdefault(field_no,{})
            samples.setdefault(kind,raw)
            if kind=='array':
                for item in value:
                    samples.setdefault('array_element:'+predicates.kind(item),raw)
            if len(batch)>=2000:
                target.executemany('INSERT INTO typed_values VALUES (?,?,?,?,?,?,?,?)',batch)
                batch.clear();budget.check()
        if batch:target.executemany('INSERT INTO typed_values VALUES (?,?,?,?,?,?,?,?)',batch)
        target.commit();mark('dictionary_extract_seconds',start)
        start=time.perf_counter()
        for sql in [
            'CREATE UNIQUE INDEX typed_uuid ON typed_core(epoch_uuid)',
            'CREATE UNIQUE INDEX typed_sort_rank ON typed_core(sort_rank)',
            'CREATE INDEX typed_chronology ON typed_core(date,start_time,epoch_uuid)',
            'CREATE INDEX typed_cell_children ON typed_core(cell_uuid,sort_rank)',
            'CREATE INDEX typed_block_children ON typed_core(block_uuid,sort_rank)',
            'CREATE INDEX typed_group_children ON typed_core(group_uuid,sort_rank)',
            'CREATE INDEX typed_protocol_children ON typed_core(protocol_name,sort_rank)',
            'CREATE INDEX typed_numeric ON typed_values(field_no,kind,numeric_value,value_id)',
            'CREATE INDEX typed_text ON typed_values(field_no,kind,text_value,value_id)',
            'CREATE INDEX typed_equality ON typed_values(field_no,equality_json,value_id)',
            'CREATE INDEX typed_kind ON typed_values(field_no,kind,value_id)']:
            target.execute(sql);target.commit();budget.check(True)
        mark('indexes_seconds',start)
        start=time.perf_counter();core_safe={}
        for field,column in CORE_FIELDS.items():
            number=target.execute('SELECT field_no FROM fields WHERE field_id=?',(field,)).fetchone()
            if number is None:continue
            bad=target.execute(f'''SELECT 1 FROM typed_core c
                LEFT JOIN native.epoch_values ev ON c.epoch_id=ev.epoch_id AND ev.field_no=?
                LEFT JOIN native.field_values v USING(value_id)
                WHERE v.value_json IS NULL OR json_type(v.value_json)<>'text'
                  OR c.{column} IS NULL OR c.{column}<>json_extract(v.value_json,'$') LIMIT 1''',number).fetchone()
            core_safe[field]=bad is None
        for key,value in [('wide_numeric_fields',sorted(wide_fields)),('core_safe',core_safe),
                          ('validation_representatives',representatives),('source_path',str(source_db)),
                          ('source_identity',[source_stat.st_ino,source_stat.st_size,source_stat.st_mtime_ns])]:
            target.execute('INSERT INTO typed_receipt VALUES (?,?)',(key,canonical(value)))
        target.commit();mark('core_equality_proof_seconds',start)
        start=time.perf_counter();target.execute('ANALYZE main');target.commit()
        mark('analyze_seconds',start)
        start=time.perf_counter()
        if target.execute('PRAGMA main.quick_check').fetchone()[0]!='ok':raise ValueError('Sidecar quick_check failed')
        counts={table:target.execute(f'SELECT COUNT(*) FROM native.{table}').fetchone()[0] for table in ORIGINAL_TABLES}
        after=source_db.stat()
        if (source_stat.st_ino,source_stat.st_size,source_stat.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('Source file stat changed')
        mark('quick_check_and_counts_seconds',start)
        return {'source':str(source_db),'target':str(target_db),'build_seconds':sum(timings.values()),
                'wall_seconds':time.perf_counter()-budget.started,'timings':timings,'added_bytes':target_db.stat().st_size,
                'original_bytes':source_stat.st_size,'dictionary_kinds':kinds,'core_safe':core_safe,
                'wide_numeric_fields':sorted(wide_fields),'native_table_counts':counts,
                'packaging':'shared immutable source plus typed auxiliary sidecar; no source clone',
                'source_stat_unchanged':True,'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'source_full_sha256_verification':'separate parent-owned preservation phase',
                'validation_representatives':'actual values covering every observed kind and array-element kind',
                'no_detail_materialization':True,'all_passed':True}
    finally:target.close()


class TypedRealSidecar(TypedReal):
    def __init__(self, db_path, source_path=None):
        self.path=Path(db_path).resolve()
        self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
        self.connection.execute('PRAGMA cache_size=-32768')
        self.connection.execute('PRAGMA temp_store=FILE')
        receipts={key:json.loads(raw) for key,raw in self.connection.execute('SELECT key,value_json FROM typed_receipt')}
        bound_source=Path(source_path or receipts['source_path']).resolve()
        bound_stat=bound_source.stat()
        if receipts['source_identity'] != [bound_stat.st_ino,bound_stat.st_size,bound_stat.st_mtime_ns]:
            self.connection.close()
            raise ValueError('Typed sidecar belongs to a different native database generation')
        attach_native(self.connection,bound_source)
        self.connection.execute('CREATE TEMP TABLE supplied_scope(epoch_id INTEGER PRIMARY KEY)')
        self.fields=dict(self.connection.execute('SELECT field_id,field_no FROM fields'))
        self.definitions=[json.loads(raw) for raw, in self.connection.execute('SELECT definition_json FROM fields ORDER BY field_no')]
        self.wide_fields=set(receipts['wide_numeric_fields']);self.core_safe=receipts['core_safe']
        self.core_string_fields={field for field,safe in self.core_safe.items() if safe}
        self.validation_representatives=receipts['validation_representatives']
        self.decoder=Decoder()
    def _validate(self,predicate):
        referenced=set()
        def collect(node):
            if not isinstance(node,dict):return
            if 'all' in node or 'any' in node:
                items=node.get('all',node.get('any',[]))
                if isinstance(items,list):
                    for child in items:collect(child)
            elif 'not' in node:collect(node['not'])
            elif isinstance(node.get('field'),str):referenced.add(node['field'])
        collect(predicate)
        outer=self
        class Representatives:
            def values(self):
                for field in referenced:
                    number=outer.fields.get(field)
                    for raw in set(outer.validation_representatives.get(str(number),{}).values()):
                        yield {field:json.loads(raw)}
        return predicates.validate(predicate,{'fields':self.definitions},Representatives())
    def iter_membership(self,predicate=None,scope=None):
        where,arguments=self._where(predicate,scope)
        for identity, in self.connection.execute('SELECT c.epoch_uuid FROM typed_core c WHERE '+where+' ORDER BY c.sort_rank',arguments):
            yield identity
