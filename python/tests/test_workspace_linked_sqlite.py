"""Real SQLite/H5 and an isolated standalone loader; no user projects."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile

import h5py
import numpy as np

from disco.workbench.recipes import capture_query, prepare_export
from linked_export_loader import LinkedExport, DETAIL_KEYS, metadata_records
from workspace_linked_sqlite import prepare_linked_package, build_linked_sqlite_export, build_linked_export_bundle
from workspace_sqlite import build_sqlite_export, _fingerprint
if __package__:
    from .test_workspace_api import FixtureService
else:
    from test_workspace_api import FixtureService


def linked_fixture(root, service=None, *, epoch_count=2, parameter_array_size=10000):
    project = service.project_dir if service is not None else Path(root) / 'project'
    project.mkdir(exist_ok=True)
    service = service or FixtureService(project)
    if epoch_count != 2:
        template = copy.deepcopy(next(iter(service.rows.values())))
        namespace = uuid.UUID('f931a656-1710-4e6b-b154-1b1180d08a85')
        identity = lambda label: str(uuid.uuid5(namespace, label))
        service.ids = [identity('epoch/' + str(index)) for index in range(epoch_count)]
        service.rows, service.cells = {}, {}
        for index, key in enumerate(service.ids):
            block = index % 106
            group, cell = block % 22, block % 11
            date = dt.datetime(2026, 9, 24, 12) + dt.timedelta(seconds=index)
            row = {**copy.deepcopy(template), 'epoch_uuid': key, 'cell_uuid': identity('cell/' + str(cell)),
                   'cell_label': 'Cell' + str(cell + 1), 'group_uuid': identity('group/' + str(group)),
                   'block_uuid': identity('block/' + str(block)), 'epoch_number': index // 106 + 1,
                   'start_time': date.strftime('%m/%d/%Y %H:%M:%S:%f'),
                   'block_start_time': (dt.datetime(2026, 9, 24, 12) + dt.timedelta(seconds=block)).strftime('%m/%d/%Y %H:%M:%S:%f')}
            service.rows[key] = row
            service.cells[row['cell_uuid']] = {'cell_uuid': row['cell_uuid'], 'label': row['cell_label'], 'cell_type': row['cell_type'], 'date': row['date'], 'start_time': '09/24/2026 12:00:00:000000'}
        service.cell_ids = list(service.cells)
    (project / 'project.json').write_text(json.dumps({'format': 'recording-project', 'version': 1, **service.project}))
    raw = project / 'raw-uploads' / 'fixture.h5'
    raw.parent.mkdir(exist_ok=True)
    cells, groups, blocks = {}, {}, {}
    with h5py.File(raw, 'w') as h5:
        for index, key in enumerate(service.ids):
            row = service.rows[key]
            block = h5.require_group('/blocks/' + row['block_uuid'])
            block.attrs['uuid'] = row['block_uuid']
            epoch = block.require_group('epochs/' + key)
            epoch.attrs['uuid'] = key
            response_id = str(uuid.uuid4())
            stream = epoch.require_group('responses/' + response_id)
            stream.attrs['uuid'] = response_id
            stream.attrs['sampleRate'] = 10000.0
            data = np.zeros(200, dtype=[('quantity', 'f8'), ('units', 'S8')])
            data['quantity'] = np.arange(200) / 7
            data['units'] = b'mV'
            stream.create_dataset('data', data=data)
            row['streams'] = [{'uuid': response_id, 'device': 'Amp1', 'kind': 'responses',
                              'h5_path': stream.name, 'data_path': stream.name + '/data',
                              'sample_rate': 10000.0, 'sample_rate_units': 'Hz', 'sample_count': 200, 'units': 'mV'}]
            parameters = {'condition': index % 3, 'large': list(range(parameter_array_size)), 'ticks': 639258608779858225,
                          'array': [1, '2', None], 'boolean': True,
                          **{'parameter_' + str(n): index if n == 0 else n / 7 for n in range(42)}}
            ep = {'uuid': key, 'start_time': row['start_time'], 'parameters': parameters,
                  'properties': {}, 'attributes': {'ticks': parameters['ticks']}}
            if row['cell_uuid'] not in cells:
                cells[row['cell_uuid']] = {'uuid': row['cell_uuid'], 'label': row['cell_label'], 'type': row['cell_type'],
                                          'start_time': '09/24/2026 12:00:00:000000', 'epoch_groups': []}
            if row['group_uuid'] not in groups:
                groups[row['group_uuid']] = {'uuid': row['group_uuid'], 'label': row['group_label'], 'epoch_blocks': []}
                cells[row['cell_uuid']]['epoch_groups'].append(groups[row['group_uuid']])
            if row['block_uuid'] not in blocks:
                blocks[row['block_uuid']] = {'uuid': row['block_uuid'], 'protocolID': 'example', 'start_time': row['block_start_time'], 'epochs': []}
                groups[row['group_uuid']]['epoch_blocks'].append(blocks[row['block_uuid']])
            blocks[row['block_uuid']]['epochs'].append(ep)
    source_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    doc = {'uuid': str(uuid.uuid4()), 'animals': [{'preparations': [{'cells': list(cells.values())}]}]}
    metadata = project / 'imports' / 'fixture' / 'metadata.catalog.json'
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(doc))
    metadata_sha = hashlib.sha256(metadata.read_bytes()).hexdigest()
    service.details = dict(metadata_records(doc))
    for row in service.rows.values():
        row['source_sha256'] = source_sha
    service.sources = [{'source_sha256': source_sha, 'source_path': str(raw), 'metadata': {'uuid': doc['uuid']}}]
    service.manifests = {source_sha: {'source_sha256': source_sha, 'source_path': str(raw),
                                     'metadata_path': str(metadata), 'metadata_sha256': metadata_sha,
                                     'source_size': raw.stat().st_size}}
    service._source_signatures = {}
    (metadata.parent / 'import-manifest.json').write_text(json.dumps(service.manifests[source_sha]))
    service._fingerprints = {key: _fingerprint({**service.rows[key], **service.details[key]}, 2) for key in service.ids}
    result = service.protocols[service.protocol_id]['result']
    result['source_revisions'] = [source_sha]
    result['epochs'] = [{'uuid': key, 'metadata_hash': service._fingerprints[key]} for key in service.ids]
    result['metadata_fingerprint_version'] = 2
    snapshot = capture_query(service.protocols[service.protocol_id]['definition'], result, str(project / 'catalog.json'))
    recipe = prepare_export(snapshot, service.ids, destination='linked-sqlite', review_policy='include_unreviewed',
                            actor='fixture', options={'split_order': 'parameters/condition,cell'})
    records = [service.epoch(key) for key in service.ids]
    for row in records:
        row['curation']['tags'] = ['frozen tag']
    package = {'format': 'recording-reference-package', 'version': 1, 'recipe': recipe,
               'epochs': records, 'sources': service.sources}
    return service, prepare_linked_package(package, service.manifests, project, grouping_sources=service.sources)


class LinkedSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.service, self.package = linked_fixture(self.root)
        self.path = self.root / 'linked.sqlite'

    def build(self):
        return build_linked_sqlite_export(self.package, self.path)

    def test_exact_metadata_groups_decisions_sql_and_smaller_database(self):
        before = copy.deepcopy(self.package)
        with patch('h5py.File', side_effect=AssertionError('Export must not open H5')):
            self.build()
        with LinkedExport(self.path) as export:
            self.assertEqual(export.describe()['counts']['epochs'], 2)
            self.assertEqual(export.query('SELECT count(*) AS n FROM epoch_groups'), [{'n': 2}])
            self.assertEqual(export.query('SELECT epoch_count FROM analysis_groups WHERE depth=1'),
                             [{'epoch_count': 1}, {'epoch_count': 1}])
            for row in self.package['epochs']:
                self.assertEqual(export.record(row['epoch_uuid']), row)
                value = export.query('SELECT epoch_parameters(?) AS p', (row['epoch_uuid'],))[0]['p']
                self.assertEqual(json.loads(value), row['parameters'])
            with self.assertRaises(sqlite3.DatabaseError):
                export.query('DELETE FROM epochs')
            with self.assertRaises(sqlite3.DatabaseError):
                export.query('ATTACH DATABASE ? AS side_effect', (str(self.root / 'unwanted.sqlite'),))
            self.assertFalse((self.root / 'unwanted.sqlite').exists())
            self.assertEqual(export.query('SELECT tag FROM epoch_tags'), [{'tag': 'frozen tag'}] * 2)
            detached = export.record(self.service.ids[0])
            detached['parameters']['condition'] = 'analysis-only edit'
            self.assertEqual(export.record(self.service.ids[0])['parameters']['condition'], 0)
        full = self.root / 'full.sqlite'
        build_sqlite_export(self.package, full)
        self.assertLess(self.path.stat().st_size, full.stat().st_size / 2)
        self.assertEqual(self.package, before)

    def test_metadata_change_and_missing_file_fail_closed(self):
        self.build()
        path = Path(self.package['sources'][0]['metadata_path'])
        original = path.read_bytes()
        with LinkedExport(self.path) as export:
            export.record(self.service.ids[0])
            path.write_bytes(original + b' ')
            with self.assertRaisesRegex(ValueError, 'changed'):
                export.record(self.service.ids[0])
        with LinkedExport(self.path) as export:
            with self.assertRaisesRegex(ValueError, 'changed'):
                export.record(self.service.ids[0])
        path.unlink()
        with LinkedExport(self.path) as export, self.assertRaises(FileNotFoundError):
            export.record(self.service.ids[0])

    def test_exact_recorded_sample_window_and_wrong_stream_rejected(self):
        self.build()
        row = self.package['epochs'][0]
        stream = row['streams'][0]
        with LinkedExport(self.path) as export:
            trace = export.read_trace(row['epoch_uuid'], stream['uuid'], start=13, count=17)
            self.assertEqual(trace['values'], (np.arange(13, 30) / 7).tolist())
            self.assertEqual(trace['time_seconds'], (np.arange(13, 30) / 10000).tolist())
            self.assertEqual(trace['units'], 'mV')
            with self.assertRaisesRegex(ValueError, 'Choose an exported'):
                export.read_trace(row['epoch_uuid'], self.package['epochs'][1]['streams'][0]['uuid'])
            for start, count in ((True, 1), (0, 20001), (-1, 2), (200, 1)):
                with self.subTest(start=start, count=count), self.assertRaises(ValueError):
                    export.read_trace(row['epoch_uuid'], stream['uuid'], start=start, count=count)

    def test_relocated_project_and_explicit_map_require_same_content(self):
        self.build()
        moved = self.root / 'moved-project'
        self.service.project_dir.rename(moved)
        key = self.service.ids[0]
        with LinkedExport(self.path, project_root=moved) as export:
            self.assertEqual(export.record(key), self.package['epochs'][0])
            stream = self.package['epochs'][0]['streams'][0]['uuid']
            self.assertEqual(export.read_trace(key, stream, count=2)['count'], 2)
        old = self.package['sources'][0]['metadata_path']
        mapping = {old: str(moved / Path(old).relative_to(self.service.project_dir))}
        with LinkedExport(self.path, file_map=mapping) as export:
            self.assertEqual(export.record(key)['epoch_uuid'], key)

    def test_h5_change_is_rejected_before_and_during_session(self):
        self.build()
        row = self.package['epochs'][0]
        source = Path(self.package['sources'][0]['source_path'])
        with LinkedExport(self.path) as export:
            export.read_trace(row['epoch_uuid'], row['streams'][0]['uuid'], count=2)
            with source.open('ab') as handle:
                handle.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                export.read_trace(row['epoch_uuid'], row['streams'][0]['uuid'], count=2)
        with LinkedExport(self.path) as export, self.assertRaisesRegex(ValueError, 'checksum'):
            export.read_trace(row['epoch_uuid'], row['streams'][0]['uuid'], count=2)

    def test_changed_frozen_sql_tables_are_rejected(self):
        self.build()
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TRIGGER freeze_epoch_tags_update')
            db.execute("UPDATE epoch_tags SET tag='changed'")
        with self.assertRaisesRegex(ValueError, 'Frozen SQLite tables changed'):
            LinkedExport(self.path)

    def test_changed_catalog_or_incomplete_membership_never_publishes(self):
        for change in ('metadata', 'members', 'duplicate'):
            package = copy.deepcopy(self.package)
            if change == 'metadata':
                package['epochs'][0]['parameters']['condition'] = 100
            elif change == 'members':
                package['epochs'].pop()
            else:
                package['epochs'].append(package['epochs'][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_linked_sqlite_export(package, self.path)
            self.assertFalse(self.path.exists())

    def test_numerically_equal_but_different_metadata_types_do_not_publish(self):
        metadata = Path(self.package['sources'][0]['metadata_path'])
        document = json.loads(metadata.read_text())
        epoch = document['animals'][0]['preparations'][0]['cells'][0]['epoch_groups'][0]['epoch_blocks'][0]['epochs'][0]
        epoch['parameters']['boolean'] = 1
        metadata.write_text(json.dumps(document))
        self.package['sources'][0]['metadata_sha256'] = hashlib.sha256(metadata.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'exact frozen epoch'):
            self.build()
        self.assertFalse(self.path.exists())

    def test_bundle_contains_standalone_loader_and_no_copied_metadata(self):
        output = self.root / 'export'
        artifact = build_linked_export_bundle(self.package, output)
        with zipfile.ZipFile(artifact) as archive:
            self.assertEqual(set(archive.namelist()), {'recordings.sqlite', 'linked_export_loader.py', 'README.md', 'requirements.txt'})
            folder = self.root / 'analysis'
            archive.extractall(folder)
        result = subprocess.run([sys.executable, '-I', str(folder / 'linked_export_loader.py'),
                                 str(folder / 'recordings.sqlite'), '--epoch', self.service.ids[0]],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), self.package['epochs'][0])
        self.assertFalse((output / 'recordings.json').exists())

    def test_downloads_source_cannot_be_a_linked_export_dependency(self):
        raw = Path(self.service.sources[0]['source_path'])
        outside = self.root / 'Downloads' / raw.name
        outside.parent.mkdir()
        shutil.copyfile(raw, outside)
        package = copy.deepcopy(self.package)
        package['sources'][0]['source_path'] = str(outside)
        manifests = copy.deepcopy(self.service.manifests)
        next(iter(manifests.values()))['source_path'] = str(outside)
        with self.assertRaisesRegex(ValueError, 'managed H5'):
            prepare_linked_package(package, manifests, self.service.project_dir)


if __name__ == '__main__':
    unittest.main()
