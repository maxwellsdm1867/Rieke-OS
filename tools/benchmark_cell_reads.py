#!/usr/bin/env python3
"""Fixed 100-epoch cell versus project growth, using real SQLite lookup SQL.

Owned fixture supplies seal admission explicitly; not native or UI qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run(source, epochs):
    sys.path[:0] = [str(source / 'python'), str(source / 'python/tests'),
                   str(ROOT / 'benchmarks/everyday'), str(ROOT / 'tools')]
    import h5py
    from fixture import row, uid
    from test_workspace_api import FixtureService
    from workspace_qc import CellQC
    from disco.metadata.disk_index import DiskMetadataIndex, _signature
    from benchmark_everyday import source as source_identity, environment
    result = dict(status='incomplete', epochs=epochs, cell_epochs=100,
        source_start=source_identity(source), environment=environment(), operations={},
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), limitations=[
            'Production cell-read methods; real SQLite membership table/index; fixture supplies seal admission.',
            'Metadata details, native SQL, HTTP/UI and full production generation build are not measured.',
            'Fixture and index construction excluded from read medians.'])
    with tempfile.TemporaryDirectory(prefix='disco-cell-read-benchmark-') as folder, \
            patch.object(h5py, 'File', side_effect=AssertionError('Cell metadata lookup opened H5')):
        path = Path(folder) / 'cell-membership.sqlite'
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE epochs(epoch_id INTEGER PRIMARY KEY,epoch_uuid TEXT UNIQUE,cell_uuid TEXT)')
            connection.executemany('INSERT INTO epochs VALUES(?,?,?)',
                ((i + 1, uid(i), uid(1_000_000 + i // 100)) for i in range(epochs)))
            connection.execute('CREATE INDEX epochs_cell ON epochs(cell_uuid,epoch_uuid)')
        service = FixtureService(folder)
        service.rows = {uid(i): row(i) for i in range(epochs)}
        cell = uid(1_000_000)
        service.cells = {cell: dict(cell_uuid=cell, label='Cell 0')}
        index = DiskMetadataIndex.__new__(DiskMetadataIndex)
        index.path = path
        index.generation = 'owned-cell-lookup-fixture'
        index.project_uuid = service.project['project_uuid']
        index._closed = False
        index._signature = _signature(path)
        service.disk_index = index
        qc = CellQC(service)

        def count():
            if hasattr(service, 'cell_epoch_count'):
                return service.cell_epoch_count(cell)
            return sum(value['cell_uuid'] == cell for value in service.rows.values())

        def measure(name, read, oracle):
            samples = []
            for _ in range(9):
                start = time.perf_counter()
                answer = read()
                samples.append((time.perf_counter() - start) * 1000)
                oracle(answer)
            result['operations'][name] = dict(milliseconds=samples, median_ms=statistics.median(samples), correct=True)

        def check_count(answer):
            assert answer == 100

        def check_rows(answer):
            assert [value['epoch_uuid'] for value in answer] == [uid(i) for i in range(100)]

        measure('cell.count', count, check_count)
        measure('cell.qc_rows', lambda: qc.rows(cell), check_rows)

        class CountedRows(dict):
            visits = 0
            def values(self):
                for value in super().values():
                    self.visits += 1
                    yield value
            def __getitem__(self, key):
                self.visits += 1
                return super().__getitem__(key)

        service.rows = CountedRows(service.rows)
        check_count(count())
        result['count_basic_row_visits'] = service.rows.visits
        service.rows.visits = 0
        check_rows(qc.rows(cell))
        result['qc_basic_row_visits'] = service.rows.visits
        with sqlite3.connect(path) as connection:
            result['sql_plan'] = connection.execute(
                'EXPLAIN QUERY PLAN SELECT COUNT(*) FROM epochs WHERE cell_uuid=?', (cell,)).fetchall()
        index.close()
        result['h5_open_attempts'] = 0
        result['source_end'] = source_identity(source)
        assert result['source_start'] == result['source_end']
        result['status'] = 'passed'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--epochs', type=int, choices=(20000, 200000, 1000000), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    result = run(args.source_root.resolve(), args.epochs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'epochs': args.epochs,
                      'visits': [result['count_basic_row_visits'], result['qc_basic_row_visits']],
                      'medians': {key: value['median_ms'] for key, value in result['operations'].items()}}))
