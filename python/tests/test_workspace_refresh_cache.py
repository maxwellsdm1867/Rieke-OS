"""Incremental source metadata cache with actual tiny H5 files and fake SQL."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

import h5py
import numpy as np

import workspace_service as module
from workspace_service import WorkspaceService
try:
    from .test_workspace_curation import Table
except ImportError:
    from test_workspace_curation import Table


class RefreshCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        (self.folder/'imports').mkdir()
        (self.folder/'protocols').mkdir()
        self.project, self.protocol = str(uuid.uuid4()), str(uuid.uuid4())
        (self.folder/'project.json').write_text(json.dumps({'project_uuid': self.project, 'name': 'Fixture'}))
        (self.folder/'catalog.json').write_text(json.dumps({'project_uuid': self.project, 'adapter': 'datajoint',
            'database': 'schema', 'connection': {'credential_provider': {'kind': 'docker-container-env', 'container': 'unused-fixture'}}}))
        definition = {'format': 'recording-protocol-workspace', 'version': 1,
            'project_uuid': self.project, 'protocol_uuid': self.protocol, 'name': 'Example', 'catalog_ref': '../catalog.json',
            'query': {'version': 1, 'all': [{'field': 'EpochBlock.protocol_name', 'operator': 'eq', 'value': 'example'}]}}
        (self.folder/'protocols/example.protocol.json').write_text(json.dumps(definition))
        self.sources = Table(('source_sha256',))
        self.records = [self.add_source('one'), self.add_source('two')]
        self.evaluator = Mock(side_effect=self.evaluate)
        for patcher in [patch.object(module, 'connect', return_value=object()),
                        patch.object(module, 'workspace_tables', return_value=(None, self.sources, None, None)),
                        patch.object(module, 'evaluate_protocol_file', self.evaluator)]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = WorkspaceService(self.folder)

    def add_source(self, name):
        identity, cell_id, group_id, block_id, epoch_id, stream_id = [str(uuid.uuid4()) for _ in range(6)]
        source_path = self.folder / (name + '.h5')
        stream_path = f'/block-{block_id}/epochs/epoch-{epoch_id}/responses/stream-{stream_id}'
        with h5py.File(source_path, 'w') as h5:
            block = h5.create_group('/block-' + block_id)
            block.attrs['uuid'] = block_id
            ep = h5.create_group(f'/block-{block_id}/epochs/epoch-{epoch_id}')
            ep.attrs['uuid'] = epoch_id
            stream = h5.create_group(stream_path)
            stream.attrs['uuid'], stream.attrs['sampleRate'] = stream_id, 10000.
            data = np.zeros(30, dtype=[('quantity', 'f8'), ('units', 'S8')])
            data['quantity'], data['units'] = np.arange(30), b'mV'
            stream.create_dataset('data', data=data)
        epoch = {'uuid': epoch_id, 'start_time': '09/24/2026 12:00:00:000001',
                 'parameters': {'value': 3.}, 'properties': {'bathTemperature': 30.}, 'attributes': {},
                 'responses': {'Amp1': {'uuid': stream_id, 'h5path': stream_path, 'sampleRate': 10000., 'sampleRateUnits': 'Hz'}}, 'stimuli': {}}
        block = {'uuid': block_id, 'protocolID': 'example', 'epochs': [epoch], 'parameters': {}}
        group = {'uuid': group_id, 'label': 'Control', 'epoch_blocks': [block]}
        cell = {'uuid': cell_id, 'label': name, 'type': 'fixture', 'start_time': '09/24/2026 12:00:00:000000', 'epoch_groups': [group]}
        document = {'uuid': identity, 'animals': [{'preparations': [{'cells': [cell]}]}]}
        metadata_path = self.folder/'imports'/(name + '.json')
        metadata_path.write_text(json.dumps(document))
        sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        manifest = {'source_path': str(source_path), 'source_sha256': sha, 'source_size': source_path.stat().st_size,
                    'metadata_path': str(metadata_path), 'metadata_sha256': hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                    'counts': {'epochs': 1, 'cells': 1}, 'validated_at': '2026-09-24T12:00:00+00:00'}
        record = {'project_uuid': self.project, 'source_sha256': sha, 'experiment_uuid': identity,
                  'experiment_id': len(self.sources.rows)+1, 'manifest': manifest}
        self.sources.insert1(record)
        return record

    def evaluate(self, path):
        members, cells = [], []
        for source in self.sources.rows:
            document = json.loads(Path(source['manifest']['metadata_path']).read_text())
            for cell, _, _, epoch in module.epochs(document):
                members.append({'uuid': epoch['uuid'], 'metadata_hash': module._fingerprint(epoch)})
                cells.append({'uuid': cell['uuid']})
        return {'epochs': members, 'cells': cells}

    def test_warm_cache_skips_h5_and_json_projection_but_validates_sql(self):
        self.assertEqual(self.service.last_refresh['rebuilt_sources'], 2)
        original = copy.deepcopy((self.service.rows, dict(self.service.details.items()), self.service._fingerprints))
        previous_calls = self.evaluator.call_count
        with patch.object(self.service, '_read_source_metadata', side_effect=AssertionError('Warm cache must not walk H5 headers')):
            result = self.service.refresh()
        self.assertEqual((result['reused_sources'], result['rebuilt_sources']), (2, 0))
        self.assertEqual(self.evaluator.call_count, previous_calls+1)
        self.assertEqual((self.service.rows, self.service.details, self.service._fingerprints), original)
        self.assertGreaterEqual(result['elapsed_seconds'], 0)
        self.assertIn('sql_queries', result['timing_ms'])
        self.assertEqual(result, self.service.last_refresh)

    def test_new_source_rebuilds_only_new_projection(self):
        self.add_source('three')
        with patch.object(self.service, '_read_source_metadata', wraps=self.service._read_source_metadata) as rebuild:
            result = self.service.refresh()
        self.assertEqual((result['reused_sources'], result['rebuilt_sources'], result['epochs']), (2, 1, 3))
        self.assertEqual(rebuild.call_count, 1)

    def test_manifest_change_invalidates_exactly_one_source(self):
        self.sources.rows[0]['manifest']['warnings'] = ['Recorded annotation update']
        with patch.object(self.service, '_read_source_metadata', wraps=self.service._read_source_metadata) as rebuild:
            result = self.service.refresh()
        self.assertEqual((result['reused_sources'], result['rebuilt_sources']), (1, 1))
        self.assertEqual(rebuild.call_count, 1)

    def test_metadata_tampering_even_same_length_and_mtime_fails_closed(self):
        metadata = Path(self.records[0]['manifest']['metadata_path'])
        before = metadata.stat()
        old = metadata.read_text()
        metadata.write_text(old.replace('30.0', '31.0'))
        os.utime(metadata, ns=(before.st_atime_ns,before.st_mtime_ns))
        cached = self.service._source_metadata_cache
        with self.assertRaisesRegex(ValueError, 'metadata checksum changed'):
            self.service.refresh()
        self.assertIs(self.service._source_metadata_cache, cached)
        self.assertEqual(self.service.last_refresh['status'], 'failed')
        with self.assertRaisesRegex(RuntimeError, 'refresh required'):
            self.service.query_result(self.protocol)

    def test_source_tampering_fails_checksum_without_publishing_cache(self):
        path = Path(self.records[0]['manifest']['source_path'])
        before = path.stat()
        with h5py.File(path, 'r+') as h5:
            datasets = []
            h5.visititems(lambda name, obj: datasets.append(name) if isinstance(obj, h5py.Dataset) else None)
            dataset = h5[datasets[0]]
            value = dataset[0]
            value['quantity'] += 1
            dataset[0] = value
        os.utime(path, ns=(before.st_atime_ns,before.st_mtime_ns))
        cache, signatures = self.service._source_metadata_cache, dict(self.service._source_signatures)
        with self.assertRaisesRegex(ValueError, 'checksum changed'):
            self.service.refresh()
        self.assertIs(self.service._source_metadata_cache, cache)
        self.assertEqual(self.service._source_signatures, signatures)

    def test_missing_raw_source_or_metadata_never_served_from_cache(self):
        for field in ('source_path', 'metadata_path'):
            with self.subTest(field=field):
                path = Path(self.records[0]['manifest'][field])
                renamed = path.with_suffix(path.suffix + '.missing')
                path.rename(renamed)
                try:
                    with self.assertRaises(FileNotFoundError):self.service.refresh()
                    self.assertFalse(self.service._loaded)
                finally:renamed.rename(path)
                self.service.refresh()

    def test_changed_sql_membership_still_rejects_warm_cache(self):
        self.evaluator.side_effect = lambda _: {'epochs': [], 'cells': []}
        cache = self.service._source_metadata_cache
        previous_success = copy.deepcopy(self.service.last_successful_refresh)
        with self.assertRaisesRegex(ValueError, 'query disagrees'):
            self.service.refresh()
        self.assertIs(self.service._source_metadata_cache, cache)
        self.assertFalse(self.service._loaded)
        self.assertEqual(self.service.last_successful_refresh, previous_success)

    def test_rebuilt_entries_are_not_published_when_later_sql_fails(self):
        self.add_source('three')
        cache, signatures = self.service._source_metadata_cache, dict(self.service._source_signatures)
        self.evaluator.side_effect = ValueError('SQL unavailable')
        with self.assertRaisesRegex(ValueError, 'SQL unavailable'):self.service.refresh()
        self.assertIs(self.service._source_metadata_cache, cache)
        self.assertEqual(self.service._source_signatures, signatures)
        self.evaluator.side_effect = self.evaluate
        result = self.service.refresh()
        self.assertEqual((result['reused_sources'], result['rebuilt_sources']), (2, 1))

    def test_input_changed_during_sql_check_rejects_snapshot(self):
        original = self.evaluate
        def mutate(path):
            result = original(path)
            source = Path(self.records[0]['manifest']['source_path'])
            source.touch()
            return result
        self.evaluator.side_effect = mutate
        with self.assertRaisesRegex(ValueError, 'before refresh completed'):self.service.refresh()
        self.assertFalse(self.service._loaded)

    def test_public_read_model_mutation_does_not_poison_private_cache(self):
        identity = next(iter(self.service.rows))
        self.service.rows[identity]['streams'][0]['units'] = 'incorrect'
        self.service.details[identity]['properties']['bathTemperature'] = -1
        self.service.refresh()
        self.assertEqual(self.service.rows[identity]['streams'][0]['units'], 'mV')
        self.assertEqual(self.service.details[identity]['properties']['bathTemperature'], 30.)


    def test_refresh_cannot_switch_initialized_project_identity(self):
        other = str(uuid.uuid4())
        for name in ('project.json', 'catalog.json'):
            file = self.folder/name
            document = json.loads(file.read_text())
            document['project_uuid'] = other
            file.write_text(json.dumps(document))
        cache = self.service._source_metadata_cache
        with self.assertRaisesRegex(ValueError, 'Project identity changed'):
            self.service.refresh()
        self.assertEqual(self.service.project['project_uuid'], self.project)
        self.assertIs(self.service._source_metadata_cache, cache)
        self.assertFalse(self.service._loaded)

    def test_warm_restart_uses_sealed_index_without_projection_decode_or_h5_headers(self):
        from workspace_disk_index import DiskMetadataIndex
        from workspace_projection_cache import ProjectionCache
        expected = copy.deepcopy((self.service.rows, self.service.cells, self.service.sources, self.service._fingerprints))
        expected_details = dict(self.service.details.items())
        initial_queries = self.evaluator.call_count
        with patch.object(ProjectionCache, 'read', side_effect=AssertionError('No full source projection decoding')), \
             patch.object(WorkspaceService, '_read_source_metadata', side_effect=AssertionError('No H5 header walks')), \
             patch.object(DiskMetadataIndex, 'build', side_effect=AssertionError('Sealed index already exists')), \
             patch('h5py.File', side_effect=AssertionError('No H5 opens on unchanged restart')):
            warm = self.service.refresh()
            restarted = WorkspaceService(self.folder)
        self.assertEqual(warm['metadata_index'], 'reused')
        self.assertEqual(restarted.last_refresh['metadata_index'], 'reopened')
        self.assertEqual((restarted.last_refresh['reused_sources'], restarted.last_refresh['rebuilt_sources']), (2,0))
        self.assertEqual(self.evaluator.call_count, initial_queries + 2)
        self.assertEqual((restarted.rows,restarted.cells,restarted.sources,restarted._fingerprints), expected)
        self.assertNotIsInstance(restarted.details, dict)
        self.assertEqual(dict(restarted.details.items()), expected_details)
        self.assertTrue(all(cell['date']=='2026-09-24' for cell in restarted.cells.values()))
        self.assertEqual({cell['start_time'] for cell in restarted.cells.values()}, {'09/24/2026 12:00:00:000000'})

    def test_all_inputs_are_preflighted_before_any_lazy_projection_is_read(self):
        second = Path(self.records[1]['manifest']['metadata_path'])
        second.write_text(second.read_text()+' ')
        old_index = self.service.disk_index
        with patch.object(old_index, 'source_projection', side_effect=AssertionError('Preflight must finish first')):
            with self.assertRaisesRegex(ValueError, 'metadata checksum changed'):
                self.service.refresh()
        self.assertIs(self.service.disk_index, old_index)
        self.assertFalse(self.service._loaded)

    def test_new_source_reuses_unchanged_lazy_projections_without_eager_merge(self):
        from collections import ChainMap
        from workspace_disk_index import DiskMetadataIndex
        old_index = self.service.disk_index
        old_ids = set(self.service.rows)
        self.add_source('three')
        with patch.object(old_index, 'source_projection', wraps=old_index.source_projection) as projections, \
             patch.object(self.service._projection_store, 'read', wraps=self.service._projection_store.read) as cache_reads, \
             patch.object(self.service, '_read_source_metadata', wraps=self.service._read_source_metadata) as parses, \
             patch.object(DiskMetadataIndex, 'build', wraps=DiskMetadataIndex.build) as builds:
            receipt=self.service.refresh()
        self.assertEqual(projections.call_count,2)
        self.assertTrue(all(call.kwargs=={'lazy_details':True} for call in projections.call_args_list))
        self.assertEqual(cache_reads.call_count,1)  # Only the newly registered source.
        self.assertEqual(parses.call_count,1)
        self.assertEqual(builds.call_count,1)
        merged=builds.call_args.args[2]
        self.assertIsInstance(merged,ChainMap)
        self.assertEqual(sum(not isinstance(mapping,dict) for mapping in merged.maps),2)
        self.assertEqual((receipt['reused_sources'],receipt['rebuilt_sources']),(2,1))
        self.assertTrue(old_ids < set(self.service.rows))
        self.assertEqual(len(self.service.rows),3)

    def test_all_active_scope_reuses_registered_catalog_and_predicate_discovery_once(self):
        index = self.service.disk_index
        self.assertIsNotNone(index)
        expected_catalog, expected_values = module.tree_catalog(list(self.service.rows.values()),
            self.service.details, sources=self.service.sources)
        expected_predicates = module.predicate_catalog(expected_catalog, expected_values)
        with patch.object(module, 'tree_catalog', side_effect=AssertionError('No legacy discovery')), \
             patch.object(index, 'catalog', wraps=index.catalog) as catalogs:
            active = self.service._tree_fields(None)
            registered = self.service._registered_tree_fields()
            self.assertIs(active, registered)
            self.assertIs(self.service._tree_fields(None), registered)
            self.assertEqual(catalogs.call_count, 1)
            self.assertEqual(registered[0], expected_catalog)
            self.assertEqual(dict(registered[1].items()), expected_values)
            self.assertNotIsInstance(registered[1], dict)  # Disk-backed value view.
        with patch.object(module, 'predicate_catalog', side_effect=AssertionError('No legacy predicate scan')), \
             patch.object(index, 'predicate_catalog', wraps=index.predicate_catalog) as predicates:
            fields = self.service.predicate_fields()
            initial_reads = predicates.call_count
            self.assertGreater(initial_reads, 0)
            self.assertEqual(self.service.predicate_fields(), fields)
            self.assertEqual(predicates.call_count, initial_reads)
            self.assertEqual(fields['total'], 2)
            self.assertEqual([{key:value for key,value in field.items()
                if key not in {'active_types', 'types_scope'}} for field in fields['fields']],
                expected_predicates['fields'])
        self.service.set_source_state_provider(lambda: {self.records[0]['source_sha256']: {'query_excluded': True}})
        narrowed, narrowed_values = self.service._tree_fields(None)
        self.assertEqual(narrowed['total'], 1)
        self.assertEqual(registered[0]['total'], 2)
        self.assertIsNot(self.service._tree_fields(None), registered)
        expected_ids = {key for key,row in self.service.rows.items()
                        if row['source_sha256'] != self.records[0]['source_sha256']}
        self.assertEqual(set(narrowed_values), expected_ids)
        self.assertEqual({field['id'] for field in narrowed['fields']},
                         {field['id'] for field in registered[0]['fields']})

    def test_warm_refresh_preserves_discovery_but_new_source_invalidates(self):
        from workspace_disk_index import DiskMetadataIndex
        index = self.service.disk_index
        fields = self.service.tree_fields(None)
        predicate_fields = self.service.predicate_fields()
        old_ids = set(index.values())
        with patch.object(module, 'tree_catalog', side_effect=AssertionError('No legacy tree discovery')), \
             patch.object(module, 'predicate_catalog', side_effect=AssertionError('No legacy predicate discovery')), \
             patch.object(DiskMetadataIndex, 'build', side_effect=AssertionError('Unchanged index must not rebuild')):
            receipt = self.service.refresh()
            self.assertTrue(receipt['discovery_indexes_preserved'])
            self.assertEqual(receipt['metadata_index'], 'reused')
            self.assertIs(self.service.disk_index, index)
            self.assertIs(self.service.tree_fields(None), fields)
            self.assertEqual(self.service.predicate_fields(), predicate_fields)
        self.add_source('three')
        with patch.object(module, 'tree_catalog', side_effect=AssertionError('No legacy tree discovery')), \
             patch.object(module, 'predicate_catalog', side_effect=AssertionError('No legacy predicate discovery')):
            receipt = self.service.refresh()
            updated = self.service.tree_fields(None)
            self.assertFalse(receipt['discovery_indexes_preserved'])
            self.assertEqual(receipt['metadata_index'], 'built')
            self.assertIsNot(self.service.disk_index, index)
            self.assertNotEqual(self.service.disk_index.generation, index.generation)
            self.assertIsNot(updated, fields)
            self.assertEqual(updated['total'], 3)
            self.assertEqual(self.service.predicate_fields()['total'], 3)
        new_ids = set(self.service.disk_index.values())
        self.assertTrue(old_ids < new_ids)
        self.assertEqual(len(new_ids - old_ids), 1)
        oracle, values = module.tree_catalog(list(self.service.rows.values()), self.service.details,
                                            sources=self.service.sources)
        self.assertEqual(updated, oracle)
        self.assertEqual(dict(self.service.disk_index.values().items()), values)

    def test_weighted_scope_lru_evicts_old_scopes_without_changing_membership(self):
        cells = list(self.service.cells)
        with patch.object(module, 'TREE_CACHE_VALUE_BUDGET', 1), patch.object(module, 'TREE_CACHE_MAX_SCOPES', 2):
            first = self.service.tree(self.protocol, {'cell_uuid': cells[0]}, 'cell')
            first_keys = set(self.service._tree_catalog_cache)
            second = self.service.tree(self.protocol, {'cell_uuid': cells[1]}, 'cell')
            self.assertLessEqual(len(self.service._tree_catalog_cache), 2)
            self.assertFalse(first_keys <= set(self.service._tree_catalog_cache))
            repeated = self.service.tree(self.protocol, {'cell_uuid': cells[0]}, 'cell')
        self.assertEqual(first, repeated)
        self.assertNotEqual(first['children'][0]['epoch_uuids'], second['children'][0]['epoch_uuids'])
        self.assertEqual(first['count'], 1)
        self.assertEqual(second['count'], 1)

    def test_shared_registered_catalog_does_not_consume_scope_value_budget(self):
        self.service._tree_fields(None)
        registered = self.service._registered_tree_fields()
        self.service._tree_catalog_cache = {}
        with patch.object(module, 'TREE_CACHE_VALUE_BUDGET', 1):
            self.service._remember_tree_catalog(('base',), registered)
            self.service._remember_tree_catalog(('empty',), ({'fields':[]}, {}))
        self.assertEqual(set(self.service._tree_catalog_cache), {('base',), ('empty',)})
