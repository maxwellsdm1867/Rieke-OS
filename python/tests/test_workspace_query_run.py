"""Query run and first results pages over a frozen publication, read from the typed index.

A run records counts and the tree revision without listing matches; inspection
pages read one typed window in the exact inspection chronology (date, start
time of day, UUID), with totals, anchors and the cell list equal to the exact
scope reader.
"""
import copy
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import test_workspace_explore_queries as explore_fixture
from workspace_service import WorkspaceService, publish_frozen, publication_serial


class QueryRunTests(unittest.TestCase):
    join = explore_fixture.RequestedSummaryTests.join

    def setUp(self):
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_lifecycle import prepare
        explore_fixture.RequestedSummaryTests.setUp(self)
        from disco.navigation.search_presets import SearchPresets
        from test_workspace_curation import Table
        from test_workspace_search_presets import PresetTable
        tables = (PresetTable(('project_uuid', 'preset_uuid')), Table(('project_uuid', 'preset_uuid', 'version')))
        runs = Table(('project_uuid', 'query_sha256'))
        self.fixture.connection.tables.extend([*tables, runs])
        self.fixture.app.extensions['search_presets'] = SearchPresets(self.fixture.store, tables, runs=runs)
        service = self.service
        template = service.rows[service.ids[0]]
        details = service.details[service.ids[0]]
        cells = [str(uuid.UUID(int=900 + n)) for n in range(3)]
        times = ['09/24/2026 23:50:00:000000', '09/25/2026 00:10:00:000000', '09/24/2026 08:00:00:000000',
                 '09/24/2026 12:00:00:000000', '09/24/2026 00:05:00:000000']
        for n in range(40):
            key = str(uuid.UUID(int=10_000 + n))
            row = {**template, 'epoch_uuid': key, 'cell_uuid': cells[n % 3], 'cell_label': f'Cell{n % 3 + 7}',
                   'date': '2026-09-24' if n % 4 else '2026-09-23', 'start_time': times[n % 5], 'epoch_number': n + 10}
            service.rows[key] = row
            detail = copy.deepcopy(details)
            detail['parameters'] = {**detail.get('parameters', {}), 'example': n % 5}
            if n % 3:
                detail['parameters']['flag'] = n % 2
            service.details[key] = detail
            service._fingerprints[key] = format(n, '064x')
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('e' * 64 + '.sqlite')
        self.index = DiskMetadataIndex.build(path, service.rows, service.details, service.sources, 'e' * 64,
                                             service.project['project_uuid'])
        service.disk_index, service.details = self.index, self.index.details
        service.typed_index, _ = prepare(self.index)
        service.rows = publish_frozen(service.rows, rows=True)
        service.cells, service.protocols, service._fingerprints = (publish_frozen(service.cells),
            publish_frozen(service.protocols), publish_frozen(service._fingerprints))
        self.assertIsNotNone(publication_serial(service))

    def post(self, path, body, status=200):
        response = self.client.post(path, json=body, headers=self.fixture.headers)
        self.assertEqual(response.status_code, status, response.get_json())
        return response.get_json()

    def predicates(self):
        cell = str(uuid.UUID(int=901))
        return [{'all': []}, {'field': 'cell', 'operator': 'eq', 'value': cell},
                {'field': 'parameters/example', 'operator': 'ne', 'value': 2},
                {'field': 'parameters/flag', 'operator': 'missing'},
                {'all': [{'field': 'parameters/example', 'operator': 'gte', 'value': 1},
                         {'field': 'parameters/example', 'operator': 'lt', 'value': 4}]},
                {'any': [{'field': 'cell', 'operator': 'eq', 'value': cell},
                         {'field': 'parameters/example', 'operator': 'eq', 'value': 0}]}]

    def run_query(self, predicate, *, exact=False):
        body = {'predicate': predicate, 'splits': 'cell', 'catalog_summary': False}
        if exact:
            with patch.object(WorkspaceService, 'run_summary', return_value=None):
                return self.post('/api/explore/run', body)
        with patch.object(WorkspaceService, 'explore_preview', side_effect=AssertionError('listed membership')):
            return self.post('/api/explore/run', body)

    def page(self, body, *, exact=False):
        if exact:
            with patch.object(WorkspaceService, 'counted_epoch_page', return_value=None):
                return self.post('/api/explore/epochs', body)
        return self.post('/api/explore/epochs', body)

    def test_counted_run_equals_the_exact_run(self):
        for predicate in self.predicates():
            with self.subTest(predicate=predicate):
                counted, exact = self.run_query(predicate), self.run_query(predicate, exact=True)
                for result in (counted, exact):
                    result['last_run'].pop('ran_at')
                self.assertEqual(counted, exact)

    def test_counted_pages_equal_the_exact_scope_reader(self):
        from disco.navigation.tree_pages import TreePages
        for predicate in self.predicates():
            revision = self.run_query(predicate)['tree_revision']
            base = {'predicate': predicate, 'splits': 'cell', 'revision': revision, 'limit': 7}
            exact_first = self.page({**base, 'include_cells': True}, exact=True)
            ids = []
            offset = 0
            while True:
                chunk = self.page({**base, 'offset': offset}, exact=True)
                ids.extend(row['epoch_uuid'] for row in chunk['epochs'])
                if not chunk['has_more']:
                    break
                offset += 7
            requests = [{**base, 'include_cells': True}, {**base, 'offset': 7}, {**base, 'offset': 14, 'limit': 5},
                        {**base, 'cell_uuid': str(uuid.UUID(int=902)), 'include_cells': True}]
            if ids:
                requests.append({**base, 'anchor_uuid': ids[len(ids) // 2]})
            for body in requests:
                with self.subTest(predicate=predicate, body={k: v for k, v in body.items() if k != 'predicate'}):
                    with patch.object(TreePages, '_scope', side_effect=AssertionError('listed matches')):
                        counted = self.page(body)
                    self.assertEqual(counted, self.page(body, exact=True))
            self.assertEqual(exact_first['total'], len(ids))

    def test_stale_revision_is_refused_before_reading(self):
        response = self.client.post('/api/explore/epochs', json={'predicate': {'all': []}, 'splits': 'cell',
                                    'revision': 'f' * 64}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 409)


if __name__ == '__main__':
    unittest.main()
