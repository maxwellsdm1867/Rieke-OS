"""Prepared pages preserve canonical display and reject unproven continuations."""
import contextlib
import copy
import cProfile
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from disco.metadata.disk_index import DiskMetadataIndex
from disco.navigation.prepared_navigation import PreparedNavigation
from disco.navigation.publication_changes import PreparationRequired
from disco.navigation.tree_pages import TreePages, StaleTreePage
from test_workspace_tree_pages import TreePageTests
from workspace_service import WorkspaceService, publish_frozen


class Tracker:
    def __init__(self):
        self.value = 1
        self.complete = True
        self.fail_exit = False
    def token(self):
        return self.value
    @contextlib.contextmanager
    def capture(self, previous, **kwargs):
        yield SimpleNamespace(complete=self.complete, watermark=self.value, verify=lambda: None)
        if self.fail_exit:
            raise RuntimeError('failed capture close')


class PreparedNavigationTests(unittest.TestCase):
    def setUp(self):
        TreePageTests.setUp(self)
        self.service.__class__ = WorkspaceService
        self.index = DiskMetadataIndex.build(Path(self.temp.name) / 'prepared.sqlite',
            self.service.rows, self.service.details, self.service.sources, 'prepared', self.service.project['project_uuid'])
        self.addCleanup(self.index.close)
        self.service.disk_index = self.index
        for name in ('rows', 'cells', 'protocols', '_fingerprints'):
            setattr(self.service, name, publish_frozen(getattr(self.service, name), rows=name == 'rows'))
        self.tracker = self.service._recovery_tracker = Tracker()
        self.owner = PreparedNavigation(self.pager, threading.RLock())
        self.addCleanup(self.owner.close)
        self.assertTrue(self.owner.supported())

    def canonical(self, body):
        previous = getattr(self.service, '_prepared_navigation', None)
        self.service._prepared_navigation = None
        try:
            return self.pager.page(body)
        finally:
            self.service._prepared_navigation = previous

    @staticmethod
    def display(value):
        if isinstance(value, dict):
            return {key: PreparedNavigationTests.display(item) for key, item in value.items()
                    if key not in ('revision', 'duration_status')}
        if isinstance(value, (list, tuple)):
            return [PreparedNavigationTests.display(item) for item in value]
        return value

    def test_first_prepared_pages_labels_anchors_and_selection_equal_legacy_without_scope_rebuild(self):
        for splits in ('', 'date,cell,block', 'parameters/value,block',
                       'joint/parameters%2Fvalue+parameters%2Fother'):
            body = {'protocol_uuid': self.service.protocol_id, 'splits': splits, 'limit': 2}
            expected = self.canonical(body)
            self.owner.prepare(body)
            self.service._prepared_navigation = self.owner
            profile = cProfile.Profile()
            profile.enable()
            actual = self.pager.page(body)
            profile.disable()
            self.assertEqual(self.display(actual), self.display(expected))
            self.assertFalse(any(item.code.co_name == '_build_scope' for item in profile.getstats() if hasattr(item.code, 'co_name')))
            for identity in self.service.rows:
                anchor = {**body, 'anchor_uuid': identity}
                self.assertEqual(self.display(self.pager.page(anchor)), self.display(self.canonical(anchor)))
            selected = self.pager.selection({key: value for key, value in body.items() if key != 'limit'} |
                {'revision': actual['revision']}, len(self.service.rows))
            previous = self.service._prepared_navigation
            self.service._prepared_navigation = None
            legacy = self.pager.selection({key: value for key, value in body.items() if key != 'limit'} |
                {'revision': expected['revision']}, len(self.service.rows))
            self.service._prepared_navigation = previous
            self.assertEqual(selected['epoch_uuids'], legacy['epoch_uuids'])

    def test_existing_prepared_navigation_never_enters_compact_fallback(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date,cell,block', 'counts_only': True}
        self.owner.prepare(body)
        self.service._prepared_navigation = self.owner
        profile = cProfile.Profile()
        with profile:
            root = self.pager.page(body)
            for identity in self.service.rows:
                page = self.pager.page({**body, 'anchor_uuid': identity})
                self.assertIn(identity, [row['epoch_uuid'] for row in page['epochs']])
            self.assertEqual(root['count'], len(self.service.rows))
        self.assertFalse(any(getattr(item.code, 'co_name', None) == '_compact_tree' for item in profile.getstats()))

    def test_unrelated_commit_does_not_change_revision_for_equivalent_scope_defaults(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date'}
        self.owner.prepare(body)
        before = self.owner.read(body)
        self.tracker.value += 1
        after = self.owner.read({**body, 'filters': {}})
        self.assertEqual(after.revision, before.revision)
        self.assertIs(after.tree, before.tree)

    def test_cloned_reader_never_borrows_the_live_services_prepared_membership(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date'}
        self.owner.prepare(body)
        self.service._prepared_navigation = self.owner
        clone = copy.copy(self.service)
        identity = next(iter(clone.rows))
        clone._tree_rows = lambda protocol, filters: [clone.rows[identity]]
        cloned_pager = TreePages(clone)
        page = cloned_pager.page(body)
        self.assertEqual(page['count'], 1)
        result = cloned_pager.selection({**body, 'revision': page['revision']}, 1)
        self.assertEqual(result['epoch_uuids'], [identity])
        self.assertEqual(self.pager.page(body)['count'], len(self.service.rows))

    def test_missing_layout_and_publication_change_never_rebuild_on_read(self):
        body = {'splits': 'date'}
        with self.assertRaises(PreparationRequired):
            self.owner.read(body)
        self.owner.prepare(body)
        self.service.rows = publish_frozen(self.service.rows, rows=True)
        with self.assertRaises(PreparationRequired):
            self.owner.read(body)

    def test_feed_gap_or_failed_capture_cannot_publish_a_new_watermark(self):
        body = {'splits': 'date'}
        self.owner.prepare(body)
        entry = self.owner.read(body)
        self.tracker.value += 1
        self.tracker.complete = False
        with self.assertRaises(PreparationRequired):
            self.owner.read(body)
        self.assertIs(self.owner.entries[self.owner.key(body)], entry)
        self.tracker.complete = True
        self.tracker.fail_exit = True
        with self.assertRaises(RuntimeError):
            self.owner.read(body)
        self.assertIs(self.owner.entries[self.owner.key(body)], entry)

    def test_committed_membership_delta_has_exact_counts_pending_duration_and_stale_revision_refusal(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date,cell,block'}
        binding = {'version': 1, 'revision_uuid': 'first'}
        with patch.object(self.owner, 'binding', side_effect=lambda scope: copy.deepcopy(binding)):
            self.owner.prepare(body)
            self.service._prepared_navigation = self.owner
            first = self.pager.page(body)
            removed = next(iter(self.service.rows))
            binding.update(version=2, revision_uuid='second')
            self.tracker.value += 1
            with patch.object(self.owner, '_delta', return_value=({}, [removed])), patch.object(self.owner, '_finish_durations'):
                changed = self.pager.page(body)
            self.assertEqual(changed['count'], first['count'] - 1)
            self.assertEqual(changed['duration_status'], 'pending')
            self.assertIsNone(changed['duration_seconds'])
            with self.assertRaises(StaleTreePage):
                self.pager.page({**body, 'revision': first['revision']})
            entry = self.owner.read(body)
            complete = entry.tree.finish_durations().page()
            rows = [row for identity, row in self.service.rows.items() if identity != removed]
            expected = None if any(row['duration_seconds'] is None for row in rows) else sum(row['duration_seconds'] for row in rows)
            self.assertEqual(complete['duration_seconds'], expected)
            self.assertEqual(complete['duration_status'], 'ready')


    def test_every_prepared_page_has_a_closing_fence_even_source_and_joint_scopes(self):
        from disco.navigation.tree import joint_id
        for scope in ({'splits': 'date'}, {'protocol_uuid': self.service.protocol_id,
                'splits': joint_id(['parameters/value', 'parameters/other'])}):
            self.owner.prepare(scope)
            self.service._prepared_navigation = self.owner
            render = self.service._render_tree
            def changed(*args, **kwargs):
                result = render(*args, **kwargs)
                self.tracker.value += 1
                return result
            with patch.object(self.service, '_render_tree', side_effect=changed), self.assertRaises(PreparationRequired):
                self.pager.page(scope)

    def test_selection_has_a_closing_fence(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date'}
        self.owner.prepare(body)
        self.service._prepared_navigation = self.owner
        entry = self.owner.read(body)
        select = entry.tree.select
        def changed(*args, **kwargs):
            result = select(*args, **kwargs)
            self.tracker.value += 1
            return result
        with patch.object(type(entry.tree), 'select', side_effect=changed), self.assertRaises(PreparationRequired):
            self.pager.selection({**body, 'revision': entry.revision}, len(self.service.rows))

    def test_unrelated_commit_during_duration_fold_preserves_completed_sum_and_new_watermark(self):
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date'}
        binding = {'version': 1, 'revision_uuid': 'first'}
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        with patch.object(self.owner, 'binding', side_effect=lambda scope: copy.deepcopy(binding)):
            self.owner.prepare(body)
            self.service._prepared_navigation = self.owner
            original = self.owner.read(body).tree.finish_durations.__func__
            def held(tree):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('test worker was not released')
                return original(tree)
            binding.update(version=2, revision_uuid='second')
            self.tracker.value += 1
            with patch.object(type(self.owner.read.__self__.entries[self.owner.key(body)].tree), 'finish_durations', held), \
                    patch.object(self.owner, '_delta', side_effect=lambda entry, latest: ({}, [next(iter(self.service.rows))]) if entry.binding['revision_uuid'] != latest['revision_uuid'] else ({}, [])):
                pending = self.pager.page(body)
                self.assertEqual(pending['duration_status'], 'pending')
                self.assertTrue(entered.wait(1))
                future = self.owner.jobs[self.owner.key(body)]
                future.add_done_callback(lambda job: done.set())
                self.tracker.value += 1
                binding['version'] += 1  # Rebinding the same immutable members is still the same duration input.
                continued = self.pager.page(body)
                self.assertEqual(continued['duration_status'], 'pending')
                release.set()
                self.assertTrue(done.wait(2))
            ready = self.pager.page(body)
            self.assertEqual(ready['duration_status'], 'ready')
            self.assertEqual(self.owner.read(body).watermark, self.tracker.value)
            self.assertEqual(ready['count'], pending['count'])

    def test_family_classification_updates_when_last_foreign_member_is_removed(self):
        rows = {identity: dict(row, protocol_name='VariableHistoryNoiseCurInject') for identity, row in self.service.rows.items()}
        foreign = next(iter(rows))
        rows[foreign]['protocol_name'] = 'foreign'
        self.service.rows = publish_frozen(rows, rows=True)
        body = {'protocol_uuid': self.service.protocol_id, 'splits': 'date'}
        binding = {'version': 1, 'revision_uuid': 'first'}
        with patch.object(self.owner, 'binding', side_effect=lambda scope: copy.deepcopy(binding)):
            self.owner.prepare(body)
            self.assertIsNone(self.owner.read(body).catalog['protocol_family'])
            binding.update(version=2, revision_uuid='second')
            self.tracker.value += 1
            with patch.object(self.owner, '_delta', return_value=({}, [foreign])), patch.object(self.owner, '_finish_durations'):
                entry = self.owner.read(body)
            self.assertEqual(entry.catalog['protocol_family'], 'history-noise')

    def test_publication_prepares_only_effective_saved_layout_or_bound_default(self):
        from flask import Flask
        from disco.navigation.tree_pages import register_tree_page_routes
        app = Flask(__name__)
        service = SimpleNamespace(protocols={
            'bound': {'definition': {'view': {'group_by': ['date', 'cell']}}},
            'unbound': {'definition': {'view': {'group_by': ['block']}}}},
            query_view=lambda identity: {'dataset_binding': {'splits': 'cell,block'}} if identity == 'bound' else {})
        app.extensions['tree_layouts'] = SimpleNamespace(read=lambda identity:
            {'split_order': ['date']} if identity == 'bound' else None)
        register_tree_page_routes(app, service, threading.RLock(), contextlib.nullcontext)
        owner = app.extensions['disco.navigation.prepared']
        self.addCleanup(owner.close)
        scopes = []
        def prepare(body):
            scopes.append(body)
            owner.entries[owner.key(body)] = None
            return {'status': 'ready'}
        with patch.object(owner, 'supported', return_value=True), patch.object(owner, 'prepare', side_effect=prepare):
            receipt = app.extensions['prepare_tree_publication']()
        self.assertEqual(receipt['status'], 'ready')
        self.assertEqual(scopes, [{'splits': 'date,cell,block'},
            {'protocol_uuid': 'bound', 'splits': 'date'},
            {'protocol_uuid': 'unbound', 'splits': 'block'}])
        self.assertEqual(receipt['views'], 3)
        scopes.clear()
        with patch.object(owner, 'supported', return_value=True), patch.object(owner, 'prepare', side_effect=prepare), \
                patch.object(app.extensions['tree_layouts'], 'read', return_value=None):
            receipt = app.extensions['prepare_tree_publication']()
        self.assertEqual(receipt['views'], 3)
        self.assertEqual(scopes, [{'splits': 'date,cell,block'},
            {'protocol_uuid': 'bound', 'splits': 'cell,block'},
            {'protocol_uuid': 'unbound', 'splits': 'block'}])


if __name__ == '__main__':
    unittest.main()
