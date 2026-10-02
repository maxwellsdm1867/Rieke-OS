"""Actual mounted metadata control; all writes stay in this isolated directory."""
from pathlib import Path
import collections
import hashlib
import json
import os
import resource
import signal
import shutil
import sqlite3
import statistics
import sys
import threading
import time
import zlib

OUT = Path('/private/tmp/disco-real-data-evals-20261001/engines')
BASE = Path('/private/tmp/disco-duckdb-million-20261001')
NATIVE = Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
sys.path[:0] = [str(NATIVE), '/private/tmp/disco-duckdb-deps-20261001',
               str(BASE/'docs/dev/duckdb-million-evals-2026-10-01/readmodel'),
               str(OUT.parent/'profile')]
from workspace_disk_index import DiskMetadataIndex
from workspace_projection_cache import _ProjectionDetails
from workspace_metadata_objects import Decoder
from real_projection_loader import load_real_projections, PROJECT, digest as file_digest
from eav_duck import DuckCatalogIndex, DuckSQL, import_sqlite, configured_connection
import duckdb
import pandas as pd

LIMIT = 512*1024*1024
START = time.perf_counter()
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120-second process cap')))
signal.alarm(120)
def watch_memory():
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > LIMIT:
            print('PROCESS_MEMORY_CAP_EXCEEDED', flush=True)
            os._exit(91)
        time.sleep(.2)
threading.Thread(target=watch_memory, daemon=True).start()

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
def event(kind, **values):
    print(json.dumps(dict(event=kind, elapsed_seconds=time.perf_counter()-START, **values)), flush=True)
def timed(function, repeats=5):
    times, expected = [], None
    for _ in range(repeats):
        begin = time.perf_counter()
        result = function()
        encoded = canonical(result)
        times.append((time.perf_counter()-begin)*1000)
        checksum = hashlib.sha256(encoded).hexdigest()
        if expected is None:
            expected = checksum
        assert checksum == expected, 'Repeated outputs differ'
    return dict(milliseconds=times, median_ms=statistics.median(times), output_sha256=expected,
                output_bytes=len(encoded)), result

def copy_objects(sqlite_path, duck_path):
    source = sqlite3.connect(f'file:{sqlite_path}?mode=ro&immutable=1', uri=True)
    target = configured_connection(duck_path)
    try:
        target.execute("SET memory_limit='192MB'")
        target.execute('CREATE TABLE metadata_objects(object_id BIGINT, source_sha VARCHAR, kind VARCHAR, object_uuid VARCHAR, payload BLOB, sha256 BLOB)')
        cursor = source.execute('SELECT object_id,source_sha,kind,object_uuid,payload,sha256 FROM metadata_objects ORDER BY object_id')
        count = 0
        while batch := cursor.fetchmany(5000):
            frame = pd.DataFrame.from_records(batch, columns=['object_id','source_sha','kind','object_uuid','payload','sha256'])
            target.register('objects_input', frame)
            target.execute('INSERT INTO metadata_objects SELECT * FROM objects_input')
            target.unregister('objects_input')
            count += len(batch)
        target.execute('CHECKPOINT')
        return count
    finally:
        source.close(); target.close()

class DecodeSQL(DuckSQL):
    """Decoder namespace is stable for this one immutable comparison handle."""
    def execute(self, sql, parameters=()):
        if sql == 'PRAGMA database_list':
            from workspace_projection_cache import _Cursor
            return _Cursor([(0, 'main', str(OUT/'real.duckdb'))])
        return super().execute(sql, parameters)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    directory=PROJECT/'cache/source-projections'
    projection_manifest=directory/'.current-generations.json'
    manifest_sha=file_digest(projection_manifest)
    names=json.loads(projection_manifest.read_bytes())['keep']
    rows,cells,sources,details,evidence_sources={},{},[],{},[]
    for name in names:
        blob=(directory/name).read_bytes()
        checksum=hashlib.sha256(blob).hexdigest()
        assert checksum==(directory/name).with_suffix('.sha256').read_text().strip()
        document=json.loads(zlib.decompress(blob)); projection=document['projection']
        lazy=_ProjectionDetails(projection['rows'],document['details'],document['objects'])
        assert not rows.keys() & projection['rows'].keys()
        rows.update(projection['rows']); cells.update(projection['cells']); sources.append(projection['source'])
        details.update((identity,lazy) for identity in lazy)
        evidence_sources.append(dict(projection=name,sha256=checksum,epochs=len(lazy),metadata_objects=len(document['objects'])))
    evidence=dict(manifest_sha256=manifest_sha,manifest=names,sources=evidence_sources)
    epoch_ids = list(rows)
    metadata_directory=PROJECT/'cache/metadata'
    metadata_manifest=metadata_directory/'.current-generations.json'
    metadata_manifest_sha=file_digest(metadata_manifest)
    active=json.loads(metadata_manifest.read_bytes())['keep']
    assert len(active)==1,'Ambiguous current metadata index'
    source_sqlite=metadata_directory/active[0]
    seal_path=Path(str(source_sqlite)+'.sha256.json')
    seal=json.loads(seal_path.read_bytes())
    assert file_digest(source_sqlite)==seal['sha256']
    shutil.copyfile(source_sqlite,OUT/'real.sqlite')
    shutil.copyfile(seal_path,OUT/'real.sqlite.sha256.json')
    assert file_digest(OUT/'real.sqlite')==seal['sha256']
    generation,project_uuid=seal['generation'],seal['project_uuid']
    receipt = dict(data_kind='actual real mounted source-projection metadata; no synthetic rows',
        epochs=len(rows), cells=len(cells), sources=len(sources), input_evidence=evidence,
        python=sys.version, sqlite=sqlite3.sqlite_version, duckdb=duckdb.__version__,
        caps=dict(process_seconds=120, process_peak_rss_bytes=LIMIT, duckdb_threads=2, duckdb_query_memory='192MB'),
        limitations=['2781 real epochs do not qualify one million real epochs',
            'Catalog algorithm and bounded SQL controls, not the full native preview endpoint',
            'DuckDB constructed by copying production EAV SQLite, so import timings are not symmetric initial-ingest comparisons',
            'Five warm repeats; page cache and runtime initialized; no cold app startup or waveform I/O',
            'DuckDB preserves the installed production EAV representation; optimized typed schema is not this comparison'])
    receipt['source_sqlite']=dict(active_name=active[0],sha256=seal['sha256'],manifest_sha256=metadata_manifest_sha,
        native_code_sha256=file_digest(NATIVE/'workspace_disk_index.py'))
    event('real_data_loaded', epochs=len(rows))
    begin = time.perf_counter()
    index = DiskMetadataIndex.open(OUT/'real.sqlite', generation, project_uuid)
    receipt['sqlite_clone_open'] = dict(seconds=time.perf_counter()-begin, bytes=index.path.stat().st_size, initial_ingest_not_measured=True)
    event('sqlite_clone_open', **receipt['sqlite_clone_open'])
    # Owned derivative only: reruns rebuild the same isolated Duck copy.
    (OUT/'real.duckdb').unlink(missing_ok=True)
    receipt['duck_copy'] = import_sqlite(index.path, OUT/'real.duckdb')
    receipt['duck_metadata_objects'] = copy_objects(index.path, OUT/'real.duckdb')
    duck = DuckCatalogIndex(OUT/'real.duckdb')
    duck.connection.execute("SET memory_limit='192MB'")
    receipt['duck_copy']['bytes_with_metadata_objects']=(OUT/'real.duckdb').stat().st_size
    event('duck_copied', seconds=receipt['duck_copy']['seconds'])
    sql = sqlite3.connect(f'file:{index.path}?mode=ro&immutable=1', uri=True)
    dsql = duck.connection
    try:
        assert index.rows() == rows
        db_epoch_ids=[row[0] for row in sql.execute('SELECT epoch_uuid FROM epochs ORDER BY epoch_id')]
        assert set(db_epoch_ids)==set(epoch_ids)
        receipt['native_epoch_membership_sha256']=digest(sorted(epoch_ids))
        epoch_ids=db_epoch_ids
        receipt['table_copy_oracles'] = {}
        for table in ['meta','epochs','fields','field_values','epoch_values','sources','metadata_objects']:
            def table_rows(connection):
                fetched = connection.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
                return [[{'blob_sha256':hashlib.sha256(value).hexdigest(), 'blob_bytes':len(value)} if isinstance(value, bytes) else value for value in row] for row in fetched]
            original, copied = table_rows(sql), table_rows(dsql)
            assert original == copied, f'Table differs: {table}'
            receipt['table_copy_oracles'][table] = dict(rows=len(original), output_sha256=digest(original))
        scopes = [('global', None, None)]
        for label, field in [('largest_protocol','protocol'), ('largest_cell','cell')]:
            query='''SELECT v.value_json,COUNT(*) FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? GROUP BY v.value_id ORDER BY COUNT(*) DESC,v.value_json LIMIT 1'''
            value, _ = sql.execute(query, [field]).fetchone()
            scopes.append((label, field, value))
        candidates = []
        for field, raw, count in sql.execute('''SELECT f.field_id,v.value_json,COUNT(*) FROM epoch_values ev JOIN fields f USING(field_no) JOIN field_values v USING(value_id) GROUP BY f.field_no,v.value_id'''):
            value = json.loads(raw)
            if 0 < count < len(rows) and field.startswith(('parameters/', 'metadata/', 'properties/')):
                candidates.append((field, raw, count, value))
        for label, kind in [('numeric_value', (int,float)), ('text_value', str)]:
            candidate = min((item for item in candidates if isinstance(item[3],kind) and not isinstance(item[3],bool)), key=lambda item:abs(item[2]-len(rows)/2))
            scopes.append((label, candidate[0], candidate[1]))
        missing = sql.execute('''SELECT f.field_id,COUNT(ev.epoch_id) AS recorded FROM fields f LEFT JOIN epoch_values ev USING(field_no) GROUP BY f.field_no HAVING recorded>0 AND recorded<? ORDER BY ABS(recorded-?) LIMIT 1''',[len(rows),len(rows)/2]).fetchone()
        scopes.append(('missing_field', missing[0], '__ABSENT__'))
        receipt['scopes'] = []
        for label, field, raw in scopes:
            if field is None:
                query, arguments = 'SELECT epoch_uuid FROM epochs ORDER BY epoch_id', []
            elif raw == '__ABSENT__':
                query = '''SELECT e.epoch_uuid FROM epochs e WHERE NOT EXISTS(SELECT 1 FROM epoch_values ev JOIN fields f USING(field_no) WHERE ev.epoch_id=e.epoch_id AND f.field_id=?) ORDER BY e.epoch_id'''
                arguments = [field]
            else:
                query = '''SELECT e.epoch_uuid FROM epochs e JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? AND v.value_json=? ORDER BY e.epoch_id'''
                arguments = [field,raw]
            membership = [identity for identity, in sql.execute(query,arguments)]
            assert membership == [identity for identity, in dsql.execute(query,arguments).fetchall()]
            scope = dict(label=label, field=field, selection='absent' if raw=='__ABSENT__' else 'observed equality' if field else 'all', epochs=len(membership), membership_sha256=digest(membership))
            selected = None if field is None else membership
            results = {}
            # Both use identical production catalog code and scoped membership.
            for name, arm in [('sqlite',index), ('duckdb',duck)]:
                if selected is None:
                    def catalog(arm=arm):
                        arm._catalog_cache=None
                        return arm.catalog()
                else:
                    def catalog(arm=arm):
                        return arm.catalog(selected)
                results[name], output = timed(catalog)
                scope['field_count'] = len(output['fields'])
            assert results['sqlite']['output_sha256']==results['duckdb']['output_sha256'], f'Catalog differs: {label}'
            scope['catalog_plus_json'] = results
            # Scope extraction timing remains a separate measurement.
            scope['membership_query']={}
            for name, connection in [('sqlite',sql),('duckdb',dsql)]:
                scope['membership_query'][name], _ = timed(lambda connection=connection:[row[0] for row in connection.execute(query,arguments).fetchall()])
            receipt['scopes'].append(scope)
            event('scope_verified', label=label, epochs=len(membership), sqlite_ms=results['sqlite']['median_ms'], duckdb_ms=results['duckdb']['median_ms'])
        bounded = {}
        for name, connection in [('sqlite',sql),('duckdb',dsql)]:
            page_query='SELECT row_json FROM epochs ORDER BY epoch_id LIMIT 60'
            bounded[name], page = timed(lambda connection=connection:[json.loads(raw) for raw, in connection.execute(page_query).fetchall()])
        assert bounded['sqlite']['output_sha256']==bounded['duckdb']['output_sha256']
        receipt['first_60_rows_plus_json']=bounded
        detail = {}
        for name, connection in [('sqlite',sql),('duckdb',DecodeSQL(dsql))]:
            def get_detail(connection=connection):
                decoder=Decoder()
                record=connection.execute('SELECT row_json,detail_blob FROM epochs ORDER BY epoch_id LIMIT 1').fetchone()
                return decoder.decode(connection,json.loads(record[0]),record[1])
            detail[name], value=timed(get_detail)
            assert value==details[epoch_ids[0]][epoch_ids[0]]
        assert detail['sqlite']['output_sha256']==detail['duckdb']['output_sha256']
        receipt['first_detail_sql_decode_json']=detail
        directory=PROJECT/'cache/source-projections'
        assert file_digest(directory/'.current-generations.json')==evidence['manifest_sha256']
        for item in evidence['sources']:
            assert file_digest(directory/item['projection'])==item['sha256']
        assert file_digest(metadata_manifest)==metadata_manifest_sha
        assert file_digest(source_sqlite)==seal['sha256']
        receipt['input_after_verified']=True
        receipt['total_seconds']=time.perf_counter()-START
        receipt['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        receipt['all_oracles_passed']=True
        (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        event('finished', peak_rss_bytes=receipt['peak_rss_bytes'], total_seconds=receipt['total_seconds'])
    finally:
        sql.close(); duck.close(); index.close()

if __name__=='__main__':
    main()
