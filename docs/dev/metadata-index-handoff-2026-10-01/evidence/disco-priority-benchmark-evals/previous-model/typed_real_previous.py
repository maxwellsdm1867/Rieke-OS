"""Disposable adaptation of the previous typedSQLite experiment to real metadata.

No new dependency, no production writes, and no additional raw metadata discovery.
All seven original tables, JSON values, compressed details and ancestor identities
remain byte-for-byte unchanged. Typed scalar dictionaries are auxiliary indexes.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import sys

NATIVE = Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
import workspace_predicates as predicates
from workspace_metadata_objects import Decoder

ORIGINAL_TABLES = ('meta', 'epochs', 'fields', 'field_values', 'epoch_values', 'sources', 'metadata_objects')
CORE_COLUMNS = ('epoch_uuid', 'source_sha256', 'cell_uuid', 'block_uuid', 'group_uuid',
                'protocol_name', 'date', 'start_time', 'block_start_time', 'epoch_number',
                'duration_seconds', 'cell_label', 'cell_type', 'group_label')
CORE_FIELDS = {'epoch': 'epoch_uuid', 'cell': 'cell_uuid', 'block': 'block_uuid',
               'group': 'group_uuid', 'protocol': 'protocol_name', 'date': 'date',
               'cell type': 'cell_type', 'group label': 'group_label', 'block time': 'block_start_time'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def file_sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def equality_json(value):
    """Canonical equal() identity, including nested int/float merges.

    Ratios preserve exact Python numeric equality; boolean has its own type.
    Original JSON is retained separately and is always used for returned values.
    """
    kind = predicates.kind(value)
    if kind == 'number':
        numerator, denominator = (value, 1) if type(value) is int else value.as_integer_ratio()
        return canonical(['number', str(numerator), str(denominator)])
    if kind == 'array':
        return canonical(['array', [equality_json(item) for item in value]])
    if kind == 'object':
        return canonical(['object', [[key, equality_json(value[key])] for key in sorted(value)]])
    return canonical([kind, value])


def table_digest(connection, table):
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1,2'):
        encoded = canonical([{'blob_sha256': hashlib.sha256(item).hexdigest(), 'blob_bytes': len(item)}
                             if isinstance(item, bytes) else item for item in row]).encode()
        digest.update(len(encoded).to_bytes(8, 'big'))
        digest.update(encoded)
        count += 1
    return dict(rows=count, sha256=digest.hexdigest())


def build(source_db, target_db):
    """Clone source, then add generic typed columns/indexes without decoding detail."""
    started = time.perf_counter()
    source_db, target_db = Path(source_db), Path(target_db)
    if source_db.resolve() == target_db.resolve() or target_db.exists():
        raise ValueError('Build requires a new isolated destination')
    before = file_sha(source_db)
    source = sqlite3.connect(source_db.as_uri() + '?mode=ro&immutable=1', uri=True)
    target_db.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(target_db)
    try:
        source.backup(target)
        clone_seconds = time.perf_counter() - started
        target.executescript('''
            PRAGMA cache_size=-32768;
            PRAGMA temp_store=FILE;
            CREATE TABLE typed_core(
                epoch_id INTEGER PRIMARY KEY,sort_rank INTEGER NOT NULL UNIQUE,epoch_uuid TEXT NOT NULL UNIQUE,
                source_sha256 TEXT,cell_uuid TEXT,block_uuid TEXT,group_uuid TEXT,
                protocol_name TEXT,date TEXT,start_time TEXT,block_start_time TEXT,
                epoch_number INTEGER,duration_seconds REAL,cell_label TEXT,cell_type TEXT,group_label TEXT);
            CREATE TABLE typed_values(
                value_id INTEGER PRIMARY KEY,field_no INTEGER NOT NULL,
                kind TEXT NOT NULL,numeric_value,numeric_class TEXT,text_value TEXT,
                equality_json TEXT NOT NULL,value_json TEXT NOT NULL);
            CREATE INDEX typed_numeric ON typed_values(field_no,kind,numeric_value,value_id);
            CREATE INDEX typed_text ON typed_values(field_no,kind,text_value,value_id);
            CREATE INDEX typed_equality ON typed_values(field_no,equality_json,value_id);
            CREATE INDEX typed_kind ON typed_values(field_no,kind,value_id);
            CREATE INDEX typed_chronology ON typed_core(date,start_time,epoch_uuid);
            CREATE INDEX typed_cell_children ON typed_core(cell_uuid,sort_rank);
            CREATE INDEX typed_block_children ON typed_core(block_uuid,sort_rank);
            CREATE INDEX typed_group_children ON typed_core(group_uuid,sort_rank);
            CREATE INDEX typed_protocol_children ON typed_core(protocol_name,sort_rank);
        ''')
        wide_fields = set()
        for sort_rank, (epoch_id, raw) in enumerate(source.execute("SELECT epoch_id,row_json FROM epochs ORDER BY COALESCE(json_extract(row_json,'$.date'),''),COALESCE(json_extract(row_json,'$.start_time'),''),epoch_uuid"), 1):
            row = json.loads(raw)
            target.execute('INSERT INTO typed_core VALUES (' + ','.join('?' for _ in range(16)) + ')',
                           [epoch_id, sort_rank] + [row.get(name) for name in CORE_COLUMNS])
        kinds = {}
        for value_id, field_no, raw in source.execute('SELECT value_id,field_no,value_json FROM field_values ORDER BY value_id'):
            value = json.loads(raw)
            kind = predicates.kind(value)
            kinds[kind] = kinds.get(kind, 0) + 1
            numeric = None
            numeric_class = None
            text = value if kind == 'string' else None
            if kind == 'number':
                numeric_class = 'integer' if type(value) is int else 'float'
                if type(value) is int and abs(value) > 2**53 - 1:
                    # Every numeric predicate in such fields uses the exact
                    # dictionary fallback. No implicit float conversion.
                    numeric_class = 'wide_integer'
                    wide_fields.add(field_no)
                else:
                    numeric = value
            target.execute('INSERT INTO typed_values VALUES (?,?,?,?,?,?,?,?)',
                           (value_id, field_no, kind, numeric, numeric_class, text, equality_json(value), raw))
        # Check all direct fields against native values before enabling shortcuts.
        core_safe = {}
        for field, column in CORE_FIELDS.items():
            number = source.execute('SELECT field_no FROM fields WHERE field_id=?', (field,)).fetchone()
            if number is None:
                continue
            expected = target.execute(f'SELECT c.epoch_id,c.{column},v.value_json FROM typed_core c '
                'LEFT JOIN epoch_values ev ON c.epoch_id=ev.epoch_id AND ev.field_no=? '
                'LEFT JOIN field_values v USING(value_id)', number)
            core_safe[field] = all(raw is not None and predicates.kind(value)=='string' and predicates.equal(value, json.loads(raw))
                                   for _, value, raw in expected)
        target.execute('CREATE TABLE typed_receipt(key TEXT PRIMARY KEY,value_json TEXT NOT NULL)')
        for key, value in [('wide_numeric_fields', sorted(wide_fields)), ('core_safe', core_safe)]:
            target.execute('INSERT INTO typed_receipt VALUES (?,?)', (key, canonical(value)))
        target.commit()
        target.execute('ANALYZE')
        target.commit()
        assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        preservation = {}
        for table in ORIGINAL_TABLES:
            original = table_digest(source, table)
            copied = table_digest(target, table)
            assert original == copied, f'Original table changed: {table}'
            preservation[table] = original
        after = file_sha(source_db)
        assert before == after
        return dict(source=str(source_db), target=str(target_db), input_sha256_before=before,
                    input_sha256_after=after, clone_seconds=clone_seconds,
                    build_and_verify_seconds=time.perf_counter()-started,
                    original_bytes=source_db.stat().st_size, indexed_bytes=target_db.stat().st_size,
                    added_bytes=target_db.stat().st_size-source_db.stat().st_size,
                    original_tables=preservation, dictionary_kinds=kinds,
                    core_safe=core_safe, wide_numeric_fields=sorted(wide_fields),
                    no_detail_materialization=True, original_query_eligibility_unchanged=True,
                    original_pattern=['typed core columns','UUID lookup','chronology and parent indexes','bounded page and facets'],
                    generic_adaptation=['typed scalar dictionary for every original native field',
                        'exact recursive array/object equality keys','int/float numeric equivalence',
                        'wide integer exact dictionary fallback','all seven native detail and ancestor tables retained'])
    finally:
        source.close()
        target.close()


class TypedReal:
    def __init__(self, db_path):
        self.path = Path(db_path).resolve()
        self.connection = sqlite3.connect(self.path.as_uri() + '?mode=ro&immutable=1', uri=True)
        self.connection.execute('PRAGMA cache_size=-32768')
        self.connection.execute('PRAGMA temp_store=FILE')
        self.connection.execute('CREATE TEMP TABLE supplied_scope(epoch_id INTEGER PRIMARY KEY)')
        self.fields = dict(self.connection.execute('SELECT field_id,field_no FROM fields'))
        self.definitions = [json.loads(raw) for raw, in self.connection.execute('SELECT definition_json FROM fields ORDER BY field_no')]
        receipts = {key: json.loads(raw) for key, raw in self.connection.execute('SELECT key,value_json FROM typed_receipt')}
        self.wide_fields = set(receipts['wide_numeric_fields'])
        self.core_safe = receipts['core_safe']
        # Builder's core_safe proof covers presence, exact equality and string
        # kind in every row. Recheck auxiliary dictionary kinds once at open;
        # predicate validation may then use one string representative.
        self.core_string_fields = set()
        for field, safe in self.core_safe.items():
            if safe:
                invalid = self.connection.execute(
                    "SELECT 1 FROM typed_values WHERE field_no=? AND kind<>'string' LIMIT 1",
                    [self.fields[field]]).fetchone()
                if invalid is not None:
                    raise ValueError('Safe core field contains a non-string value')
                self.core_string_fields.add(field)
        self.decoder = Decoder()

    def close(self):
        self.decoder.clear()
        self.connection.close()

    def _validate(self, predicate):
        referenced = set()
        def collect(node):
            if 'all' in node or 'any' in node:
                for child in node.get('all', node.get('any', [])):
                    collect(child)
            elif 'not' in node:
                collect(node['not'])
            elif 'field' in node:
                referenced.add(node['field'])
        collect(predicate)
        connection = self.connection
        class Representatives:
            def values(self):
                for field in referenced:
                    number = self_outer.fields.get(field)
                    if number is None:
                        continue
                    if field in self_outer.core_string_fields:
                        yield {field: ''}
                        continue
                    for raw, in connection.execute('SELECT value_json FROM typed_values WHERE field_no=?', (number,)):
                        yield {field: json.loads(raw)}
        self_outer = self
        return predicates.validate(predicate, {'fields': self.definitions}, Representatives())

    def _leaf(self, node):
        field, op = node['field'], node['operator']
        number = self.fields[field]
        column = CORE_FIELDS.get(field)
        if column and self.core_safe.get(field) and op in {'eq', 'exists', 'missing', 'is_null'}:
            if op == 'exists':
                return '1', []
            if op in {'missing', 'is_null'}:
                return '0', []
            if predicates.kind(node['value']) == 'string':
                return f'c.{column}=?', [node['value']]
        if op == 'missing':
            return 'c.epoch_id NOT IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)', [number]
        if op == 'exists':
            return 'c.epoch_id IN (SELECT epoch_id FROM epoch_values WHERE field_no=?)', [number]
        selector, arguments = '', [number]
        if op == 'is_null':
            selector = "v.kind='null'"
        elif op in {'eq','ne','in','not_in'}:
            choices = node['value'] if op in {'in','not_in'} else [node['value']]
            selector = 'v.equality_json IN (' + ','.join('?' for _ in choices) + ')' if choices else '0'
            arguments.extend(equality_json(value) for value in choices)
            if op in {'ne','not_in'}:
                selector = 'NOT (' + selector + ')'
        elif op in {'gt','gte','lt','lte'} and number not in self.wide_fields:
            selector = "v.kind='number' AND v.numeric_value " + {'gt':'>','gte':'>=','lt':'<','lte':'<='}[op] + ' ?'
            arguments.append(node['value'])
        else:
            # Contains and wide-int range comparisons are evaluated only on the
            # small native dictionary, never by materializing per-epoch DTOs.
            matches = [value_id for value_id, raw in self.connection.execute(
                'SELECT value_id,value_json FROM typed_values WHERE field_no=?', [number])
                if predicates.matches(node, {field: json.loads(raw)})]
            selector = 'v.value_id IN (' + ','.join('?' for _ in matches) + ')' if matches else '0'
            arguments.extend(matches)
        return ('c.epoch_id IN (SELECT ev.epoch_id FROM typed_values v JOIN epoch_values ev '
                'ON ev.field_no=v.field_no AND ev.value_id=v.value_id WHERE v.field_no=? AND (' + selector + '))'), arguments

    def _compile(self, node):
        for group, operator, empty in [('all',' AND ','1'),('any',' OR ','0')]:
            if group in node:
                compiled = [self._compile(child) for child in node[group]]
                return '(' + operator.join(sql for sql, _ in compiled) + ')' if compiled else empty, [a for _, args in compiled for a in args]
        if 'not' in node:
            sql, arguments = self._compile(node['not'])
            return 'NOT (' + sql + ')', arguments
        return self._leaf(node)

    def predicate_sql(self, predicate):
        return ('1', []) if predicate is None else self._compile(self._validate(predicate))

    def _where(self, predicate=None, scope=None):
        sql, arguments = self.predicate_sql(predicate)
        if isinstance(scope, dict):
            allowed = {'protocol','cell','block','group'}
            if set(scope) - allowed:
                raise ValueError('Unknown direct scope field')
            for field, value in scope.items():
                part, params = self.predicate_sql({'field':field,'operator':'eq','value':value})
                sql += ' AND (' + part + ')'
                arguments.extend(params)
        elif scope is not None:
            self.connection.execute('DELETE FROM supplied_scope')
            self.connection.executemany('INSERT OR IGNORE INTO supplied_scope SELECT epoch_id FROM epochs WHERE epoch_uuid=?', [(identity,) for identity in scope])
            sql += ' AND c.epoch_id IN (SELECT epoch_id FROM supplied_scope)'
        return sql, arguments

    def membership(self, predicate=None, scope=None):
        where, arguments = self._where(predicate, scope)
        return [identity for identity, in self.connection.execute('SELECT c.epoch_uuid FROM typed_core c WHERE ' + where + ' ORDER BY c.sort_rank', arguments)]

    def _page(self, where, arguments, cursor=None, limit=60):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Page limit must be 1..100')
        cursor_sql, cursor_args = '', []
        if cursor is not None:
            if type(cursor) is not int or cursor < 1:
                raise ValueError('Cursor must be a chronology rank')
            cursor_sql, cursor_args = ' AND c.sort_rank>?', [cursor]
        fetched = self.connection.execute('SELECT c.sort_rank,e.row_json FROM typed_core c JOIN epochs e USING(epoch_id) WHERE ' + where + cursor_sql + ' ORDER BY c.sort_rank LIMIT ?', arguments + cursor_args + [limit+1]).fetchall()
        page = fetched[:limit]
        return dict(rows=[json.loads(raw) for _, raw in page], cursor=page[-1][0] if len(fetched)>limit else None)

    def page(self, predicate=None, scope=None, cursor=None, limit=60):
        where, arguments = self._where(predicate, scope)
        return self._page(where, arguments, cursor, limit)

    def preview(self, predicate=None, scope=None, facet_fields=(), limit=60, cursor=None):
        if len(facet_fields)>140 or len(set(facet_fields)) != len(facet_fields):
            raise ValueError('Facet fields must be unique native fields')
        where, arguments = self._where(predicate, scope)
        count = self.connection.execute('SELECT COUNT(*) FROM typed_core c WHERE ' + where, arguments).fetchone()[0]
        page = self._page(where, arguments, cursor, limit)
        facets = {}
        for field in facet_fields:
            if field not in self.fields:
                raise ValueError('Unknown native facet field')
            number = self.fields[field]
            # One min() aggregate makes bare value_json come from the first
            # epoch carrying each semantic value. No epoch detail is decoded.
            query = ('SELECT v.value_json,v.kind,COUNT(*),MIN(c.sort_rank) '
                     'FROM typed_core c JOIN epoch_values ev USING(epoch_id) JOIN typed_values v USING(value_id) '
                     'WHERE ev.field_no=? AND (' + where + ') '
                     'GROUP BY v.equality_json ORDER BY MIN(c.sort_rank) LIMIT 61')
            buckets = self.connection.execute(query, [number]+arguments).fetchall()
            present = self.connection.execute('SELECT COUNT(*) FROM typed_core c JOIN epoch_values ev USING(epoch_id) WHERE ev.field_no=? AND (' + where + ')', [number]+arguments).fetchone()[0]
            facets[field] = dict(values=[dict(value=json.loads(raw),type=kind,count=n) for raw, kind, n, _ in buckets[:60]],
                                 missing_count=count-present,present_count=present,values_truncated=len(buckets)>60)
        return dict(count=count, **page, facets=facets)

    def detail(self, epoch_uuid):
        record = self.connection.execute('SELECT row_json,detail_blob FROM epochs WHERE epoch_uuid=?', [epoch_uuid]).fetchone()
        if record is None:
            raise KeyError(epoch_uuid)
        return self.decoder.decode(self.connection, json.loads(record[0]), record[1])

    def groups(self, kind='cell', predicate=None, scope=None, cursor=None, limit=60):
        if kind not in {'cell','block'} or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Unsupported bounded group query')
        column = kind + '_uuid'
        where, arguments = self._where(predicate, scope)
        if kind == 'cell':
            if cursor is not None:
                if not isinstance(cursor,str):
                    raise ValueError('Cell group cursor must be a UUID')
                where += f' AND c.{column}>?'
                arguments.append(cursor)
            result = self.connection.execute(f'SELECT c.{column},COUNT(*) FROM typed_core c WHERE ' + where + f' GROUP BY c.{column} ORDER BY c.{column} LIMIT ?', arguments+[limit+1]).fetchall()
            page = result[:limit]
            return dict(groups=[dict(uuid=identity,count=n) for identity,n in page],cursor=page[-1][0] if len(result)>limit else None)
        # Previous typed prototype orders blocks by their recorded start time,
        # then UUID, and applies the cursor after grouping all matched members.
        grouped = ("SELECT c.block_uuid AS uuid,COUNT(*) AS n,MIN(COALESCE(c.block_start_time,'')) AS start_time "
                   'FROM typed_core c WHERE ' + where + ' GROUP BY c.block_uuid')
        post_where = ''
        if cursor is not None:
            if (not isinstance(cursor,dict) or set(cursor)!={'start_time','key'}
                    or not all(isinstance(value,str) for value in cursor.values())):
                raise ValueError('Block cursor requires start_time and key strings')
            post_where = ' WHERE (start_time,uuid)>(?,?)'
            arguments.extend([cursor['start_time'],cursor['key']])
        result = self.connection.execute('SELECT uuid,n,start_time FROM (' + grouped + ')' + post_where + ' ORDER BY start_time,uuid LIMIT ?', arguments+[limit+1]).fetchall()
        page = result[:limit]
        next_cursor = {'start_time':page[-1][2],'key':page[-1][0]} if len(result)>limit else None
        return dict(groups=[dict(uuid=identity,count=n) for identity,n,_ in page],cursor=next_cursor)

    def explain(self, predicate=None, scope=None):
        where, arguments = self._where(predicate, scope)
        return [list(row) for row in self.connection.execute('EXPLAIN QUERY PLAN SELECT c.epoch_uuid FROM typed_core c WHERE ' + where + ' ORDER BY c.sort_rank LIMIT 60', arguments)]
