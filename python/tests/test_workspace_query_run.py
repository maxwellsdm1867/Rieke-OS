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

    def single_field(self, predicate):
        fields, pending = set(), [predicate]
        while pending:
            node = pending.pop()
            if 'field' in node:
                fields.add(node['field'])
            pending.extend(node.get('all', []) + node.get('any', []) + ([node['not']] if 'not' in node else []))
        return len(fields) <= 1

    def test_counted_run_equals_the_exact_run(self):
        for predicate in self.predicates():
            with self.subTest(predicate=predicate):
                counted, exact = self.run_query(predicate), self.run_query(predicate, exact=True)
                for result in (counted, exact):
                    result['last_run'].pop('ran_at')
                if self.single_field(predicate):
                    self.assertNotIn('counts', counted)
                    self.assertEqual(counted, exact)
                    continue
                # Multi-field runs answer at once; exact counts follow from the job.
                job = counted.pop('counts')
                self.assertEqual((job['status'], counted['matched_count'], counted['last_run']['cell_count']), ('pending', None, None))
                self.join()
                result = self.client.get('/api/explore/summaries/' + job['request_id']).get_json()
                self.assertEqual(result['status'], 'ready', result)
                self.assertEqual(result['result'], {'matched_count': exact['matched_count'], 'cell_count': exact['last_run']['cell_count']})
                for key in ('matched_count', 'tree', 'catalog'):
                    counted.pop(key); exact.pop(key)
                for key in ('epoch_count', 'cell_count'):
                    counted['last_run'].pop(key); exact['last_run'].pop(key)
                self.assertEqual(counted, exact)

    def test_multi_field_pages_report_pending_counts_then_exact_totals(self):
        predicate = {'any': [{'field': 'cell', 'operator': 'eq', 'value': str(uuid.UUID(int=901))},
                             {'field': 'parameters/example', 'operator': 'eq', 'value': 0}]}
        self.jobs.autostart = False
        revision = self.run_query(predicate)['tree_revision']
        body = {'predicate': predicate, 'splits': 'cell', 'revision': revision, 'limit': 7, 'include_cells': True}
        pending = self.page(body)
        exact = self.page(body, exact=True)
        self.assertEqual((pending['total'], pending['cells_pending'], pending['counts']['status']), (None, True, 'pending'))
        self.assertNotIn('cells', pending)
        self.assertEqual(pending['epochs'], exact['epochs'])
        self.assertEqual(pending['has_more'], exact['has_more'])
        self.jobs.drive_worker()
        ready = self.page(body)
        self.assertEqual(ready.pop('counts')['status'], 'ready')
        self.assertEqual(ready, exact)

    def test_cell_list_pages_in_first_appearance_order(self):
        for predicate in ({'field': 'parameters/example', 'operator': 'ne', 'value': 2}, {'all': []}):
            revision = self.run_query(predicate)['tree_revision']
            body = {'predicate': predicate, 'splits': 'cell', 'revision': revision, 'limit': 7, 'include_cells': True}
            full = self.page(body, exact=True)['cells']
            collected, position = [], 0
            while position is not None:
                for exact in (False, True):
                    response = self.page({**body, 'cells_limit': 2, 'cells_after': position}, exact=exact)
                    if not exact:
                        counted = response
                    else:
                        self.assertEqual({k: v for k, v in counted.items() if k != 'counts'}, response)
                self.assertEqual(counted['cells_total'], len(full))
                collected.extend(counted['cells'])
                position = counted['cells_next']
            self.assertEqual(collected, full)
        self.post('/api/explore/epochs', {**body, 'cells_after': 2}, status=400)


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
                        if counted.get('counts', {}).get('status') == 'pending':
                            self.join()  # Multi-field totals arrive with the counts job.
                            counted = self.page(body)
                    counted.pop('counts', None)
                    self.assertEqual(counted, self.page(body, exact=True))
            self.assertEqual(exact_first['total'], len(ids))

    def test_single_field_aggregates_equal_the_scanned_cells_and_counts(self):
        from disco.metadata.explore_queries import typed_reader
        with typed_reader(self.service) as reader:
            for predicate in self.predicates():
                validated = reader._validate(predicate)
                single = reader.single_field_cells(validated)
                with self.subTest(predicate=predicate):
                    fields, pending = set(), [predicate]
                    while pending:
                        node = pending.pop()
                        if 'field' in node:
                            fields.add(node['field'])
                        pending.extend(node.get('all', []) + node.get('any', []) + ([node['not']] if 'not' in node else []))
                    if len(fields) > 1:
                        self.assertIsNone(single)
                        continue
                    self.assertEqual(single, reader.chronology_cells(validated))
                    self.assertEqual(reader.single_field_count(validated), reader.count(validated))
                    self.assertEqual(len(single), reader.distinct_cells(validated))

    def test_single_field_run_and_pages_never_scan_matches_and_later_pages_seek(self):
        from disco.metadata.typed_index import TypedMetadataIndex
        predicate = {'all': [{'field': 'parameters/example', 'operator': 'gte', 'value': 1},
                             {'field': 'parameters/example', 'operator': 'lt', 'value': 4}]}
        refuse = lambda name: patch.object(TypedMetadataIndex, name, side_effect=AssertionError(name + ' scanned matches'))
        with refuse('distinct_cells'), refuse('chronology_cells'), refuse('count'):
            revision = self.run_query(predicate)['tree_revision']
            base = {'predicate': predicate, 'splits': 'cell', 'revision': revision, 'limit': 5, 'include_cells': True}
            first = self.page(base)
        seeks = []
        original = TypedMetadataIndex.chronology_page

        def observed(reader, *args, **kwargs):
            seeks.append(kwargs.get('after_rank'))
            return original(reader, *args, **kwargs)
        with refuse('distinct_cells'), refuse('chronology_cells'), refuse('count'), \
                refuse('single_field_cells'), refuse('single_field_count'), \
                patch.object(TypedMetadataIndex, 'chronology_page', observed):
            second = self.page({**base, 'offset': 5})
            third = self.page({**base, 'offset': 10})
        self.assertTrue(all(rank is not None for rank in seeks), seeks)
        self.assertEqual(second, self.page({**base, 'offset': 5}, exact=True))
        self.assertEqual(third, self.page({**base, 'offset': 10}, exact=True))
        self.assertEqual(first, self.page(base, exact=True))

    def test_stale_revision_is_refused_before_reading(self):
        response = self.client.post('/api/explore/epochs', json={'predicate': {'all': []}, 'splits': 'cell',
                                    'revision': 'f' * 64}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 409)


if __name__ == '__main__':
    unittest.main()
