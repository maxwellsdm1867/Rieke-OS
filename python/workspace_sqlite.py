"""Frozen workspace metadata and H5 pointers as a queryable SQLite handoff.

This is a generic recording-workspace schema, not the fitted Compact/SRM/VMN
analysis schema. No fabricated waveform rows, fitted parameters, or condition
labels are supplied. Wheeler can inspect/query this database using SQLite.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
import zlib

from workspace_recipes import member_map, verify
from workspace_tree import field_id
from workspace_tag_exchange import frozen_annotation_entries

SCHEMA_VERSION = 2
FORMAT = 'recording-workspace-sqlite'
COMPATIBILITY = ('Queryable with standard SQLite and Wheeler SQL tools. Schema is recording-workspace v2; '
                 'not a drop-in replacement for retina_srm_compact or vmn_diff_mean fitted-analysis databases. '
                 'Waveforms are lazy references to original H5 files; no raw_traces sample table or model fits are included.')
SCHEMA = '''
CREATE TABLE export_metadata (
 export_uuid TEXT PRIMARY KEY, project_uuid TEXT NOT NULL, protocol_uuid TEXT NOT NULL,
 format TEXT NOT NULL, schema_version INTEGER NOT NULL, created_at TEXT NOT NULL,
 actor TEXT NOT NULL, catalog_ref TEXT NOT NULL, recipe_json TEXT NOT NULL,
 query_json TEXT NOT NULL, recipe_sha256 TEXT NOT NULL, package_sha256 TEXT NOT NULL,
 compatibility TEXT NOT NULL, waveforms TEXT NOT NULL);
CREATE TABLE sources (source_sha256 TEXT PRIMARY KEY, source_path TEXT NOT NULL);
CREATE TABLE cells (cell_uuid TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL REFERENCES sources,
 cell_label TEXT, cell_type TEXT, recording_date TEXT, metadata_json TEXT NOT NULL);
CREATE TABLE epoch_groups (group_uuid TEXT PRIMARY KEY, cell_uuid TEXT NOT NULL REFERENCES cells,
 group_label TEXT, metadata_json TEXT NOT NULL);
CREATE TABLE epoch_blocks (block_uuid TEXT PRIMARY KEY, group_uuid TEXT NOT NULL REFERENCES epoch_groups,
 acquisition_protocol TEXT NOT NULL, start_time TEXT, end_time TEXT, metadata_json TEXT NOT NULL);
CREATE TABLE parameter_sets (parameter_set_sha256 TEXT PRIMARY KEY, parameters_json TEXT NOT NULL);
CREATE TABLE parameter_values (parameter_set_sha256 TEXT NOT NULL REFERENCES parameter_sets,
 field_id TEXT NOT NULL, json_type TEXT NOT NULL, value_json TEXT NOT NULL, numeric_value REAL, text_value TEXT,
 PRIMARY KEY(parameter_set_sha256,field_id)) WITHOUT ROWID;
CREATE TABLE epochs (epoch_uuid TEXT PRIMARY KEY, block_uuid TEXT NOT NULL REFERENCES epoch_blocks,
 export_uuid TEXT NOT NULL REFERENCES export_metadata,
 source_sha256 TEXT NOT NULL REFERENCES sources, epoch_number INTEGER,
 start_time TEXT, end_time TEXT, duration_seconds REAL,
 metadata_fingerprint TEXT NOT NULL, metadata_fingerprint_version INTEGER NOT NULL,
 included INTEGER NOT NULL CHECK(included=1), review_state TEXT NOT NULL, curation_revision INTEGER NOT NULL,
 curation_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
 parameter_set_sha256 TEXT NOT NULL REFERENCES parameter_sets);
CREATE TABLE frozen_records (epoch_uuid TEXT PRIMARY KEY REFERENCES epochs,
 codec TEXT NOT NULL CHECK(codec='zlib-json'), raw_size INTEGER NOT NULL CHECK(raw_size>0),
 record_sha256 TEXT NOT NULL, payload BLOB NOT NULL);
CREATE TABLE streams (stream_uuid TEXT PRIMARY KEY, epoch_uuid TEXT NOT NULL REFERENCES epochs,
 kind TEXT NOT NULL CHECK(kind IN ('responses','stimuli')), device TEXT NOT NULL,
 h5_path TEXT NOT NULL, data_path TEXT, sample_rate REAL, sample_rate_units TEXT,
 sample_count INTEGER, units TEXT, metadata_json TEXT NOT NULL);
CREATE TABLE epoch_tags (epoch_uuid TEXT NOT NULL REFERENCES epochs, tag TEXT NOT NULL,
 PRIMARY KEY(epoch_uuid,tag));
CREATE TABLE shared_annotations (target_kind TEXT NOT NULL CHECK(target_kind IN ('cell','epoch')),
 target_uuid TEXT NOT NULL, profile_uuid TEXT NOT NULL, author_name TEXT NOT NULL,
 tag TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 PRIMARY KEY(target_kind,target_uuid,profile_uuid,tag));
CREATE TABLE annotation_revisions (target_kind TEXT NOT NULL CHECK(target_kind IN ('cell','epoch')),
 target_uuid TEXT NOT NULL, profile_uuid TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 PRIMARY KEY(target_kind,target_uuid,profile_uuid));
CREATE VIEW epoch_parameters AS SELECT e.epoch_uuid,p.field_id,p.json_type,p.value_json,p.numeric_value,p.text_value
 FROM epochs e JOIN parameter_values p USING(parameter_set_sha256);
CREATE INDEX epochs_parameters ON epochs(parameter_set_sha256);
CREATE INDEX epochs_block ON epochs(block_uuid);
CREATE INDEX blocks_group ON epoch_blocks(group_uuid);
CREATE INDEX groups_cell ON epoch_groups(cell_uuid);
CREATE INDEX cells_type ON cells(cell_type);
CREATE INDEX streams_epoch ON streams(epoch_uuid);
CREATE INDEX parameters_field_value ON parameter_values(field_id,numeric_value,text_value);
CREATE TABLE example_queries (name TEXT PRIMARY KEY, description TEXT NOT NULL, sql TEXT NOT NULL);
CREATE TABLE documentation (name TEXT PRIMARY KEY, content TEXT NOT NULL);
CREATE VIEW epoch_overview AS
 SELECT e.epoch_uuid,c.cell_uuid,c.cell_label,c.cell_type,c.recording_date,
 g.group_uuid,g.group_label,b.block_uuid,b.acquisition_protocol,e.start_time,
 e.duration_seconds,e.epoch_number,e.review_state,c.source_sha256,s.source_path
 FROM epochs e JOIN epoch_blocks b USING(block_uuid) JOIN epoch_groups g USING(group_uuid)
 JOIN cells c USING(cell_uuid) JOIN sources s USING(source_sha256);
'''
TABLES = ('export_metadata', 'sources', 'cells', 'epoch_groups', 'epoch_blocks',
          'epochs', 'streams', 'epoch_tags', 'shared_annotations', 'annotation_revisions', 'parameter_sets', 'parameter_values', 'frozen_records', 'example_queries', 'documentation')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _uuid(value):
    try:
        normalized = str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError('Missing or malformed SQLite export UUID') from error
    if normalized != value:
        raise ValueError('SQLite export UUIDs must be canonical')
    return normalized


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid source SHA256')
    return value


def _fingerprint(record, version):
    details = {key: record[key] for key in ('parameters', 'properties', 'attributes', 'metadata')}
    if version == 2:
        content = {'epoch': details, 'source_sha256': record['source_sha256']}
    elif version == 1:
        content = details['metadata']['epoch']
    else:
        raise ValueError('Unsupported metadata fingerprint version')
    return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()


# The audit copy is lossless and distinct from the queryable metadata columns.
# Limit decoding so a damaged or untrusted artifact cannot expand without bound.
MAX_RECORD_BYTES = 64 * 1024 * 1024


def load_frozen_record(connection, epoch_uuid):
    version = connection.execute('SELECT schema_version FROM export_metadata').fetchone()[0]
    if version == 1:
        row = connection.execute('SELECT record_json FROM epochs WHERE epoch_uuid=?', (epoch_uuid,)).fetchone()
        if row is None:
            raise ValueError('Missing frozen epoch record')
        return json.loads(row[0])
    if version != 2:
        raise ValueError('Unsupported frozen-record schema')
    row = connection.execute('SELECT codec,raw_size,record_sha256,payload FROM frozen_records WHERE epoch_uuid=?', (epoch_uuid,)).fetchone()
    if row is None or row[0] != 'zlib-json' or type(row[1]) is not int or not 0 < row[1] <= MAX_RECORD_BYTES:
        raise ValueError('Missing or invalid frozen epoch archive')
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(row[3], row[1] + 1)
        if len(raw) != row[1] or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Frozen epoch archive size mismatch')
        if hashlib.sha256(raw).hexdigest() != row[2]:
            raise ValueError('Frozen epoch archive checksum mismatch')
        return json.loads(raw)
    except (zlib.error, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise ValueError('Invalid frozen epoch archive') from error


def _parameter_leaves(value, path=('parameters',)):
    # Export every value; interactive discovery limits must not discard data.
    if isinstance(value, dict) and value:
        for key, child in sorted(value.items()):
            yield from _parameter_leaves(child, (*path, str(key)))
    else:
        yield field_id(path), value


def _cell_date(metadata):
    value = metadata.get('start_time')
    if not value:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(str(value)[:10], fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Unrecognized cell start timestamp')


def build_sqlite_export(package, output_path):
    """Publish one complete SQLite snapshot atomically, never replace a file."""
    if not isinstance(package, dict) or package.get('format') != 'recording-reference-package' or package.get('version') != 1:
        raise ValueError('SQLite export requires a frozen reference package')
    recipe = verify(package['recipe'])
    if recipe.get('format') != 'recording-export-recipe' or recipe.get('version') != 1:
        raise ValueError('SQLite export requires a sealed export recipe')
    members = member_map(recipe)
    snapshot = verify(recipe['query_snapshot'])
    query_members = member_map(snapshot)
    if any(snapshot.get(key) != recipe.get(key) for key in ('project_uuid','protocol_uuid','query_sha256','catalog_ref')):
        raise ValueError('Export recipe and query snapshot have different scope')
    if any(key not in query_members or member != query_members[key] for key, member in members.items()):
        raise ValueError('Export membership differs from its frozen query snapshot')
    records = package['epochs']
    if not isinstance(records, list):
        raise ValueError('Frozen epochs must be an array')
    ids = [_uuid(record['epoch_uuid']) for record in records]
    if not ids or len(set(ids)) != len(ids) or set(ids) != set(members):
        raise ValueError('SQLite package must contain exactly the frozen export membership')
    export_uuid, project_uuid, protocol_uuid = map(_uuid, (recipe['export_uuid'], recipe['project_uuid'], recipe['protocol_uuid']))
    version = recipe['query_snapshot'].get('metadata_fingerprint_version', 1)
    sources = {}
    for source in package['sources']:
        identity = _sha(source['source_sha256'])
        if identity in sources or not isinstance(source.get('source_path'), str) or not source['source_path']:
            raise ValueError('Duplicate source identity or missing source path')
        sources[identity] = source['source_path']
    details = {}
    used_sources = set()
    for record in records:
        identity = record['epoch_uuid']
        source_sha = _sha(record['source_sha256'])
        if source_sha not in sources or source_sha not in recipe['source_revisions']:
            raise ValueError('Epoch references an unrecorded source identity')
        reference = record.get('source_reference', {})
        if reference.get('sha256') != source_sha or reference.get('path') != sources[source_sha]:
            raise ValueError('Epoch source pointer differs from frozen source registration')
        if _fingerprint(record, version) != members[identity]['metadata_hash']:
            raise ValueError('Frozen epoch metadata fingerprint mismatch')
        for level, key in (('cell', 'cell_uuid'), ('group', 'group_uuid'), ('block', 'block_uuid'), ('epoch', 'epoch_uuid')):
            value = _uuid(record[key])
            recorded = record['metadata'].get(level, {}).get('uuid')
            if recorded is not None and recorded != value:
                raise ValueError('Source hierarchy identity differs from the frozen epoch')
        curation = record['curation']
        if curation.get('included') is not True or not isinstance(curation.get('tags'), list):
            raise ValueError('Exported epochs must have an included frozen curation state')
        if any(not isinstance(tag, str) for tag in curation['tags']) or len(set(curation['tags'])) != len(curation['tags']):
            raise ValueError('Frozen tags must be distinct strings')
        if type(curation.get('revision')) is not int or curation['revision'] < 0:
            raise ValueError('Invalid frozen curation revision')
        if curation.get('review_state') not in {'unreviewed', 'approved'}:
            raise ValueError('Invalid frozen review state')
        details[identity] = {key: record[key] for key in ('parameters', 'properties', 'attributes', 'metadata')}
        used_sources.add(source_sha)
    shared_annotations = frozen_annotation_entries(records)
    path = Path(output_path)
    if path.exists():
        raise ValueError('SQLite artifact already exists; refusing overwrite')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sqlite-export-', suffix='.db', dir=path.parent)
    os.close(fd)
    connection = None
    try:
        connection = sqlite3.connect(temporary)
        # 8 KiB pages reduce overflow/unused space for the metadata + archive workload.
        connection.execute('PRAGMA page_size=8192')
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        connection.execute('PRAGMA application_id=1381452627')
        connection.executescript(SCHEMA)
        with connection:
            connection.execute('INSERT INTO export_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (export_uuid,project_uuid,protocol_uuid,FORMAT,SCHEMA_VERSION,recipe['created_at'],recipe['actor'],
                 recipe['catalog_ref'],_json(recipe),_json(recipe['query']),recipe['content_sha256'],
                 hashlib.sha256(_json(package).encode()).hexdigest(),COMPATIBILITY,'lazy H5 references; no sampled waveform rows'))
            connection.executemany('INSERT INTO sources VALUES (?,?)', [(sha,sources[sha]) for sha in sorted(used_sources)])
            connection.executemany('INSERT INTO example_queries VALUES (?,?,?)', [
                ('cells', 'Cells grouped by the exact recorded cell type', 'SELECT cell_type, count(*) AS cells FROM cells GROUP BY cell_type'),
                ('epochs', 'Selected epochs with recording and cell context', 'SELECT * FROM epoch_overview ORDER BY recording_date,cell_label,start_time'),
                ('parameters', 'Recorded frequency cutoff (no inferred condition labels)', "SELECT p.epoch_uuid,p.numeric_value AS frequency_cutoff FROM epoch_parameters p WHERE p.field_id='parameters/frequencyCutoff'"),
                ('streams', 'Join lazy stream pointers to the original source file', 'SELECT st.*,s.source_sha256,s.source_path FROM streams st JOIN epochs e USING(epoch_uuid) JOIN sources s USING(source_sha256)'),
                ('blocks', 'Acquisition blocks remain separate even when settings repeat', 'SELECT c.cell_uuid,b.block_uuid,b.start_time,count(*) AS epochs FROM epochs e JOIN epoch_blocks b USING(block_uuid) JOIN epoch_groups g USING(group_uuid) JOIN cells c USING(cell_uuid) GROUP BY c.cell_uuid,b.block_uuid ORDER BY c.cell_uuid,b.start_time'),
                ('settings', 'Exact shared settings; a parameter set is not an inferred scientific condition', 'SELECT parameter_set_sha256,count(*) AS epochs FROM epochs GROUP BY parameter_set_sha256'),
                ('stimulus_recipes', 'Recorded stimulus generator metadata, not regenerated current samples', "SELECT epoch_uuid,device,metadata_json FROM streams WHERE kind='stimuli'"),
                ('tags', 'Frozen protocol tags and acquisition identity', 'SELECT * FROM epoch_tags ORDER BY epoch_uuid,tag')])
            connection.executemany('INSERT INTO documentation VALUES (?,?)', [
                ('README', COMPATIBILITY + '\nOpen with sqlite3 or Python sqlite3.connect(file_uri+"?mode=ro",uri=True).\nStart with example_queries and epoch_overview. Original H5 source files must remain accessible; verify source_sha256 before reading. Waveform sample units/rate/path are recorded per stream. Do not infer drug identity from group labels. IDs are stable UUIDs; date/cell labels are display metadata. Missing metadata remains NULL; arrays/large integer parameters remain exact value_json. Shared parameter_sets are deduplicated by exact typed JSON; epoch_parameters is a query-compatible view. A parameter set is NOT a scientific condition: choose grouping fields explicitly and preserve acquisition block boundaries. cells.recording_date comes from cell start, not epoch day. Stimulus streams with no data_path carry generator metadata only; reconstruction requires a validated adapter with exact generator version, seed and units. No cleaned voltage, inferred drug phases or fitted results are manufactured. frozen_records holds zlib-compressed UTF-8 JSON with decoded byte count and SHA256 for lossless audit; use load_frozen_record in workspace_sqlite.py. Queryable metadata remains plain SQL/JSON. Mutation triggers protect exported tables against accidental changes but are not tamper-proof. Create separate analysis tables/database for derived results.'),
                ('schema', SCHEMA), ('provenance', _json({'recipe_sha256':recipe['content_sha256'], 'query_sha256':recipe['query_sha256'], 'query_snapshot_uuid':snapshot['snapshot_uuid']}))])
            seen = {name: {} for name in ('cells','epoch_groups','epoch_blocks')}
            def ancestor(table, row):
                old = seen[table].get(row[0])
                if old is not None and old != row:
                    raise ValueError('Conflicting source hierarchy metadata for a stable UUID')
                if old is None:
                    connection.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})",row)
                    seen[table][row[0]] = row
            parameter_sets = set()
            for record in records:
                parameters_json = _json(record['parameters'])
                parameter_sha = hashlib.sha256(parameters_json.encode()).hexdigest()
                if parameter_sha not in parameter_sets:
                    connection.execute('INSERT INTO parameter_sets VALUES (?,?)', (parameter_sha,parameters_json))
                    for field,value in _parameter_leaves(record['parameters']):
                        kind = 'null' if value is None else 'boolean' if type(value) is bool else 'number' if type(value) in (int,float) else 'string' if isinstance(value,str) else 'object' if isinstance(value,dict) else 'array'
                        numeric = value if kind=='number' and abs(value) <= 2**53 - 1 else None
                        connection.execute('INSERT INTO parameter_values VALUES (?,?,?,?,?,?)',
                            (parameter_sha,field,kind,_json(value),numeric,value if kind=='string' else None))
                    parameter_sets.add(parameter_sha)
                identity, meta, curation = record['epoch_uuid'],record['metadata'],record['curation']
                ancestor('cells',(record['cell_uuid'],record['source_sha256'],record.get('cell_label'),
                    record.get('cell_type'),_cell_date(meta.get('cell',{})),_json(meta.get('cell',{}))))
                ancestor('epoch_groups',(record['group_uuid'],record['cell_uuid'],record.get('group_label'),_json(meta.get('group',{}))))
                ancestor('epoch_blocks',(record['block_uuid'],record['group_uuid'],record['protocol_name'],
                    record.get('block_start_time',meta.get('block',{}).get('start_time')),record.get('block_end_time',meta.get('block',{}).get('end_time')),_json(meta.get('block',{}))))
                connection.execute('INSERT INTO epochs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,record['block_uuid'],export_uuid,record['source_sha256'],record.get('epoch_number'),record.get('start_time'),
                     meta['epoch'].get('end_time'),record.get('duration_seconds'),members[identity]['metadata_hash'],version,
                     1,curation['review_state'],curation['revision'],_json(curation),_json(details[identity]),parameter_sha))
                raw_record = _json(record).encode()
                if len(raw_record) > MAX_RECORD_BYTES:
                    raise ValueError('Frozen epoch archive exceeds size limit')
                connection.execute('INSERT INTO frozen_records VALUES (?,?,?,?,?)',
                    (identity,'zlib-json',len(raw_record),hashlib.sha256(raw_record).hexdigest(),zlib.compress(raw_record)))
                for stream in record['streams']:
                    stream_id = _uuid(stream['uuid'])
                    if stream['kind'] not in {'responses','stimuli'} or not isinstance(stream.get('h5_path'),str) or not stream['h5_path']:
                        raise ValueError('Stream requires a valid kind and lazy H5 pointer')
                    raw = meta['epoch'].get(stream['kind'],{}).get(stream['device'],{})
                    if raw.get('uuid') is not None and raw['uuid'] != stream_id:
                        raise ValueError('Stream UUID differs from source metadata')
                    connection.execute('INSERT INTO streams VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (stream_id,identity,stream['kind'],stream['device'],stream['h5_path'],stream.get('data_path'),
                         stream.get('sample_rate'),stream.get('sample_rate_units'),stream.get('sample_count'),
                         stream.get('units') if stream.get('units') is not None else raw.get('units'),_json(raw)))
                connection.executemany('INSERT INTO epoch_tags VALUES (?,?)',[(identity,tag) for tag in curation['tags']])
            for entry in shared_annotations:
                kind, key = entry['target_kind'], entry['target_uuid']
                connection.executemany('INSERT INTO shared_annotations VALUES (?,?,?,?,?,?)',
                    [(kind,key,tag['profile_uuid'],tag['author_name'],tag['tag'],tag['revision']) for tag in entry['tags']])
                connection.executemany('INSERT INTO annotation_revisions VALUES (?,?,?,?)',
                    [(kind,key,author,revision) for author,revision in entry['revisions'].items()])
            connection.execute('INSERT INTO documentation VALUES (?,?)', ('shared_annotations',
                'Optional v2 additive extension: shared_annotations preserves exact cell/epoch targets, author profile UUID/name and tag-set revision. Cell tags inherit by the cells→epoch_overview UUID join; they are not copied into epoch_tags. epoch_tags remains protocol-specific curation. annotation_revisions preserves empty tag-set revisions. frozen_records retains the complete per-epoch annotations snapshot.'))
            connection.execute('INSERT INTO example_queries VALUES (?,?,?)', ('shared_tags',
                'Direct and cell-inherited authored tags for each exported epoch',
                "SELECT e.epoch_uuid,a.* FROM epoch_overview e JOIN shared_annotations a ON (a.target_kind='epoch' AND a.target_uuid=e.epoch_uuid) OR (a.target_kind='cell' AND a.target_uuid=e.cell_uuid)"))
            connection.execute('INSERT INTO documentation VALUES (?,?)', ('external_tag_return',
                'Rieke app exports include annotation-return.json beside recordings.sqlite, with exact targets and a message example. '
                'To add live project tags, write a complete JSON file to annotations/incoming/<message_uuid>.json beside this database. '
                'Envelope: {format:"rieke-external-tags",version:1,message_uuid:<fresh UUID>,export_uuid:<this export UUID>,document:{'
                'format:"rieke-tag-exchange",version:1,project_uuid:<this project UUID>,entries:[{target_kind:"epoch" or "cell",'
                'target_uuid:<exact acquisition UUID>,source_sha256:<source hash>,tags:[{tag:<text>,profile_uuid:<stable author UUID>,author_name:<name>}]}]}}. '
                'Publish via a temporary file and atomic rename. Keep this database unchanged. '
                'The project page automatically scans the original export folder on open and while visible; receipts appear in annotations/receipts. '
                'Tags are additive; cell tags inherit to all epochs of that cell. Copied databases need their completed messages delivered to the original export folder. '
                'Current tags are available through the project annotation API; this database preserves the export-time snapshot.'))
            # This is an immutable handoff snapshot, not the lab's mutable master.
            # Owners can deliberately remove these guards; this is not tamper-proof storage.
            for table in TABLES:
                for action in ('INSERT','UPDATE','DELETE'):
                    connection.execute(f"CREATE TRIGGER freeze_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable export snapshot'); END")
        if connection.execute('PRAGMA foreign_key_check').fetchall() or connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity validation failed')
        counts = {table: connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
        if {row[0] for row in connection.execute('SELECT epoch_uuid FROM epochs')} != set(members):
            raise ValueError('SQLite membership verification failed')
        connection.close(); connection = None
        with open(temporary,'rb') as handle:
            os.fsync(handle.fileno())
        os.link(temporary,path)
        return {'path':str(path),'schema_version':SCHEMA_VERSION,'format':FORMAT,'counts':counts,'compatibility':COMPATIBILITY}
    except sqlite3.IntegrityError as error:
        raise ValueError('SQLite export violates identity or hierarchy integrity: '+str(error)) from error
    finally:
        if connection is not None:
            connection.close()
        Path(temporary).unlink(missing_ok=True)
