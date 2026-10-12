"""Scoped reads keep exact output without unrelated discovery or repeated builds."""
import copy
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import test_workspace_workbench as workbench_fixture
import test_workspace_annotation_density as annotation_fixture
import test_workspace_annotations as shared_fixture
from disco.metadata.disk_index import DiskMetadataIndex
from disco.navigation.tag_predicates import TagPredicates
from disco.navigation.tree_pages import TreePages, _structural_contract
from disco.workbench.recipes import checksum
from disco.workbench.workbench import WorkbenchConflict
from workspace_service import WorkspaceService
from workspace_qc import CellQC


class FrozenScopedReadTests(unittest.TestCase):
    def setUp(self):
        self.case = workbench_fixture.WorkbenchTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.case.service
        self.manager = self.case.manager
        self.protocol = self.case.protocol

    def context(self):
        return self.manager.context(self.protocol, self.case.revision, 'actor-one')

    def index(self):
        index = DiskMetadataIndex.build(Path(self.case.case.temp.name) / 'scope-read.sqlite',
            self.service.rows, self.service.details, self.service.sources,
            'scoped-reads-v1', self.service.project['project_uuid'])
        self.service.disk_index = index
        self.addCleanup(index.close)
        return index

    def body(self, **options):
        return dict(protocol_uuid=self.protocol, splits='cell', counts_only=True, **options)

    def test_context_never_discovers_unrelated_protocol_membership(self):
        other = str(uuid.uuid4())
        self.service.protocols[other] = copy.deepcopy(self.service.protocols[self.protocol])
        original = WorkspaceService.query_result
        calls = []
        def scoped_only(service, protocol):
            calls.append(protocol)
            if protocol == other:
                raise AssertionError('Unrelated unavailable binding must not break Workbench')
            return original(service, protocol)
        with patch.object(WorkspaceService, 'query_result', scoped_only):
            response = self.case.get_context()
        self.assertTrue(calls)
        self.assertNotIn(other, calls)
        self.assertEqual(response['protocol']['counts']['epochs'], 1)
        self.assertEqual([cell['cell_uuid'] for cell in response['protocol']['cells']],
            [self.service.rows[self.case.added]['cell_uuid']])
        self.assertTrue(all('protocol_uuids' not in cell for cell in response['protocol']['cells']))

    def test_custom_summary_keeps_its_existing_interface(self):
        original = self.service._cell_summary
        def custom(rows):
            return [dict(cell, custom_summary=True) for cell in original(rows)]
        with patch.object(self.service, '_cell_summary', custom):
            response = self.case.get_context()
        self.assertTrue(all(cell['custom_summary'] for cell in response['protocol']['cells']))
        self.assertTrue(all('protocol_uuids' in cell for cell in response['protocol']['cells']))

    def test_frozen_tree_reuses_projection_but_not_request_adapters_or_authority(self):
        self.index()
        context = self.context()
        scoped = self.manager.frozen_service(context)
        pager = TreePages(scoped)
        first = pager.page(self.body())
        second_scoped = self.manager.frozen_service(self.context())
        self.assertIsNot(scoped, second_scoped)
        self.assertFalse(_structural_contract(second_scoped))  # Not native typed/binding authority.
        second = TreePages(second_scoped)
        with patch.object(second, '_build_scope', side_effect=AssertionError('Frozen scope rebuilt')):
            self.assertEqual(second.page(self.body()), first)
        # Changing a returned DTO cannot mutate retained projection data.
        first['branches'][0]['count'] = -1
        self.assertEqual(second.page(self.body())['branches'][0]['count'], 1)

    def test_selected_views_never_alias_unrestricted_or_empty_membership(self):
        self.index()
        context = self.context()
        def read(value):
            scoped = self.manager.frozen_service(value)
            return scoped.epoch_page(self.protocol), TreePages(scoped).page(self.body())
        full, tree = read(context)
        selected, selected_tree = read(dict(context, _view_ids={self.case.added}))
        empty, empty_tree = read(dict(context, _view_ids=set()))
        self.assertEqual(full, selected)
        self.assertEqual(tree, selected_tree)
        self.assertEqual(empty['total'], 0)
        self.assertEqual(empty_tree['total'], 0)
        self.assertEqual(read(context), (full, tree))

    def test_warm_pages_refuse_index_changes_and_changed_pending_fingerprints(self):
        index = self.index()
        context = self.context()
        TreePages(self.manager.frozen_service(context)).page(self.body())
        original = self.service._fingerprints[self.case.added]
        self.service._fingerprints[self.case.added] = 'changed'
        with self.assertRaisesRegex(WorkbenchConflict, 'unavailable or changed'):
            self.manager.frozen_service(self.context())
        self.service._fingerprints[self.case.added] = original
        with index.path.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            self.manager.frozen_service(self.context())

    def test_acceptance_removes_pending_rows_from_retained_projection(self):
        self.index()
        before = self.context()
        first = self.manager.frozen_service(before).epoch_page(self.protocol)
        self.assertEqual(first['total'], 1)
        request = self.case.accepted_request()
        result = self.case.accept(request)
        self.assertEqual(result.status_code, 200, result.get_json())
        after = self.context()
        self.assertNotEqual(before['candidate_scope_revision'], after['candidate_scope_revision'])
        self.assertEqual(self.manager.frozen_service(after).epoch_page(self.protocol)['total'], 0)

    def test_custom_row_policy_keeps_public_fallback(self):
        self.index()
        calls = []
        def custom(protocol, filters=None):
            calls.append(protocol)
            return []
        with patch.object(self.service, '_tree_rows', custom):
            scoped = self.manager.frozen_service(self.context())
            self.assertFalse(_structural_contract(scoped, frozen_protocol=self.protocol))
            self.assertEqual(TreePages(scoped).page(self.body())['total'], 0)
        self.assertEqual(calls, [self.protocol])

    def test_warm_tree_still_checks_closing_context(self):
        self.index()
        public = self.case.get_context()
        body = dict(candidate_scope_revision=public['candidate_scope_revision'], splits='cell')
        root = self.case.root + '/tree/page'
        first = self.case.case.client.post(root, json=body, headers=self.case.case.headers)
        self.assertEqual(first.status_code, 200, first.get_json())
        original = self.manager.context
        calls = []
        def changed(*args, **kwargs):
            context = original(*args, **kwargs)
            calls.append(1)
            if len(calls) == 2:
                context['candidate_scope_revision'] = 'changed-at-close'
            return context
        with patch.object(self.manager, 'context', side_effect=changed):
            refused = self.case.case.client.post(root, json=body, headers=self.case.case.headers)
        self.assertEqual(refused.status_code, 409, refused.get_json())
        self.assertNotIn('branches', refused.get_json())

    def test_draft_and_shared_coverage_changes_reuse_only_immutable_grouping(self):
        self.index()
        shared = self.case.coverage_annotations()
        before = self.case.get_context()
        context = self.context()
        scoped = self.manager.frozen_service(context)
        body = dict(protocol_uuid=self.protocol, splits='cell')
        first = TreePages(scoped).page(body)
        saved = self.case.save(before, [dict(epoch_uuid=self.case.added, selected=True, reviewed=True)])
        self.assertEqual(saved.status_code, 200, saved.get_json())
        fresh = self.context()
        self.assertNotEqual(context['candidate_scope_revision'], fresh['candidate_scope_revision'])
        pager = TreePages(self.manager.frozen_service(fresh))
        with patch.object(pager, '_build_scope', side_effect=AssertionError('Draft rebuilt pure grouping')):
            self.assertEqual(pager.page(body), first)
        snapshot = shared.snapshot()
        changed = dict(snapshot, revision='new-shared-revision', records=[dict(
            target_kind='epoch', target_uuid=self.case.added, tags=['current'])])
        with patch.object(shared, 'snapshot', return_value=changed):
            context = self.context()
            pager = TreePages(self.manager.frozen_service(context))
            with patch.object(pager, '_build_scope', side_effect=AssertionError('Annotation rebuilt pure grouping')):
                answer = pager.page(body)
        self.assertEqual(answer['branches'][0]['shared_tag_coverage'], dict(total_epochs=1, tagged_epochs=1))


class ScopedAnnotationReadTests(unittest.TestCase):
    def setUp(self):
        self.case = annotation_fixture.DenseAnnotationSelectionTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_empty_annotation_snapshot_does_not_read_the_project(self):
        class NoProjectRead:
            def __getattribute__(self, name):
                raise AssertionError('Empty annotation request must not read project state')
        self.assertEqual(TagPredicates(NoProjectRead()).snapshot(set()),
            ({}, {'version': 1, 'revision': checksum([]), 'protocols': []}))

    def test_epoch_annotation_hydration_is_scoped_across_batch_boundaries(self):
        case = self.case
        for count in (250, 251, 501):
            with self.subTest(count=count):
                ids = case.ids[:count]
                case.table.read_log.clear()
                result = case.store.for_epochs([case.service.rows[key] for key in ids])
                self.assertEqual(set(result), set(ids))
                self.assertEqual({chip['profile_uuid'] for chip in result[ids[0]]['epoch_tags']},
                    {case.author, case.other_author})
                requested = {'epoch': [], 'cell': []}
                for read in case.table.read_log:
                    batch = read['restrictions'][-1]
                    self.assertIsInstance(batch, list)
                    self.assertLessEqual(len(batch), 250)
                    kind = next(part['target_kind'] for part in read['restrictions']
                                if isinstance(part, dict) and 'target_kind' in part)
                    requested[kind].extend(item['target_uuid'] for item in batch)
                self.assertEqual(requested['epoch'], ids)
                self.assertEqual(set(requested['cell']), {case.service.rows[key]['cell_uuid'] for key in ids})

    def test_summary_fallback_reads_only_selected_targets_and_inherited_cells(self):
        case = self.case
        rows = [case.service.rows[key] for key in case.ids[:251]]
        case.table.read_log.clear()
        summary = case.store.summary(rows)
        self.assertEqual(summary['shared_tagged_epochs'], 251)
        self.assertEqual(summary['total_tags'], len(case.multi_tags) + 1)
        self.assertTrue(case.table.read_log)
        self.assertTrue(all(isinstance(read['restrictions'][-1], list) for read in case.table.read_log))
        self.assertTrue(all(len(read['restrictions'][-1]) <= 250 for read in case.table.read_log))


class IndexedCellReadTests(unittest.TestCase):
    def setUp(self):
        self.case = shared_fixture.SharedAnnotationTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.service = self.case.service

    def test_qc_and_annotation_counts_share_index_without_project_iteration(self):
        service = self.service
        first = service.ids[0]
        cell = service.rows[first]['cell_uuid']
        expected = [row for row in service.rows.values() if row['cell_uuid'] == cell]
        index = DiskMetadataIndex.build(Path(self.case.case.temp.name) / 'cell-read.sqlite',
            service.rows, service.details, service.sources, 'cell-reads-v1', service.project['project_uuid'])
        service.disk_index = index
        self.addCleanup(index.close)
        class LookupsOnly(dict):
            def __iter__(self): raise AssertionError('Cell read enumerated project IDs')
            def values(self): raise AssertionError('Cell read enumerated project rows')
            def items(self): raise AssertionError('Cell read enumerated project rows')
        with patch.object(service, 'rows', LookupsOnly(service.rows)):
            self.assertEqual(service.cell_rows(cell), expected)
            self.assertEqual(service.cell_epoch_count(cell), len(expected))
            self.assertEqual(CellQC(service).rows(cell), sorted(expected,
                key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid'])))
            for endpoint, field in ((f'/api/cells/{cell}/annotations', 'epoch_count'),
                    (f'/api/epochs/{first}/annotations', 'cell_epoch_count')):
                response = self.case.client.get(endpoint)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()[field], len(expected))
            response = self.case.client.get(f'/api/epochs/{first}')
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()['annotations']['cell_epoch_count'], len(expected))

    def test_legacy_cell_reads_track_registration_and_link_changes(self):
        service = self.service
        first, second = service.ids
        cell = service.rows[first]['cell_uuid']
        self.assertEqual(service.cell_epoch_count(cell), 1)
        service.rows[second]['cell_uuid'] = cell
        self.assertEqual(service.cell_epoch_count(cell), 2)
        self.assertEqual({row['epoch_uuid'] for row in service.cell_rows(cell)}, {first, second})
        del service.rows[second]
        self.assertEqual(service.cell_epoch_count(cell), 1)
        self.assertEqual(service.cell_epoch_count(str(uuid.uuid4())), 0)

    def test_one_epoch_hydrates_only_its_curation_and_preserves_custom_policy(self):
        service = self.service
        identity = service.ids[0]
        calls = []
        def provider(protocol, fingerprints):
            calls.append((protocol, fingerprints))
            return {key: dict(tags=['current'], metadata_fingerprint=value, review_state='stale')
                    for key, value in fingerprints.items()}
        with patch.object(service, 'curation_provider', provider):
            result = service.epoch(identity, service.protocol_id)
        self.assertEqual(calls, [(service.protocol_id, {identity: service._fingerprints[identity]})])
        self.assertEqual(result['curation']['tags'], ['current'])
        self.assertFalse(result['curation']['reviewed'])
        with patch.object(service, '_curation', return_value={identity: dict(tags=['custom'])}) as custom:
            result = service.epoch(identity, service.protocol_id)
        custom.assert_called_once_with(service.protocol_id)
        self.assertEqual(result['curation']['tags'], ['custom'])


if __name__ == '__main__':
    unittest.main()
