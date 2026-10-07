"""Deterministic metadata-only fixture; all expected identities come from integers."""
import json
import sqlite3
import threading
import zlib

N = 1_000_000
SOURCE_SHA = 'a' * 64
STREAMS = [{'stream_name': 'Amp1', 'h5_path': '/epoch/response/data',
            'sample_count': 10000, 'sample_rate_hz': 10000, 'units': 'pA'}]


def uid(i):
    return f'00000000-0000-0000-0000-{i:012x}'


def row(i):
    return {'epoch_uuid': uid(i), 'cell_uuid': uid(N + i // 100),
            'cell_label': f'Cell {i // 100}', 'cell_type': 'ON',
            'block_uuid': uid(2 * N + i // 20), 'group_uuid': uid(3 * N),
            'group_label': 'control', 'protocol_name': 'Synthetic',
            'date': '2026-10-07', 'start_time': '10/07/2026 10:00:00:000000',
            'block_start_time': '10/07/2026 10:00:00', 'duration_seconds': 1.0,
            'source_sha256': SOURCE_SHA, 'epoch_number': i % 20 + 1, 'streams': STREAMS}


def detail(i):
    return {'parameters': {'unique': f'unique-{i:012d}', 'category': i % 10},
            'properties': {}, 'metadata': {}}


def tree_fixture():
    from workspace_service import WorkspaceService
    from disco.metadata.disk_index import DiskMetadataIndex
    from disco.navigation.tree_pages import TreePages, _structural_contract

    class AdmittedSchema(DiskMetadataIndex):
        # The seam is admission/catalog only. Service and pager methods are real.
        def __init__(self):
            self.generation = 'everyday-million-v1'

        def _check(self):
            pass

        def catalog(self, *args, **kwargs):
            return {'fields': [{'id': f, 'label': f.title(), 'types': ['string']}
                               for f in ('date', 'cell', 'block')], 'total': N}

        def values(self, *args, **kwargs):
            raise AssertionError('Structural browsing requested a metadata matrix')

        def close(self):
            pass

    service = WorkspaceService.__new__(WorkspaceService)
    service._loaded = True
    service.project = {'project_uuid': uid(9 * N)}
    service.curation_provider = None
    service.rows = {uid(i): row(i) for i in range(N)}
    service._fingerprints = dict.fromkeys(service.rows, 'b' * 64)
    service.sources = [{'source_sha256': SOURCE_SHA, 'source_path': 'never-open.h5'}]
    service.cells = {}
    service.protocols = {}
    service.disk_index = AdmittedSchema()
    assert len(service.rows) == N and _structural_contract(service)
    return service, TreePages(service)


# SQLite relations are real million-row tables; only disk ownership/seal admission
# is replaced by an owned in-memory connection. Query implementations are inherited.
from disco.metadata.typed_index import TypedMetadataIndex
from disco.metadata.typed_query import CORE_COLUMNS, equality_json
from disco.metadata.metadata_objects import Decoder

class MemoryReader(TypedMetadataIndex):

    def __init__(self, connection):
        self.connection = connection
        self._closed = False
        self._cancel_event = threading.Event()
        self._cancel_callback = None
        self.fields = {'parameters/unique': 1, 'parameters/category': 2, 'cell': 3, 'block': 4}
        self.definitions = [{'id': x, 'label': x} for x in self.fields]
        self.validation_representatives = {'1': {'string': json.dumps('unique-000000000000')}, '2': {'number': '0'}, '3': {'string': json.dumps(uid(N))}, '4': {'string': json.dumps(uid(2 * N))}}
        self.core_safe = {'cell': True, 'block': True}
        self.wide_fields = set()
        self.core_string_fields = {'cell', 'block'}
        self.decoder = Decoder()
        self._dictionary_match_no = 0

    def _check(self):
        if self._closed:
            raise ValueError('Memory fixture closed')
        if self._cancel_requested():
            raise RuntimeError('Memory fixture cancelled')

def typed_fixture(report):
    c = sqlite3.connect(':memory:')
    c.execute('PRAGMA temp_store=MEMORY')
    c.execute("ATTACH DATABASE ':memory:' AS native")
    c.executescript('CREATE TABLE native.epochs(epoch_id INTEGER PRIMARY KEY,epoch_uuid TEXT UNIQUE NOT NULL,source_sha TEXT,cell_uuid TEXT,row_json TEXT NOT NULL,detail_blob BLOB NOT NULL,fingerprint TEXT NOT NULL);\n    CREATE TABLE native.epoch_values(epoch_id INTEGER,field_no INTEGER,value_id INTEGER,PRIMARY KEY(epoch_id,field_no)) WITHOUT ROWID;\n    CREATE TEMP VIEW epochs AS SELECT * FROM native.epochs;\n    CREATE TEMP VIEW epoch_values AS SELECT * FROM native.epoch_values;\n    CREATE TABLE typed_core(epoch_id INTEGER PRIMARY KEY,sort_rank INTEGER,epoch_uuid TEXT NOT NULL,source_sha256 TEXT,cell_uuid TEXT,block_uuid TEXT,group_uuid TEXT,protocol_name TEXT,date TEXT,start_time TEXT,block_start_time TEXT,epoch_number INTEGER,duration_seconds REAL,cell_label TEXT,cell_type TEXT,group_label TEXT);\n    CREATE TABLE typed_values(value_id INTEGER PRIMARY KEY,field_no INTEGER NOT NULL,kind TEXT NOT NULL,numeric_value,numeric_class TEXT,text_value TEXT,equality_json TEXT NOT NULL,value_json TEXT NOT NULL);\n    CREATE TEMP TABLE supplied_scope(epoch_id INTEGER PRIMARY KEY);\n    CREATE TEMP TABLE supplied_sources(source_sha TEXT PRIMARY KEY);\n    CREATE TEMP TABLE dictionary_matches(match_no INTEGER,value_id INTEGER,PRIMARY KEY(match_no,value_id)) WITHOUT ROWID;')
    for start in range(0, N, 2000):
        native = []
        core = []
        values = []
        links = []
        for i in range(start, min(N, start + 2000)):
            r = row(i)
            unique = f'unique-{i:012d}'
            native.append((i + 1, r['epoch_uuid'], SOURCE_SHA, r['cell_uuid'], json.dumps(r, separators=(',', ':')), zlib.compress(json.dumps({'version': 1, 'inline': detail(i), 'objects': {}}).encode()), 'b' * 64))
            core.append([i + 1, i + 1] + [r.get(k) for k in CORE_COLUMNS])
            values.append((i + 1, 1, 'string', None, None, unique, equality_json(unique), json.dumps(unique)))
            links.extend(((i + 1, 1, i + 1), (i + 1, 2, N + 1 + i % 10)))
        c.executemany('INSERT INTO native.epochs VALUES (?,?,?,?,?,?,?)', native)
        c.executemany('INSERT INTO typed_core VALUES (' + ','.join('?' * 16) + ')', core)
        c.executemany('INSERT INTO typed_values VALUES (?,?,?,?,?,?,?,?)', values)
        c.executemany('INSERT INTO native.epoch_values VALUES (?,?,?)', links)
        if start % 100000 == 0:
            report('insert_progress', inserted=start + 2000)
    c.executemany('INSERT INTO typed_values VALUES (?,?,?,?,?,?,?,?)', [(N + 1 + i, 2, 'number', i, 'integer', None, equality_json(i), json.dumps(i)) for i in range(10)])
    for name, sql in [('epochs_source', 'CREATE INDEX native.epochs_source ON epochs(source_sha)'), ('values_reverse', 'CREATE INDEX native.values_reverse ON epoch_values(field_no,value_id,epoch_id)'), ('typed_uuid', 'CREATE UNIQUE INDEX typed_uuid ON typed_core(epoch_uuid)'), ('typed_sort_rank', 'CREATE UNIQUE INDEX typed_sort_rank ON typed_core(sort_rank)'), ('typed_chronology', 'CREATE INDEX typed_chronology ON typed_core(date,start_time,epoch_uuid)'), ('typed_cell_children', 'CREATE INDEX typed_cell_children ON typed_core(cell_uuid,sort_rank)'), ('typed_block_children', 'CREATE INDEX typed_block_children ON typed_core(block_uuid,sort_rank)'), ('typed_group_children', 'CREATE INDEX typed_group_children ON typed_core(group_uuid,sort_rank)'), ('typed_protocol_children', 'CREATE INDEX typed_protocol_children ON typed_core(protocol_name,sort_rank)'), ('typed_numeric', 'CREATE INDEX typed_numeric ON typed_values(field_no,kind,numeric_value,value_id)'), ('typed_text', 'CREATE INDEX typed_text ON typed_values(field_no,kind,text_value,value_id)'), ('typed_equality', 'CREATE INDEX typed_equality ON typed_values(field_no,equality_json,value_id)'), ('typed_kind', 'CREATE INDEX typed_kind ON typed_values(field_no,kind,value_id)')]:
        c.execute(sql)
        report('index_built', name=name)
    c.commit()
    c.execute('ANALYZE main')
    c.commit()
    assert c.execute('SELECT COUNT(*) FROM native.epochs').fetchone()[0] == N
    return MemoryReader(c)
