"""Experimental bounded SQL read model; neither engine owns annotations.

The typed SQLite and DuckDB arms consume exactly the same streaming CSV and
execute the same query semantics. This module is not a production replacement.
"""
from __future__ import annotations

import csv
import datetime
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


CORE = [('epoch_uuid', 'VARCHAR'), ('source_sha256', 'VARCHAR'),
        ('protocol_uuid', 'VARCHAR'), ('date', 'VARCHAR'),
        ('cell_uuid', 'VARCHAR'), ('cell_label', 'VARCHAR'),
        ('block_uuid', 'VARCHAR'), ('block_label', 'VARCHAR'),
        ('epoch_number', 'BIGINT'), ('start_time', 'VARCHAR'),
        ('duration_seconds', 'DOUBLE'), ('metadata_hash', 'VARCHAR'),
        ('group_uuid', 'VARCHAR'), ('group_label', 'VARCHAR'),
        ('cell_type', 'VARCHAR'), ('block_start_time', 'VARCHAR'),
        ('protocol_name', 'VARCHAR'), ('synthetic_index', 'BIGINT')]
PARAMS = [('contrast', 'DOUBLE'), ('seed', 'BIGINT'),
          ('stimTime', 'BIGINT'), ('currentMean', 'BIGINT')]
SCHEMA = CORE + [(name + suffix, typ) for name, value_type in PARAMS
                 for suffix, typ in [('', value_type), ('_present', 'BOOLEAN'),
                                     ('_kind', 'VARCHAR')]]
NAMES = [name for name, _ in SCHEMA]
PROTOCOL_UUID = str(uuid.UUID(bytes=hashlib.sha256(b'-2').digest()[:16]))
PROJECT_UUID = str(uuid.UUID(bytes=hashlib.sha256(b'-1').digest()[:16]))
ORDER = ('date', 'start_time', 'epoch_uuid')
FIELDS = {name for name, _ in CORE + PARAMS}
VERSION = 1


def identity(n):
    return str(uuid.UUID(bytes=hashlib.sha256(str(n).encode()).digest()[:16]))


def fixture_row(index, epochs):
    """O(1) deterministic metadata generation; UUID namespaces never overlap."""
    cell, block = index // 100, index // 20
    start = (datetime.datetime(2026, 9, 1, 12) + datetime.timedelta(seconds=index)).strftime('%m/%d/%Y %H:%M:%S:%f')
    row = [identity(index), f'{cell % 10 + 1:064x}',
           PROTOCOL_UUID, '2026-09-01', identity(epochs + cell), f'Cell{cell}',
           identity(2 * epochs + block), start, index % 20 + 1,
           start, 1.0, 'b' * 64, identity(3 * epochs), 'Control',
           ('ON', 'OFF')[cell % 2], start, 'Synthetic', index]
    # Primary corpus exactly preserves the prior all-present fixture. Explicit
    # flags support missing/null/type edge cases tested separately.
    for name, typ in PARAMS:
        value = {'contrast': (index % 5) / 10, 'seed': index,
                 'stimTime': 1000, 'currentMean': (index % 3) * 100}[name]
        row.extend([value, 1, 'integer' if typ == 'BIGINT' else 'float'])
    return row


def generate_csv(path, epochs, progress=None):
    """Stream the one shared input, retaining only bounded expected summaries."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {name: {} for name, _ in PARAMS if name != 'seed'}
    start = time.perf_counter()
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(NAMES)
        for index in range(epochs):
            row = fixture_row(index, epochs)
            writer.writerow(row)
            for offset, (name, _) in enumerate(PARAMS):
                if name == 'seed':
                    continue
                value, present, kind = row[len(CORE) + 3 * offset:len(CORE) + 3 * offset + 3]
                key = json.dumps([bool(present), kind, value if kind not in ('missing', 'null') else None])
                counts[name][key] = counts[name].get(key, 0) + 1
            if progress and (index + 1) % 10000 == 0:
                progress(index + 1)
    receipt = {'fixture_version': VERSION, 'epochs': epochs, 'schema': SCHEMA,
               'bytes': path.stat().st_size, 'generation_seconds': time.perf_counter() - start,
               'expected_facets': counts}
    Path(str(path) + '.json').write_text(json.dumps(receipt, indent=2))
    return receipt


def _sqlite_row(row):
    result = []
    for raw, (_, typ) in zip(row, SCHEMA):
        if raw == '':
            result.append(None)
        elif typ in ('BIGINT', 'BOOLEAN'):
            result.append(int(raw))
        elif typ == 'DOUBLE':
            result.append(float(raw))
        else:
            result.append(raw)
    return result


class AnalyticalProjection:
    """Engine-specific ingestion, engine-neutral bounded query contract.

    Cursors are dictionaries of ORDER values, or a string group key. Tags are
    supplied by native-authoritative membership; this read model cannot mutate
    tags. A caller must reject stale cursors if its metadata generation changes.
    """
    def __init__(self, engine, db_path, *, threads=2, memory_limit='512MB', temp_directory=None):
        if engine not in ('sqlite', 'duckdb'):
            raise ValueError('Unknown engine')
        self.engine, self.db_path = engine, Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if engine == 'sqlite':
            self.connection = sqlite3.connect(self.db_path)
            self.connection.execute('PRAGMA cache_size=-65536')
            self.connection.execute('PRAGMA temp_store=FILE')
        else:
            import duckdb
            self.connection = duckdb.connect(str(self.db_path))
            self.connection.execute(f'SET threads={int(threads)}')
            self.connection.execute('SET memory_limit=?', [memory_limit])
            self.connection.execute("SET max_temp_directory_size='2GB'")
            temp = Path(temp_directory or self.db_path.parent / 'spill')
            temp.mkdir(parents=True, exist_ok=True)
            self.connection.execute('SET temp_directory=?', [str(temp)])
        self.lazy_rows = LazyRows(self)
        self.lazy_cells = LazyCells(self)

    def execute(self, sql, parameters=()):
        return self.connection.execute(sql, parameters)

    def rows(self, sql, parameters=()):
        cursor = self.execute(sql, parameters)
        names = [entry[0] for entry in cursor.description]
        return [{name: bool(value) if name.endswith('_present') else value
                 for name, value in zip(names, row)} for row in cursor.fetchall()]

    def build(self, csv_path, progress=None):
        phases = {}
        started = time.perf_counter()
        self.execute('CREATE TABLE epochs (' + ', '.join(f'{name} {typ}' for name, typ in SCHEMA) + ')')
        insert_start = time.perf_counter()
        if self.engine == 'duckdb':
            types = '{' + ', '.join(f"'{name}':'{typ}'" for name, typ in SCHEMA) + '}'
            self.execute(f'INSERT INTO epochs SELECT * FROM read_csv(?, header=true, columns={types}, nullstr=\'\')', [str(csv_path)])
        else:
            with open(csv_path, newline='') as handle:
                reader = csv.reader(handle)
                next(reader)
                batch, count = [], 0
                for row in reader:
                    batch.append(_sqlite_row(row))
                    if len(batch) == 2000:
                        self.connection.executemany('INSERT INTO epochs VALUES (' + ','.join('?' for _ in NAMES) + ')', batch)
                        count += len(batch)
                        batch.clear()
                        if progress:
                            progress(count)
                if batch:
                    self.connection.executemany('INSERT INTO epochs VALUES (' + ','.join('?' for _ in NAMES) + ')', batch)
            self.connection.commit()
        phases['insert_seconds'] = time.perf_counter() - insert_start
        index_start = time.perf_counter()
        # DuckDB's columnar scans are its normal grouping/filter execution;
        # SQLite needs its ordinary B-trees. Both have an exact UUID lookup.
        self.execute('CREATE UNIQUE INDEX epoch_identity ON epochs(epoch_uuid)')
        if self.engine == 'sqlite':
            for name, columns in [('chronology', 'date,start_time,epoch_uuid'),
                                  ('cell_children', 'cell_uuid,block_uuid,epoch_uuid'),
                                  ('block_children', 'block_uuid,epoch_uuid'),
                                  ('contrast_lookup', 'contrast_present,contrast_kind,contrast,date,start_time,epoch_uuid')]:
                self.execute(f'CREATE INDEX {name} ON epochs({columns})')
            self.connection.commit()
            self.execute('ANALYZE')
            self.connection.commit()
        phases['index_seconds'] = time.perf_counter() - index_start
        checkpoint_start = time.perf_counter()
        self.checkpoint()
        phases['checkpoint_seconds'] = time.perf_counter() - checkpoint_start
        phases['build_seconds'] = time.perf_counter() - started
        phases['persisted_bytes'] = self.db_path.stat().st_size
        return phases

    def checkpoint(self):
        if self.engine == 'duckdb':
            self.execute('CHECKPOINT')
        else:
            self.connection.commit()

    def close(self):
        self.connection.close()

    def _where(self, filters=None, parent=None, ids=None):
        predicates, values = [], []
        for field, value in {**(parent or {}), **(filters or {})}.items():
            if field not in FIELDS:
                raise ValueError(f'Unsupported field {field}')
            if field in dict(PARAMS):
                if isinstance(value, dict):
                    kind = value.get('kind')
                    if kind not in ('missing', 'null', 'float', 'integer', 'string'):
                        raise ValueError('Explicit parameter kind required')
                    predicates.append(f'{field}_kind=?')
                    values.append(kind)
                    if kind in ('missing', 'null'):
                        continue
                    value = value['value']
                else:
                    kind = 'integer' if type(value) is int else 'float' if type(value) is float else 'string'
                    predicates.append(f'{field}_present=1 AND {field}_kind=?')
                    values.append(kind)
            if value is None:
                predicates.append(f'{field} IS NULL')
            else:
                predicates.append(f'{field}=?')
                values.append(value)
        if ids is not None:
            ids = tuple(ids)
            if len(ids) > 100:
                raise ValueError('Membership preview is bounded to 100 supplied IDs')
            predicates.append('epoch_uuid IN (' + ','.join('?' for _ in ids) + ')' if ids else '1=0')
            values.extend(ids)
        return (' WHERE ' + ' AND '.join(predicates) if predicates else ''), values

    def page(self, limit=60, cursor=None, filters=None, parent=None, ids=None):
        if not 1 <= limit <= 100:
            raise ValueError('Page limit must be 1..100')
        where, values = self._where(filters, parent, ids)
        if cursor:
            where += (' AND ' if where else ' WHERE ') + '(date,start_time,epoch_uuid)>(?,?,?)'
            values += [cursor[name] for name in ORDER]
        data = self.rows('SELECT * FROM epochs' + where + ' ORDER BY date,start_time,epoch_uuid LIMIT ?', values + [limit + 1])
        more, data = len(data) > limit, data[:limit]
        return {'items': data, 'next_cursor': {name: data[-1][name] for name in ORDER} if more else None}

    def tree_children(self, level, parent=None, filters=None, limit=60, cursor=None):
        levels = {'date': ('date', 'date'), 'cell': ('cell_uuid', 'cell_label'),
                  'block': ('block_uuid', 'block_label')}
        if level not in levels or not 1 <= limit <= 100:
            raise ValueError('Unsupported grouping or page size')
        key, label = levels[level]
        where, values = self._where(filters, parent)
        total = self.execute(f'SELECT COUNT(DISTINCT {key}) FROM epochs' + where, values).fetchone()[0]
        if cursor is not None and level != 'block':
            where += (' AND ' if where else ' WHERE ') + f'{key}>?'
            values = values + [cursor]
        grouped = (f'SELECT {key} AS key, MIN({label}) AS label, COUNT(*) AS count, '
                   'COUNT(DISTINCT cell_uuid) AS cells, '
                   'CASE WHEN COUNT(duration_seconds)=COUNT(*) THEN SUM(duration_seconds) ELSE NULL END AS duration_seconds, '
                   'MIN(block_start_time) AS start_time FROM epochs' + where + f' GROUP BY {key}')
        if level == 'block':
            post_where = ' WHERE (start_time,key)>(?,?)' if cursor is not None else ''
            if cursor is not None:
                values = values + [cursor['start_time'], cursor['key']]
            sql = 'SELECT * FROM (' + grouped + ') groups' + post_where + ' ORDER BY start_time,key LIMIT ?'
        else:
            sql = grouped + f' ORDER BY {key} LIMIT ?'
        data = self.rows(sql, values + [limit + 1])
        more, data = len(data) > limit, data[:limit]
        next_cursor = ({'start_time': data[-1]['start_time'], 'key': data[-1]['key']}
                       if level == 'block' else data[-1]['key']) if more else None
        return {'items': data, 'total': total, 'next_cursor': next_cursor}

    def detail(self, epoch_uuid):
        data = self.rows('SELECT * FROM epochs WHERE epoch_uuid=?', [epoch_uuid])
        if not data:
            return None
        row = data[0]
        return self._detail(row)

    @staticmethod
    def _basic(row):
        return {name: row[name] for name, _ in CORE} | {'streams': []}

    @classmethod
    def _detail(cls, row):
        return cls._basic(row) | {
            'parameters': {name: row[name] for name, _ in PARAMS if row[name + '_present']},
            'parameter_states': {name: {'present': bool(row[name + '_present']),
                                      'kind': row[name + '_kind'], 'value': row[name]}
                                 for name, _ in PARAMS},
            'properties': {}, 'attributes': {},
            'metadata': {'cell': {'uuid': row['cell_uuid'], 'label': row['cell_label'],
                                 'properties': {'type': row['cell_type']}},
                         'block': {'uuid': row['block_uuid'], 'parameters': {'amp': 'Amp1'}}}}

    def facets(self, field, filters=None, limit=60):
        if field not in dict(PARAMS) or not 1 <= limit <= 100:
            raise ValueError('Unsupported facet or limit')
        where, values = self._where(filters)
        data = self.rows(f'SELECT {field}_present AS present, {field}_kind AS kind, {field} AS value, COUNT(*) AS count '
                         'FROM epochs' + where + f' GROUP BY {field}_present,{field}_kind,{field} '
                         f'ORDER BY {field}_present,{field}_kind,{field} LIMIT ?', values + [limit + 1])
        for row in data:
            row['present'] = bool(row['present'])
        return {'items': data[:limit], 'has_more': len(data) > limit}

    def preview(self, filters=None, facet_fields=('contrast', 'currentMean'), limit=60):
        where, values = self._where(filters)
        count = self.execute('SELECT COUNT(*) FROM epochs' + where, values).fetchone()[0]
        return {'count': count, **self.page(limit=limit, filters=filters),
                'facets': {field: self.facets(field, filters, limit) for field in facet_fields}}

    def tag_page(self, ids, limit=60, filters=None):
        return self.page(limit=limit, filters=filters, ids=ids)


class LazyRows(Mapping):
    """Point/membership/streaming adapter, never a million-element Python map."""
    def __init__(self, projection):
        self.projection = projection

    def __len__(self):
        return self.projection.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]

    def __contains__(self, key):
        return self.projection.execute('SELECT 1 FROM epochs WHERE epoch_uuid=? LIMIT 1', [key]).fetchone() is not None

    def __getitem__(self, key):
        data = self.projection.rows('SELECT * FROM epochs WHERE epoch_uuid=?', [key])
        if not data:
            raise KeyError(key)
        return self.projection._basic(data[0])

    def __iter__(self):
        # Separate reader prevents point lookups inside iteration from resetting
        # the streaming cursor. Iteration buffers at most 2,000 SQL rows.
        if self.projection.engine == 'sqlite':
            reader = sqlite3.connect(f'file:{self.projection.db_path}?mode=ro', uri=True)
        else:
            reader = self.projection.connection.cursor()
        try:
            cursor = reader.execute('SELECT epoch_uuid FROM epochs ORDER BY synthetic_index')
            while True:
                batch = cursor.fetchmany(2000)
                if not batch:
                    break
                for row in batch:
                    yield row[0]
        finally:
            reader.close()


class LazyCells(Mapping):
    def __init__(self, projection):
        self.projection = projection

    def __len__(self):
        return self.projection.execute('SELECT COUNT(DISTINCT cell_uuid) FROM epochs').fetchone()[0]

    def __contains__(self, key):
        return self.projection.execute('SELECT 1 FROM epochs WHERE cell_uuid=? LIMIT 1', [key]).fetchone() is not None

    def __getitem__(self, key):
        data = self.projection.rows('SELECT cell_uuid,cell_label AS label,cell_type,date FROM epochs WHERE cell_uuid=? LIMIT 1', [key])
        if not data:
            raise KeyError(key)
        return data[0]

    def __iter__(self):
        # 10,000 cells at the million-epoch fixture is modest, but stream anyway.
        if self.projection.engine == 'sqlite':
            reader = sqlite3.connect(f'file:{self.projection.db_path}?mode=ro', uri=True)
        else:
            reader = self.projection.connection.cursor()
        try:
            cursor = reader.execute('SELECT DISTINCT cell_uuid FROM epochs ORDER BY cell_uuid')
            while True:
                batch = cursor.fetchmany(1000)
                if not batch:
                    break
                for row in batch:
                    yield row[0]
        finally:
            reader.close()
