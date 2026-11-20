"""A populated project opens with new fields queryable, then repairs one damaged recording."""
import json
from pathlib import Path
import sqlite3
from time import perf_counter
import unittest
from unittest.mock import patch

import h5py
import workspace_service
import test_workspace_refresh_cache as refresh_fixture


class AttributeUpgradeTests(unittest.TestCase):
    def test_sqlite_export_keeps_only_selected_source_attributes_with_exact_values(self):
        from disco.workbench.recipes import capture_query, prepare_export
        from workspace_sqlite import build_sqlite_export

        project = refresh_fixture.RefreshCacheTests()
        project.setUp()
        self.addCleanup(project.doCleanups)
        source = project.add_source('precise', epoch_attributes={'ticks': 2**62 + 1})
        service = project.service
        service.refresh()
        epoch = next(key for key, row in service.rows.items() if row['source_sha256'] == source['source_sha256'])
        result = {**service.query_result(project.protocol), 'project_uuid':project.project,
                  'protocol_uuid':project.protocol, 'source_revisions':[s['source_sha256'] for s in service.sources],
                  'metadata_fingerprint_version':2, 'epochs':[
                      {'uuid':key, 'metadata_hash':service._fingerprints[key]} for key in service.rows]}
        snapshot = capture_query(service.protocol(project.protocol)['definition'], result, str(project.folder/'catalog.json'))
        recipe = prepare_export(snapshot, [epoch], destination='wheeler-sqlite',
                                review_policy='include_unreviewed', actor='fixture')
        row = service.epoch(epoch)
        row['stimulus'] = {'Amp1': {'operatingMode': 'VClamp', 'offset': -62.5}}
        package = {'format':'recording-reference-package', 'version':1, 'recipe':recipe,
                   'epochs':[row], 'sources':service.sources}
        descriptors = {s['source_sha256']:s['h5_attribute_inventory'] for s in service.sources}
        artifact = project.folder/'one.sqlite'
        with patch.object(h5py, 'File', side_effect=AssertionError('Export reopened the H5')):
            build_sqlite_export(package, artifact, inventories=descriptors)
        with sqlite3.connect(artifact) as db:
            self.assertEqual(db.execute('SELECT DISTINCT epoch_uuid,source_sha256 FROM epoch_h5_attributes').fetchall(),
                             [(epoch, source['source_sha256'])])
            fields = dict(db.execute('SELECT field_id,value_json FROM epoch_recorded_fields'))
            self.assertEqual(fields['h5/epoch/@ticks'], str(2**62 + 1))
            self.assertEqual(fields['stimulus/Amp1/operatingMode'], '"VClamp"')
            self.assertEqual(fields['stimulus/Amp1/offset'], '-62.5')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'Immutable'):
                db.execute('DELETE FROM h5_attributes')

    def test_global_search_accepts_raw_leaf_names_and_keeps_each_owner(self):
        from disco.metadata.search import search_workspace

        project = refresh_fixture.RefreshCacheTests()
        project.setUp()
        self.addCleanup(project.doCleanups)
        large_tick = 2**62 + 1
        project.add_source('precision', epoch_attributes={'exactTick': large_tick})
        project.service.refresh()
        result = search_workspace(project.service, f'exactTick = {large_tick}')['results'][0]
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['predicate'], {'field': 'h5/epoch/@exactTick', 'operator': 'eq',
                                               'value_encoding': 'json', 'value': str(large_tick)})
        epoch = next(iter(project.service.rows))
        choices = search_workspace(project.service, f'uuid = "{epoch}"')
        self.assertTrue(choices['field_ambiguous'])
        counts = {r['field_id']:r['count'] for r in choices['results']}
        self.assertEqual(counts['h5/epoch/@uuid'], 1)
        self.assertEqual(counts['h5/block/@uuid'], 0)

    def test_open_repair_and_warm_refresh_keep_protocol_predicates_queryable(self):
        project = refresh_fixture.RefreshCacheTests()
        project.setUp()
        self.addCleanup(project.doCleanups)
        expected = set()
        for number in range(6):
            value = 'IClamp' if number % 2 else 'VClamp'
            registration = project.add_source(f'recording-{number}', epoch_attributes={'newMode': value})
            if value == 'IClamp':
                doc = json.loads(Path(registration['manifest']['metadata_path']).read_text())
                expected.update(epoch['uuid'] for _, _, _, epoch in workspace_service.epochs(doc))

        # Leave existing parsed metadata, mappings and project index in place.
        # No recording has an attribute inventory that this version can accept.
        for source in project.service.sources:
            Path(source['h5_attribute_inventory']['path']).with_suffix('.seal.json').unlink()
        fields = {'all': [
            {'field': 'parameters/value', 'operator': 'eq', 'value': 3},
            {'field': 'h5/epoch/@newMode', 'operator': 'eq', 'value': 'IClamp'},
        ]}
        self.timings = {}
        started = perf_counter()
        service = workspace_service.WorkspaceService(project.folder)
        self.timings['automatic_project_open_s'] = perf_counter() - started

        def check_query(receipt, repaired, reused):
            coverage = receipt['attribute_coverage']
            self.assertEqual(coverage['status'], 'complete')
            self.assertEqual(coverage['inventories_recovered'], repaired)
            self.assertEqual(receipt['reused_sources'], reused)
            self.assertEqual(coverage['recorded_attributes'], coverage['inventoried_attributes'])
            self.assertEqual(coverage['source_fields'], coverage['searchable_source_fields'])
            protocol_ids = [m['uuid'] for m in service.query_result(project.protocol)['epochs']]
            self.assertEqual(len(protocol_ids), 8)
            with patch.object(h5py, 'File', side_effect=AssertionError('Predicate reopened H5')):
                self.assertEqual(set(service.match_predicate(fields, protocol_ids)[1]), expected)

        check_query(service.last_refresh, 8, 0)
        damaged = service.rows[next(iter(expected))]['source_sha256']
        source = next(s for s in service.sources if s['source_sha256'] == damaged)
        Path(source['h5_attribute_inventory']['path']).with_suffix('.seal.json').write_text('{}')
        started = perf_counter()
        with patch.object(h5py, 'File', wraps=h5py.File) as reads:
            repair = service.refresh()
        self.timings['repair_one_source_s'] = perf_counter() - started
        self.assertEqual({Path(call.args[0]) for call in reads.call_args_list},
                         {Path(source['source_path'])})
        check_query(repair, 1, 7)

        started = perf_counter()
        with patch.object(h5py, 'File', side_effect=AssertionError('Warm refresh reopened H5')):
            warm = service.refresh()
        self.timings['unchanged_refresh_s'] = perf_counter() - started
        check_query(warm, 0, 8)
