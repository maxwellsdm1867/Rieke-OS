"""Generation-bound typed reads over one shared immutable native metadata base.

Native tables stay in the sealed source file. This packaging saves a second full
copy; it does not replace original metadata, predicate semantics or JSON DTOs.
"""
from __future__ import annotations
import copy
import functools
import hashlib
import json, os, resource, shutil, sqlite3, sys, threading, time
from pathlib import Path
from disco.metadata.typed_query import (_TypedQueries, ORIGINAL_TABLES, CORE_COLUMNS, CORE_FIELDS,
                                canonical, equality_json, predicates, Decoder, file_sha)

FORMAT = 1


class QueryCancelled(RuntimeError):
    """Cooperative cancellation; this is never an empty or successful result."""


def _signature(path):
    current = Path(path).stat()
    return [current.st_dev, current.st_ino, current.st_size,
            current.st_mtime_ns, current.st_ctime_ns]


def _rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


def _guard(method):
    @functools.wraps(method)
    def checked(self, *args, **kwargs):
        self._check()
        try:
            result = method(self, *args, **kwargs)
        except sqlite3.OperationalError:
            if self._cancel_requested():
                raise QueryCancelled('Typed metadata query cancelled') from None
            raise
        self._check()
        return result
    return checked


def attach_native(connection, source_path):
    source = Path(source_path).resolve()
    connection.execute('ATTACH DATABASE ? AS native', (source.as_uri()+'?mode=ro&immutable=1',))
    for table in ORIGINAL_TABLES:
        connection.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM native.{table}')
    connection.execute('PRAGMA native.cache_size=-32768')


class Budget:
    def __init__(self, directory, max_seconds=300, min_free_gib=4, max_rss_gib=1, cancelled=None):
        self.directory = directory
        self.started = time.perf_counter()
        self.max_seconds = max_seconds
        self.min_free = min_free_gib * 1024**3
        self.max_rss = max_rss_gib * 1024**3
        self.reason = None
        self.last = 0
        self.cancelled = cancelled
    def check(self, force=False):
        now = time.perf_counter()
        if not force and now-self.last < .5:
            return 0
        self.last = now
        usage = _rss_bytes()
        if self.cancelled and self.cancelled():
            self.reason = 'build cancelled'
        elif now-self.started > self.max_seconds:
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


def build(source_db, target_db, *, max_seconds=300, min_free_gib=4, max_rss_gib=1,
          progress=None, expected_generation=None, expected_project_uuid=None, cancel_check=None):
    """Build a fresh, sealed sidecar from a caller-verified immutable native base.

    Native seal verification and reader leases belong to the lifecycle adapter.
    This builder never publishes a generation or modifies the native database.
    Failed builds retain an unsealed partial asset for bounded cleanup by callers.
    """
    if Path(source_db).is_symlink() or Path(target_db).is_symlink():
        raise ValueError('Typed indexes cannot use symbolic links')
    source_db, target_db = Path(source_db).resolve(), Path(target_db).resolve()
    if source_db == target_db or target_db.exists() or Path(str(target_db)+'.sha256.json').exists():
        raise ValueError('Requires a fresh sidecar path distinct from source')
    target_db.parent.mkdir(parents=True, exist_ok=True)
    source_stat = source_db.stat()
    source_identity = _signature(source_db)
    # Exclusive reservation avoids overwriting a competing builder's asset.
    descriptor = os.open(target_db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    target = sqlite3.connect(target_db, uri=True)
    budget = Budget(target_db.parent, max_seconds, min_free_gib, max_rss_gib, cancel_check)
    timings, kinds, wide_fields, representatives = {}, {}, set(), {}
    def mark(label, start):
        timings[label] = time.perf_counter()-start
        if progress: progress({'phase': label, 'seconds': timings[label], 'bytes': target_db.stat().st_size})
        budget.check(True)
    try:
        budget.check(True)
        target.execute('PRAGMA cache_size=-32768')
        target.execute('PRAGMA temp_store=FILE')
        target.execute('PRAGMA journal_mode=DELETE')
        target.execute('PRAGMA synchronous=FULL')
        attach_native(target, source_db)
        metadata = {key: json.loads(raw) for key, raw in target.execute('SELECT key,value FROM native.meta')}
        if metadata.get('format') != 3 or metadata.get('complete') is not True:
            raise ValueError('Requires a complete native metadata index')
        for key, expected in (('generation', expected_generation), ('project_uuid', expected_project_uuid)):
            if expected is not None and metadata.get(key) != expected:
                raise ValueError('Native metadata generation/project mismatch')
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
                          ('source_identity',source_identity), ('format', FORMAT),
                          ('generation', metadata['generation']), ('project_uuid', metadata['project_uuid'])]:
            target.execute('INSERT INTO typed_receipt VALUES (?,?)',(key,canonical(value)))
        target.commit();mark('core_equality_proof_seconds',start)
        start=time.perf_counter();target.execute('ANALYZE main');target.commit()
        mark('analyze_seconds',start)
        start=time.perf_counter()
        if target.execute('PRAGMA main.quick_check').fetchone()[0]!='ok':raise ValueError('Sidecar quick_check failed')
        counts={table:target.execute(f'SELECT COUNT(*) FROM native.{table}').fetchone()[0] for table in ORIGINAL_TABLES}
        if source_identity != _signature(source_db):
            raise ValueError('Source file stat changed')
        mark('quick_check_and_counts_seconds',start)
        target.execute('INSERT INTO typed_receipt VALUES (?,?)', ('complete', 'true'))
        target.commit()
        target.close()
        seal = {'format': FORMAT, 'generation': metadata['generation'],
                'project_uuid': metadata['project_uuid'], 'sha256': file_sha(target_db)}
        if source_identity != _signature(source_db):
            raise ValueError('Source changed while sealing typed index')
        with open(str(target_db)+'.sha256.json', 'x') as stream:
            stream.write(canonical(seal)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return {'source':str(source_db),'target':str(target_db),'build_seconds':sum(timings.values()),
                'wall_seconds':time.perf_counter()-budget.started,'timings':timings,'added_bytes':target_db.stat().st_size,
                'original_bytes':source_stat.st_size,'dictionary_kinds':kinds,'core_safe':core_safe,
                'wide_numeric_fields':sorted(wide_fields),'native_table_counts':counts,
                'packaging':'shared immutable source plus typed auxiliary sidecar; no source clone',
                'source_stat_unchanged':True,'max_rss_bytes':_rss_bytes(),
                'source_full_sha256_verification':'separate parent-owned preservation phase',
                'validation_representatives':'actual values covering every observed kind and array-element kind',
                'no_detail_materialization':True,'all_passed':True}
    except sqlite3.OperationalError:
        if budget.reason:
            raise RuntimeError(budget.reason) from None
        raise
    finally:target.close()


class TypedMetadataIndex(_TypedQueries):
    """Thread-confined reader over one caller-verified immutable native base.

    Ranks are backend continuation positions, not public cursors. Service code
    must bind them to generation_token, scope, predicate and annotation state.
    Group results cover nonempty members; preserve empty native branches in the
    service adapter. Explicit membership() materializes a list; prefer iteration.
    """
    def __init__(self, db_path, source_path=None, *, expected_generation=None,
                 expected_project_uuid=None, cancel_check=None, _verified_reader=None):
        if Path(db_path).is_symlink():
            raise ValueError('Typed indexes cannot use symbolic links')
        self.path=Path(db_path).resolve()
        self._closed = False
        self._cancel_event = threading.Event()
        self._cancel_callback = cancel_check
        self._signature = _signature(self.path)
        self._seal_path = Path(str(self.path)+'.sha256.json')
        self._seal_signature = _signature(self._seal_path)
        seal = json.loads(self._seal_path.read_text())
        if self._seal_signature != _signature(self._seal_path):
            raise ValueError('Typed seal changed during verification')
        if _verified_reader is not None:
            if not isinstance(_verified_reader, TypedMetadataIndex):
                raise ValueError('Verified open requires an existing typed reader')
            _verified_reader._check()
            if (self.path != _verified_reader.path or self._signature != _verified_reader._signature
                    or seal != _verified_reader._seal):
                raise ValueError('Verified typed reader belongs to a different asset')
        elif file_sha(self.path) != seal.get('sha256'):
            raise ValueError('Typed index seal mismatch')
        if seal.get('format') != FORMAT:
            raise ValueError('Typed index seal mismatch')
        self._seal = copy.deepcopy(seal)
        self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            self._open(source_path, expected_generation, expected_project_uuid, seal)
            if _verified_reader is not None:
                _verified_reader._check()
                if (self.source_path != _verified_reader.source_path
                        or self._source_signature != _verified_reader._source_signature):
                    raise ValueError('Verified reader belongs to another native source')
        except BaseException:
            self.connection.close()
            self._closed = True
            raise

    @classmethod
    def open_verified(cls, verified_reader, *, cancel_check=None):
        """Open a thread-owned connection from a live default-verified reader.

        No independent user-supplied signature is trusted. Both files and the
        seal must still match the verified reader before and after opening.
        The lifecycle adapter must retain the native-generation reader lease.
        """
        if not isinstance(verified_reader, cls):
            raise ValueError('Verified open requires an existing typed reader')
        verified_reader._check()
        return cls(verified_reader.path, verified_reader.source_path,
                   expected_generation=verified_reader.generation,
                   expected_project_uuid=verified_reader.project_uuid,
                   cancel_check=cancel_check, _verified_reader=verified_reader)

    def _open(self, source_path, expected_generation, expected_project_uuid, seal):
        self.connection.execute('PRAGMA cache_size=-32768')
        self.connection.execute('PRAGMA temp_store=FILE')
        receipts={key:json.loads(raw) for key,raw in self.connection.execute('SELECT key,value_json FROM typed_receipt')}
        if receipts.get('complete') is not True or receipts.get('format') != FORMAT:
            raise ValueError('Incomplete or incompatible typed metadata index')
        for key, expected in (('generation', expected_generation), ('project_uuid', expected_project_uuid)):
            if receipts[key] != seal.get(key) or (expected is not None and receipts[key] != expected):
                raise ValueError('Typed metadata generation/project mismatch')
        if source_path is not None and Path(source_path).is_symlink():
            raise ValueError('Native indexes cannot use symbolic links')
        bound_source=Path(source_path or receipts['source_path']).resolve()
        if receipts['source_identity'] != _signature(bound_source):
            raise ValueError('Typed sidecar belongs to a different native database generation')
        self.source_path = bound_source
        self._source_signature = receipts['source_identity']
        self.generation, self.project_uuid = receipts['generation'], receipts['project_uuid']
        self.generation_token = hashlib.sha256(canonical({
            'generation': self.generation, 'project_uuid': self.project_uuid,
            'source_identity': self._source_signature, 'typed_sha256': seal['sha256'],
            'format': FORMAT}).encode()).hexdigest()
        attach_native(self.connection,bound_source)
        self.connection.execute('CREATE TEMP TABLE supplied_scope(epoch_id INTEGER PRIMARY KEY)')
        self.connection.execute('CREATE TEMP TABLE supplied_sources(source_sha TEXT PRIMARY KEY)')
        self.connection.execute('CREATE TEMP TABLE dictionary_matches(match_no INTEGER,value_id INTEGER,PRIMARY KEY(match_no,value_id)) WITHOUT ROWID')
        self._dictionary_match_no = 0
        self.fields=dict(self.connection.execute('SELECT field_id,field_no FROM fields'))
        self.definitions=[json.loads(raw) for raw, in self.connection.execute('SELECT definition_json FROM fields ORDER BY field_no')]
        self.wide_fields=set(receipts['wide_numeric_fields']);self.core_safe=receipts['core_safe']
        self.core_string_fields={field for field,safe in self.core_safe.items() if safe}
        self.validation_representatives=receipts['validation_representatives']
        self.decoder=Decoder()
        self.connection.set_progress_handler(lambda: int(self._cancel_requested()), 10000)
        self._check()

    def _check(self):
        if self._closed:
            raise ValueError('Typed metadata index is closed')
        if self._cancel_requested():
            raise QueryCancelled('Typed metadata query cancelled')
        if (self._signature != _signature(self.path) or self._source_signature != _signature(self.source_path)
                or self._seal_signature != _signature(self._seal_path)):
            raise ValueError('Typed metadata generation changed; reopen verified indexes')

    def _cancel_requested(self):
        return self._cancel_event.is_set() or bool(self._cancel_callback and self._cancel_callback())

    def cancel(self):
        """May be called by another thread; use one reader per owned operation."""
        self._cancel_event.set()
        if not self._closed:
            self.connection.interrupt()

    def set_cancel_callback(self, callback=None):
        """Install an Event.is_set-style callback on the reader's owning thread."""
        self._cancel_callback = callback

    def reset_cancel(self):
        self._cancel_event.clear()

    def close(self):
        if not self._closed:
            self.decoder.clear()
            self.connection.close()
            self._closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *error):
        self.close()

    @_guard
    def field_registry(self):
        """Complete definitions and observed kinds without value distributions."""
        fields = copy.deepcopy(self.definitions)
        for field in fields:
            observed = self.validation_representatives.get(str(self.fields[field['id']]), {})
            field['types'] = sorted(key for key in observed if not key.startswith('array_element:'))
        return {'fields': fields, 'operators': list(predicates.OPERATORS),
                'predicate_version': 1, 'generation_token': self.generation_token,
                'limits': {'max_depth': predicates.MAX_DEPTH, 'max_nodes': predicates.MAX_NODES,
                           'max_choices': predicates.MAX_CHOICES}}
    def _validate(self,predicate):
        referenced=set()
        stack = [(predicate, 0)]
        visited = 0
        while stack and visited <= predicates.MAX_NODES:
            node, depth = stack.pop()
            visited += 1
            if not isinstance(node, dict) or depth > predicates.MAX_DEPTH:
                continue
            if 'all' in node or 'any' in node:
                items=node.get('all',node.get('any',[]))
                if isinstance(items,list):
                    stack.extend((child, depth+1) for child in items[:predicates.MAX_NODES+1])
            elif 'not' in node:stack.append((node['not'], depth+1))
            elif isinstance(node.get('field'),str):referenced.add(node['field'])
        outer=self
        class Representatives:
            def values(self):
                for field in referenced:
                    number=outer.fields.get(field)
                    for raw in set(outer.validation_representatives.get(str(number),{}).values()):
                        yield {field:json.loads(raw)}
        return predicates.validate(predicate,{'fields':self.definitions},Representatives())
    def iter_membership(self,predicate=None,scope=None):
        self._check()
        where,arguments=self._where(predicate,scope)
        try:
            for number, (identity,) in enumerate(self.connection.execute(
                    'SELECT c.epoch_uuid FROM typed_core c WHERE '+where+' ORDER BY c.sort_rank', arguments)):
                if number % 2000 == 0:
                    self._check()
                yield identity
            self._check()
        except sqlite3.OperationalError:
            if self._cancel_requested():
                raise QueryCancelled('Typed metadata query cancelled') from None
            raise

    @_guard
    def count(self, predicate=None, scope=None):
        where, arguments = self._where(predicate, scope)
        return self.connection.execute('SELECT COUNT(*) FROM typed_core c WHERE '+where, arguments).fetchone()[0]

    def _validate_facets(self, fields):
        if not isinstance(fields, (list, tuple)) or any(not isinstance(f, str) for f in fields):
            raise ValueError('Facet fields must be an array of native field IDs')
        if len(set(fields)) != len(fields):
            raise ValueError('Facet fields must be unique native fields')
        if any(f not in self.fields for f in fields):
            raise ValueError('Unknown native facet field')

    def _page(self,where,arguments,cursor=None,limit=60):
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Page limit must be 1..100')
        cursor_sql='';cursor_args=[]
        if cursor is not None:
            if type(cursor) is not int or cursor<1:
                raise ValueError('Cursor must be a chronology rank')
            cursor_sql=' AND c.sort_rank>?';cursor_args=[cursor]
        # MATERIALIZED is intentional: choosing IDs must finish before joining
        # wide native row_json, otherwise broad predicates read hundreds of
        # thousands of JSON payloads only to return sixty rows.
        sql=('WITH page_ids AS MATERIALIZED ('
             'SELECT c.epoch_id,c.sort_rank FROM typed_core c WHERE '+where+cursor_sql+
             ' ORDER BY c.sort_rank LIMIT ?) '
             'SELECT p.sort_rank,e.row_json FROM page_ids p JOIN epochs e USING(epoch_id) ORDER BY p.sort_rank')
        fetched=self.connection.execute(sql,arguments+cursor_args+[limit+1]).fetchall()
        page=fetched[:limit]
        return dict(rows=[json.loads(raw) for _,raw in page],cursor=page[-1][0] if len(fetched)>limit else None)


    def _summaries(self, where, arguments, facet_fields, selective):
        count = self.connection.execute('SELECT COUNT(*) FROM typed_core c WHERE '+where, arguments).fetchone()[0]
        facets = {}
        for field in facet_fields:
            number = self.fields[field]
            if selective:
                joined = ('FROM typed_core c CROSS JOIN epoch_values ev '
                          'ON ev.epoch_id=c.epoch_id AND ev.field_no=? '
                          'JOIN typed_values v USING(value_id) WHERE ('+where+') ')
                present_sql = ('SELECT COUNT(*) FROM typed_core c CROSS JOIN epoch_values ev '
                               'ON ev.epoch_id=c.epoch_id AND ev.field_no=? WHERE ('+where+')')
            else:
                joined = ('FROM typed_core c JOIN epoch_values ev USING(epoch_id) '
                          'JOIN typed_values v USING(value_id) WHERE ev.field_no=? AND ('+where+') ')
                present_sql = ('SELECT COUNT(*) FROM typed_core c JOIN epoch_values ev USING(epoch_id) '
                               'WHERE ev.field_no=? AND ('+where+')')
            buckets = self.connection.execute('SELECT v.value_json,v.kind,COUNT(*),MIN(c.sort_rank) '+
                joined+'GROUP BY v.equality_json ORDER BY MIN(c.sort_rank) LIMIT 61',
                [number]+arguments).fetchall()
            present = self.connection.execute(present_sql, [number]+arguments).fetchone()[0]
            facets[field] = {
                'values': [{'value': json.loads(raw), 'type': kind, 'count': n}
                           for raw, kind, n, _ in buckets[:60]],
                'missing_count': count-present, 'present_count': present,
                'values_truncated': len(buckets)>60}
        return {'count': count, 'facets': facets}

    @_guard
    def summaries(self, predicate=None, scope=None, facet_fields=()):
        """Exact count and requested facets without decoding row/detail DTOs."""
        self._validate_facets(facet_fields)
        where, arguments = self._where(predicate, scope)
        selective = isinstance(scope, dict) and bool(set(scope)&{'cell','block','group'})
        return self._summaries(where, arguments, facet_fields, selective)

    @_guard
    def preview(self, predicate=None, scope=None, facet_fields=(), limit=60, cursor=None):
        self._validate_facets(facet_fields)
        where, arguments = self._where(predicate, scope)
        selective = isinstance(scope, dict) and bool(set(scope)&{'cell','block','group'})
        result = self._summaries(where, arguments, facet_fields, selective)
        return {**result, **self._page(where, arguments, cursor, limit)}

    @_guard
    def page(self, predicate=None, scope=None, cursor=None, limit=60):
        return super().page(predicate, scope, cursor, limit)

    @_guard
    def groups(self, kind='cell', predicate=None, scope=None, cursor=None, limit=60):
        return super().groups(kind, predicate, scope, cursor, limit)

    @_guard
    def detail(self, epoch_uuid):
        return super().detail(epoch_uuid)

    @_guard
    def membership(self, predicate=None, scope=None):
        """Explicit eager compatibility operation; prefer iter_membership()."""
        return super().membership(predicate, scope)

    @_guard
    def explain(self, predicate=None, scope=None):
        return super().explain(predicate, scope)

    def _where(self,predicate=None,scope=None):
        self._check()
        previous=getattr(self,'_structurally_scoped',False)
        self._structurally_scoped=isinstance(scope,dict) and bool(set(scope)&{'cell','block','group'})
        try:
            return super()._where(predicate,scope)
        finally:
            self._structurally_scoped=previous


    def _leaf(self,node):
        sql,arguments=super()._leaf(node)
        if not getattr(self,'_structurally_scoped',False):
            return sql,arguments
        exists='c.epoch_id IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)'
        missing='c.epoch_id NOT IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)'
        local='EXISTS (SELECT 1 FROM epoch_values ev WHERE ev.epoch_id=c.epoch_id AND ev.field_no=?)'
        if sql==exists:return local,arguments
        if sql==missing:return 'NOT '+local,arguments
        prefix=('c.epoch_id IN (SELECT ev.epoch_id FROM typed_values v JOIN epoch_values ev '
                'ON ev.field_no=v.field_no AND ev.value_id=v.value_id WHERE v.field_no=? AND (')
        if sql.startswith(prefix) and sql.endswith('))'):
            selector=sql[len(prefix):-2]
            # Fix loop order to first point-read the selected epoch/field entry,
            # then its globally unique dictionary value. A tiny parent scope
            # must never enumerate project-wide metadata membership first.
            sql=('EXISTS (SELECT 1 FROM epoch_values ev CROSS JOIN typed_values v '
                 'ON ev.field_no=v.field_no AND ev.value_id=v.value_id '
                 'WHERE ev.epoch_id=c.epoch_id AND ev.field_no=? AND ('+selector+'))')
        return sql,arguments
