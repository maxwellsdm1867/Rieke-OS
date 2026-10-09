"""Compact internal-use SQLite references to existing sealed import metadata."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from disco.workbench.recipes import build_tree
from disco.navigation.tree import catalog
from linked_export_loader import FORMAT, VERSION, DETAIL_KEYS, canonical, verified_metadata, database_seal, signature
from workspace_sqlite import validate_sqlite_package

SCHEMA = '''
CREATE TABLE export_info (format TEXT NOT NULL, version INTEGER NOT NULL,
 export_uuid TEXT PRIMARY KEY, project_uuid TEXT NOT NULL, project_root TEXT NOT NULL,
 recipe_json TEXT NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE sources (source_sha256 TEXT PRIMARY KEY, source_path TEXT NOT NULL,
 metadata_path TEXT NOT NULL, metadata_sha256 TEXT NOT NULL,
 source_project_relative TEXT, metadata_project_relative TEXT,
 source_workspace_relative TEXT, metadata_workspace_relative TEXT);
CREATE TABLE cells (cell_uuid TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL REFERENCES sources,
 cell_label TEXT, cell_type TEXT, recording_date TEXT);
CREATE TABLE epoch_groups (group_uuid TEXT PRIMARY KEY, cell_uuid TEXT NOT NULL REFERENCES cells, group_label TEXT);
CREATE TABLE epoch_blocks (block_uuid TEXT PRIMARY KEY, group_uuid TEXT NOT NULL REFERENCES epoch_groups,
 acquisition_protocol TEXT NOT NULL, start_time TEXT, end_time TEXT);
CREATE TABLE epochs (epoch_uuid TEXT PRIMARY KEY, block_uuid TEXT NOT NULL REFERENCES epoch_blocks,
 source_sha256 TEXT NOT NULL REFERENCES sources, epoch_number INTEGER, start_time TEXT,
 duration_seconds REAL, metadata_fingerprint TEXT NOT NULL, included INTEGER NOT NULL CHECK(included=1),
 review_state TEXT NOT NULL, curation_revision INTEGER NOT NULL);
CREATE TABLE epoch_records (epoch_uuid TEXT PRIMARY KEY REFERENCES epochs,
 record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL);
CREATE TABLE streams (stream_uuid TEXT PRIMARY KEY, epoch_uuid TEXT NOT NULL REFERENCES epochs,
 kind TEXT NOT NULL CHECK(kind IN ('responses','stimuli')), device TEXT NOT NULL,
 h5_path TEXT NOT NULL, data_path TEXT, sample_rate REAL, sample_rate_units TEXT, sample_count INTEGER, units TEXT);
CREATE TABLE epoch_tags (epoch_uuid TEXT NOT NULL REFERENCES epochs, tag TEXT NOT NULL, PRIMARY KEY(epoch_uuid,tag));
CREATE TABLE shared_annotations (target_kind TEXT NOT NULL, target_uuid TEXT NOT NULL,
 profile_uuid TEXT NOT NULL, author_name TEXT NOT NULL, tag TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(target_kind,target_uuid,profile_uuid,tag));
CREATE TABLE annotation_revisions (target_kind TEXT NOT NULL,target_uuid TEXT NOT NULL,
 profile_uuid TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(target_kind,target_uuid,profile_uuid));
CREATE TABLE analysis_groups (group_id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES analysis_groups,
 depth INTEGER NOT NULL, field_id TEXT NOT NULL, value_json TEXT NOT NULL, missing INTEGER NOT NULL,
 epoch_count INTEGER NOT NULL, cell_count INTEGER NOT NULL);
CREATE TABLE analysis_group_epochs (group_id INTEGER NOT NULL REFERENCES analysis_groups,
 epoch_uuid TEXT NOT NULL REFERENCES epochs, PRIMARY KEY(group_id,epoch_uuid)) WITHOUT ROWID;
CREATE TABLE example_queries (name TEXT PRIMARY KEY,sql TEXT NOT NULL);
CREATE INDEX epochs_block ON epochs(block_uuid);
CREATE INDEX blocks_group ON epoch_blocks(group_uuid);
CREATE INDEX groups_cell ON epoch_groups(cell_uuid);
CREATE VIEW epoch_overview AS SELECT e.*,c.cell_uuid,c.cell_label,c.cell_type,c.recording_date,
 g.group_uuid,g.group_label,b.acquisition_protocol,s.source_path
 FROM epochs e JOIN epoch_blocks b USING(block_uuid) JOIN epoch_groups g USING(group_uuid)
 JOIN cells c USING(cell_uuid) JOIN sources s ON s.source_sha256=e.source_sha256;
'''

README = '''# Disco linked SQLite export

This is a small, frozen selection for internal analysis. It is not a portable
archive: the referenced metadata and H5 files must remain available in their
managed project folders. No waveform samples or full metadata copies are included.
Keep this folder together. Use the full metadata export or project transfer for
sharing with someone who cannot access those project folders.

## Start here

Python 3.11 or newer is required. SQL and metadata need only its standard library.
For recorded samples: `python -m pip install -r requirements.txt`.

    python linked_export_loader.py recordings.sqlite
    python linked_export_loader.py recordings.sqlite --sql "SELECT cell_uuid, count(*) AS epochs FROM epoch_overview GROUP BY cell_uuid"
    python linked_export_loader.py recordings.sqlite --sql "SELECT group_id,field_id,value_json,epoch_count FROM analysis_groups WHERE depth=1"
    python linked_export_loader.py recordings.sqlite --epoch EPOCH_UUID
    python linked_export_loader.py recordings.sqlite --epoch EPOCH_UUID --stream STREAM_UUID --start 0 --count 1000

The placeholders EPOCH_UUID and STREAM_UUID are the exact IDs in `epochs` and
`streams`. The loader accepts only exported epochs and recorded response streams.
Generated stimuli are described by their recorded generator/parameters; this
loader does not invent or regenerate a stimulus waveform.

## Python / agents

    from linked_export_loader import LinkedExport
    with LinkedExport("recordings.sqlite") as export:
        groups = export.query("SELECT * FROM analysis_groups")
        epochs = export.query("SELECT * FROM epoch_overview")
        epoch = export.record(epochs[0]["epoch_uuid"])
        parameters = epoch["parameters"]
        responses = [s for s in epoch["streams"] if s["kind"] == "responses"]
        if responses:
            trace = export.read_trace(epoch["epoch_uuid"], responses[0]["uuid"], count=1000)

With this loader, SQL can fetch metadata lazily:

    export.query("SELECT epoch_uuid, epoch_parameters(epoch_uuid) AS parameters_json FROM epochs LIMIT 5")
    export.query("SELECT epoch_uuid, json_extract(epoch_metadata(epoch_uuid), '$.block.protocolID') AS protocol FROM epochs")

Ordinary SQLite clients can query the stored tables directly. The two custom
functions require the Python loader. `epoch_groups` means acquisition groups;
`analysis_groups` means the frozen export split tree, including typed/missing
values. `analysis_group_epochs` preserves exact membership at every tree level.
Selections, grouping, curation and shared tags are export-time snapshots; later
project edits do not update this file. Store analysis results in a separate file.
This reference bundle does not automatically send annotations back to Disco.

## Relocation and verification

Pass `--project-root /new/project` if this project moved, or
`--workspace-root /new/workspace` if its parent and sibling projects moved.
For other layouts, `--file-map mapping.json` accepts an object mapping exact old
file paths to new paths. These options change locators, never file identities.
The Python constructor accepts the corresponding project_root, workspace_root,
and file_map arguments. An optional expected_sha256 verifies the SQLite file.

The loader checks metadata checksums and epoch fingerprints on demand. The first
read of each H5 checks the full file checksum, which can take time for large
recordings; subsequent windows reuse that verification within the same reader.
Changed or missing files fail rather than returning replacement data. Keep one
reader open for repeated windows. Sample reads are bounded to 20,000 full-rate
samples per call; nonfinite recorded values are represented as null/None.
'''


def prepare_linked_package(package, manifests, project_dir, *, grouping_sources=()):
    """Bind caller-verified import locators, without new membership authority."""
    root = Path(project_dir).resolve(strict=True)
    sources = []
    used = {row['source_sha256'] for row in package['epochs']}
    for source in package['sources']:
        if source['source_sha256'] not in used:
            continue
        manifest = manifests[source['source_sha256']]
        metadata = Path(manifest['metadata_path']).resolve(strict=True)
        raw = Path(source['source_path']).resolve(strict=True)
        if manifest['source_sha256'] != source['source_sha256'] or Path(manifest['source_path']).resolve() != raw:
            raise ValueError('Linked export source differs from its validated import')
        if not metadata.is_relative_to(root / 'imports'):
            raise ValueError('Linked export metadata must belong to this project imports folder')
        from disco.projects.recording_files import managed_recording_owner
        if managed_recording_owner(root, raw) is None:
            raise ValueError('Linked export requires managed H5 files; retain this recording in a project first')
        sources.append({**source, 'metadata_path': str(metadata), 'metadata_sha256': manifest['metadata_sha256']})
    return {**package, 'sources': sources, 'project_root': str(root), 'grouping_sources': list(grouping_sources)}


def build_linked_sqlite_export(package, output_path):
    valid = validate_sqlite_package(package)
    recipe, records = valid['recipe'], valid['records']
    root = Path(package['project_root']).resolve(strict=True)
    sources = {row['source_sha256']: row for row in package['sources']}
    verified, signatures = {}, {}
    for sha in valid['used_sources']:
        source = sources[sha]
        verified[sha], signatures[sha] = verified_metadata(source['metadata_path'], source['metadata_sha256'])
    for row in records:
        details = verified[row['source_sha256']].get(row['epoch_uuid'])
        if canonical(details) != canonical({key: row[key] for key in DETAIL_KEYS}):
            raise ValueError('Existing imported metadata cannot reproduce the exact frozen epoch')
    frozen_fields = recipe.get('options', {}).get('tree_view', {}).get('fields', [])
    fields, values = catalog(records, valid['details'],
        known_fields=[field for field in frozen_fields if isinstance(field, dict)],
        sources=package.get('grouping_sources', ()))
    split = recipe.get('options', {}).get('split_order', ','.join(recipe.get('view', {}).get('group_by', [])))
    tree = build_tree(records, split, values, set(fields) | {field for field in frozen_fields if isinstance(field, str)})
    path = Path(output_path)
    if path.exists():
        raise ValueError('Linked SQLite artifact already exists; refusing overwrite')
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.linked-export-', dir=path.parent)
    os.close(descriptor)
    connection = None
    try:
        connection = sqlite3.connect(temporary)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute(f'PRAGMA user_version={VERSION}')
        connection.executescript(SCHEMA)
        with connection:
            connection.execute('INSERT INTO export_info VALUES (?,?,?,?,?,?,?)',
                (FORMAT, VERSION, recipe['export_uuid'], recipe['project_uuid'], str(root), canonical(recipe), ''))
            def relative(raw, parent):
                p = Path(raw).resolve()
                return str(p.relative_to(parent)) if p.is_relative_to(parent) else None
            for sha in sorted(valid['used_sources']):
                source = sources[sha]
                connection.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                    (sha, source['source_path'], source['metadata_path'], source['metadata_sha256'],
                     relative(source['source_path'], root), relative(source['metadata_path'], root),
                     relative(source['source_path'], root.parent), relative(source['metadata_path'], root.parent)))
            ancestors = {}
            def ancestor(table, row):
                key = (table, row[0])
                if key in ancestors:
                    if ancestors[key] != row:
                        raise ValueError('Conflicting frozen hierarchy metadata')
                    return
                ancestors[key] = row
                connection.execute('INSERT INTO ' + table + ' VALUES (' + ','.join('?' for _ in row) + ')', row)
            for row in records:
                identity, curation = row['epoch_uuid'], row['curation']
                ancestor('cells', (row['cell_uuid'], row['source_sha256'], row.get('cell_label'), row.get('cell_type'), row.get('date')))
                ancestor('epoch_groups', (row['group_uuid'], row['cell_uuid'], row.get('group_label')))
                ancestor('epoch_blocks', (row['block_uuid'], row['group_uuid'], row['protocol_name'], row.get('block_start_time'), row.get('block_end_time')))
                connection.execute('INSERT INTO epochs VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (identity, row['block_uuid'], row['source_sha256'], row.get('epoch_number'), row.get('start_time'),
                     row.get('duration_seconds'), valid['members'][identity]['metadata_hash'], 1,
                     curation['review_state'], curation['revision']))
                small = canonical({key: value for key, value in row.items() if key not in DETAIL_KEYS})
                connection.execute('INSERT INTO epoch_records VALUES (?,?,?)', (identity, small, hashlib.sha256(small.encode()).hexdigest()))
                connection.executemany('INSERT INTO epoch_tags VALUES (?,?)', [(identity, tag) for tag in curation['tags']])
                for stream in row['streams']:
                    connection.execute('INSERT INTO streams VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (stream['uuid'], identity, *(stream.get(key) for key in ('kind', 'device', 'h5_path', 'data_path', 'sample_rate', 'sample_rate_units', 'sample_count', 'units'))))
            for entry in valid['shared_annotations']:
                connection.executemany('INSERT INTO shared_annotations VALUES (?,?,?,?,?,?)',
                    [(entry['target_kind'], entry['target_uuid'], tag['profile_uuid'], tag['author_name'], tag['tag'], tag['revision']) for tag in entry['tags']])
                connection.executemany('INSERT INTO annotation_revisions VALUES (?,?,?,?)',
                    [(entry['target_kind'], entry['target_uuid'], author, revision) for author, revision in entry['revisions'].items()])
            next_group = 0
            def save_groups(node, parent=None, depth=1):
                nonlocal next_group
                if 'epoch_uuids' in node:
                    return node['epoch_uuids']
                members = []
                for child in node['children']:
                    next_group += 1
                    identity = next_group
                    connection.execute('INSERT INTO analysis_groups VALUES (?,?,?,?,?,?,?,?)',
                        (identity, parent, depth, node['field'], canonical(child['value']), int(child['missing']), child['count'], child['cell_count']))
                    ids = save_groups(child, identity, depth + 1)
                    connection.executemany('INSERT INTO analysis_group_epochs VALUES (?,?)', [(identity, key) for key in ids])
                    members.extend(ids)
                return members
            if set(save_groups(tree)) != set(valid['members']):
                raise ValueError('Frozen analysis groups differ from export membership')
            connection.executemany('INSERT INTO example_queries VALUES (?,?)', [
                ('cells', 'SELECT cell_uuid,count(*) AS epochs FROM epoch_overview GROUP BY cell_uuid'),
                ('acquisition_groups', 'SELECT group_uuid,count(*) AS epochs FROM epoch_overview GROUP BY group_uuid'),
                ('analysis_groups', 'SELECT * FROM analysis_groups ORDER BY group_id'),
                ('recordings', 'SELECT * FROM sources'),
                ('responses', "SELECT * FROM streams WHERE kind='responses'"),
            ])
            connection.execute('UPDATE export_info SET content_sha256=?', (database_seal(connection),))
            for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    connection.execute(f"CREATE TRIGGER freeze_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable linked export'); END")
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Linked SQLite integrity validation failed')
        connection.close()
        connection = None
        if any(signature(Path(sources[sha]['metadata_path']).resolve()) != before for sha, before in signatures.items()):
            raise ValueError('Referenced metadata changed while writing the export')
        with open(temporary, 'rb') as handle:
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except sqlite3.IntegrityError as error:
        raise ValueError('Linked SQLite identity or hierarchy integrity failure: ' + str(error)) from error
    finally:
        if connection is not None:
            connection.close()
        Path(temporary).unlink(missing_ok=True)
    return path


def build_linked_export_bundle(package, output):
    """Deliver the database together with its standalone loader and instructions."""
    output = Path(output)
    database = build_linked_sqlite_export(package, output / 'recordings.sqlite')
    target = output / 'linked-recordings.zip'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(database, 'recordings.sqlite')
        archive.write(Path(__file__).with_name('linked_export_loader.py'), 'linked_export_loader.py')
        archive.writestr('README.md', README)
        archive.writestr('requirements.txt', 'numpy>=1.26\nh5py>=3.10\n')
    return target
