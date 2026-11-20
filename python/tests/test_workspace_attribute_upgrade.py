"""A populated project opens with new fields queryable, then repairs one damaged recording."""
import json
from pathlib import Path
from time import perf_counter
import unittest
from unittest.mock import patch

import h5py
import workspace_service
import test_workspace_refresh_cache as refresh_fixture


class AttributeUpgradeTests(unittest.TestCase):
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
