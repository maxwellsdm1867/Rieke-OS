"""Exact production catalog algorithm on a disposable DuckDB EAV projection.

No production source is patched. This is a catalog-only engine control. The
original sealed SQLite index remains the authoritative detail/metadata reader.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import duckdb
import pandas as pd
from workspace_disk_index import DiskMetadataIndex
from projection import PROJECT_UUID


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def configured_connection(path, temp_directory=None):
    connection = duckdb.connect(str(path))
    connection.execute('SET threads=2')
    connection.execute("SET memory_limit='512MB'")
    connection.execute("SET max_temp_directory_size='2GB'")
    temp = Path(temp_directory or Path(path).parent / 'eav-spill')
    temp.mkdir(parents=True, exist_ok=True)
    connection.execute('SET temp_directory=?', [str(temp)])
    return connection


class DuckResult:
    def __init__(self, connection):
        self.connection = connection
        self.description = connection.description

    def fetchone(self):
        return self.connection.fetchone()

    def fetchall(self):
        return self.connection.fetchall()

    def __iter__(self):
        while True:
            batch = self.connection.fetchmany(2000)
            if not batch:
                break
            yield from batch


class DuckSQL:
    """Cursor compatibility plus strictly equivalent SQL dialect adjustments."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        # SQLite permits dependent selected columns not named in GROUP BY.
        # value_id uniquely determines value_json; including it changes no groups.
        sql = sql.replace('GROUP BY ev.field_no,ev.value_id ORDER',
                          'GROUP BY ev.field_no,ev.value_id,v.value_json ORDER')
        sql = sql.replace('GROUP BY v.value_id ORDER',
                          'GROUP BY v.value_id,v.value_json ORDER')
        # SQLite's constrained CROSS JOIN is ordinary equijoin semantics.
        # DuckDB rejects CROSS JOIN ... USING and chooses its own join plan.
        sql = sql.replace('CROSS JOIN epoch_values', 'JOIN epoch_values')
        return DuckResult(self.connection.execute(sql, parameters))

    def executemany(self, sql, parameters):
        # Production values() uses this for <=16 requested field definitions,
        # never for importing data or adding a million scope members.
        for values in parameters:
            self.execute(sql, values)
        return self


def import_sqlite(source_path, destination_path, progress=None):
    """Bounded 5,000-row DataFrame batches; no DuckDB row-at-a-time import."""
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f'file:{Path(source_path)}?mode=ro&immutable=1', uri=True)
    target = configured_connection(destination_path)
    phases, started = {}, time.perf_counter()
    try:
        for table in ('meta', 'epochs', 'fields', 'field_values', 'epoch_values', 'sources'):
            begin = time.perf_counter()
            columns = source.execute(f'PRAGMA table_info({table})').fetchall()
            names = [column[1] for column in columns]
            types = [('BIGINT' if 'INT' in column[2].upper() else
                      'BLOB' if column[2].upper() == 'BLOB' else 'VARCHAR') for column in columns]
            target.execute(f'CREATE TABLE {table} (' + ','.join(f'{name} {typ}' for name, typ in zip(names, types)) + ')')
            reader, count = source.execute(f'SELECT * FROM {table}'), 0
            while True:
                batch = reader.fetchmany(5000)
                if not batch:
                    break
                frame = pd.DataFrame.from_records(batch, columns=names)
                target.register('import_batch', frame)
                target.execute(f'INSERT INTO {table} SELECT * FROM import_batch')
                target.unregister('import_batch')
                count += len(batch)
                if progress:
                    progress(table, count)
            phases[table] = {'rows': count, 'seconds': time.perf_counter() - begin}
        target.execute('CREATE UNIQUE INDEX eav_epoch_uuid ON epochs(epoch_uuid)')
        target.execute('CHECKPOINT')
        return {'tables': phases, 'seconds': time.perf_counter() - started,
                'bytes': destination_path.stat().st_size}
    finally:
        source.close()
        target.close()


def derive_from_typed(typed_path, template_sqlite_path, destination_path, progress=None):
    """Bulk SQL EAV derivation for the exact four-parameter synthetic fixture.

    Sixteen SQL field passes replace Python epoch maps. This is not import
    support for arbitrary production metadata or an acquisition integrity seal.
    """
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    target = configured_connection(destination_path)
    template = sqlite3.connect(f'file:{Path(template_sqlite_path)}?mode=ro&immutable=1', uri=True)
    expressions = {'epoch': 'epoch_uuid', 'date': 'date', 'cell': 'cell_uuid',
                   'block': 'block_uuid', 'block time': 'block_start_time',
                   'cell type': 'cell_type', 'group label': 'group_label',
                   'group': 'group_uuid', 'protocol': 'protocol_name',
                   'parameters/contrast': 'contrast', 'parameters/currentMean': 'currentMean',
                   'parameters/seed': 'seed', 'parameters/stimTime': 'stimTime',
                   'metadata/cell/properties/type': 'cell_type',
                   'metadata/cell/label': 'cell_label', 'metadata/block/parameters/amp': "'Amp1'"}
    phases, started = {}, time.perf_counter()
    try:
        # ATTACH path escaping is ordinary SQL literal escaping, not shell code.
        target.execute("ATTACH '" + str(Path(typed_path)).replace("'", "''") + "' AS typed (READ_ONLY)")
        begin = time.perf_counter()
        target.execute('''CREATE TABLE epochs AS SELECT synthetic_index+1 AS epoch_id,
            epoch_uuid,source_sha256 AS source_sha,cell_uuid,
            CAST(to_json(struct_pack(epoch_uuid:=epoch_uuid,cell_uuid:=cell_uuid,cell_label:=cell_label,
                cell_type:=cell_type,date:=date,start_time:=start_time,group_uuid:=group_uuid,group_label:=group_label,
                block_uuid:=block_uuid,block_start_time:=block_start_time,protocol_name:=protocol_name,
                duration_seconds:=duration_seconds,epoch_number:=epoch_number,streams:=[]::VARCHAR[],
                source_sha256:=source_sha256,metadata_hash:=metadata_hash,synthetic_index:=synthetic_index)) AS VARCHAR) AS row_json,
            NULL::BLOB AS detail_blob,metadata_hash AS fingerprint FROM typed.epochs''')
        phases['epoch_rows_seconds'] = time.perf_counter() - begin
        definitions = template.execute('SELECT field_no,field_id,definition_json FROM fields ORDER BY field_no').fetchall()
        if {row[1] for row in definitions} != set(expressions):
            raise ValueError('EAV derivation supports only the exact registered synthetic fixture fields')
        target.execute('CREATE TABLE fields(field_no BIGINT,field_id VARCHAR,definition_json VARCHAR)')
        target.register('field_input', pd.DataFrame.from_records(definitions, columns=['field_no', 'field_id', 'definition_json']))
        target.execute('INSERT INTO fields SELECT * FROM field_input')
        target.unregister('field_input')
        target.execute('CREATE TABLE field_values(value_id BIGINT,field_no BIGINT,value_json VARCHAR)')
        target.execute('CREATE TABLE epoch_values(epoch_id BIGINT,field_no BIGINT,value_id BIGINT)')
        offset = 0
        for field_no, field_id, _ in definitions:
            begin = time.perf_counter()
            expression = expressions[field_id]
            target.execute(f'''INSERT INTO field_values
                SELECT ?+ROW_NUMBER() OVER (ORDER BY first_index),?,value_json FROM (
                  SELECT CAST(to_json({expression}) AS VARCHAR) AS value_json,MIN(synthetic_index) AS first_index
                  FROM typed.epochs GROUP BY value_json) dictionary''', [offset, field_no])
            target.execute(f'''INSERT INTO epoch_values SELECT t.synthetic_index+1,?,v.value_id
                FROM typed.epochs t JOIN field_values v ON v.field_no=? AND v.value_json=CAST(to_json({expression}) AS VARCHAR)''',
                           [field_no, field_no])
            count = target.execute('SELECT COUNT(*) FROM field_values WHERE field_no=?', [field_no]).fetchone()[0]
            offset += count
            phases[field_id] = {'distinct': count, 'seconds': time.perf_counter() - begin}
            if progress:
                progress(field_id, count)
        target.execute('CREATE TABLE meta(key VARCHAR,value VARCHAR)')
        metadata = {'format': 3, 'generation': 'experimental-typed-eav',
                    'project_uuid': PROJECT_UUID, 'complete': True}
        frame = pd.DataFrame([(key, json.dumps(value)) for key, value in metadata.items()], columns=['key', 'value'])
        target.register('metadata_input', frame)
        target.execute('INSERT INTO meta SELECT * FROM metadata_input')
        target.unregister('metadata_input')
        target.execute('CREATE TABLE sources(source_sha VARCHAR,source_json VARCHAR)')
        sources = template.execute('SELECT source_sha,source_json FROM sources').fetchall()
        target.register('source_input', pd.DataFrame(sources, columns=['source_sha', 'source_json']))
        target.execute('INSERT INTO sources SELECT * FROM source_input')
        target.unregister('source_input')
        target.execute('CREATE UNIQUE INDEX eav_epoch_uuid ON epochs(epoch_uuid)')
        target.execute('CHECKPOINT')
        return {'phases': phases, 'seconds': time.perf_counter() - started,
                'bytes': destination_path.stat().st_size,
                'epoch_values': target.execute('SELECT COUNT(*) FROM epoch_values').fetchone()[0]}
    finally:
        target.close()
        template.close()


class DuckCatalogIndex(DiskMetadataIndex):
    """Reuse the exact current catalog/suggestion implementation and outputs."""
    def __init__(self, path):
        self.path = Path(path)
        self._closed = False
        self.connection = configured_connection(self.path)
        self._definitions = [json.loads(raw) for raw, in
                             self.connection.execute('SELECT definition_json FROM fields ORDER BY field_no').fetchall()]
        metadata = {key: json.loads(value) for key, value in self.connection.execute('SELECT key,value FROM meta').fetchall()}
        self._catalog_cache = metadata.get('catalog')
        self._predicate_cache = metadata.get('predicate_catalog')
        self._epoch_count = self.connection.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]
        self.generation = metadata.get('generation')
        self.project_uuid = metadata.get('project_uuid')

    def _check(self):
        if self._closed:
            raise ValueError('Experimental Duck catalog reader is closed')

    @contextmanager
    def _connect(self, ids=None):
        self._check()
        connection = self.connection.cursor()
        try:
            if ids is None:
                connection.execute('CREATE TEMP VIEW scope AS SELECT epoch_id AS ordinal,epoch_id FROM epochs')
            elif not ids:
                connection.execute('CREATE TEMP TABLE scope(ordinal BIGINT,epoch_id BIGINT)')
            else:
                # Stable first occurrence preserves SQLite INSERT OR IGNORE.
                frame = pd.DataFrame({'ordinal': range(len(ids)), 'epoch_uuid': ids})
                frame = frame.drop_duplicates('epoch_uuid', keep='first')
                connection.register('scope_input', frame)
                connection.execute('CREATE TEMP TABLE scope AS SELECT i.ordinal,e.epoch_id FROM scope_input i JOIN epochs e USING(epoch_uuid)')
                connection.unregister('scope_input')
            yield DuckSQL(connection)
            self._check()
        finally:
            connection.close()

    def close(self):
        if not self._closed:
            self.connection.close()
        self._closed = True

    @property
    def details(self):
        raise NotImplementedError('Catalog-only control; use the original sealed SQLite details reader')
