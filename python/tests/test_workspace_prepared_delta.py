"""Bounded cached adjacent projections; real seal verification, SQL doubles only."""
import sys
import unittest
import uuid
from unittest.mock import patch
import test_workspace_api as fixture
from disco.decisions.explorer import ExplorerHistory, MemberView


class PreparedDeltaTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.WorkspaceAPITests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.history = self.case.explorer_history
        response = self.case.client.post('/api/explore/revisions', json={
            'predicate': {'all': []}, 'splits': 'cell', 'summary_only': True}, headers=self.case.headers)
        self.assertEqual(response.status_code, 201)
        self.root = response.get_json()['revision_uuid']
        self.original = dict(self.history.members(self.root).items())
        self.key = str(uuid.uuid4())
        self.delta = self.create(self.root, {self.key: 'a' * 64}, [next(iter(self.original))])

    def create(self, parent, added, removed=()):
        result = self.history.create_delta(parent, added, removed, 'tester', name='Delta')
        identity = result['revision_uuid']
        self.history.header(identity)  # Ordinary bind verifies before display admission.
        return identity

    def read(self, previous, current, **kwargs):
        forbidden = {getattr(ExplorerHistory, name).__code__ for name in
                     ('header', 'members', '_row', '_verified_recipe')}
        forbidden.update((MemberView.__init__.__code__, MemberView.flatten.__code__, MemberView.__iter__.__code__))
        def check(frame, event, arg):
            if event == 'call' and frame.f_code in forbidden:
                raise AssertionError('Prepared delta entered a hydrating/enumerating read')
        prior = sys.getprofile()
        sys.setprofile(check)
        try:
            result = self.history.prepared_delta(previous, current, **kwargs)
            if result is not None:
                self.assertEqual(set(result), {'added', 'removed', 'metadata'})
                self.assertTrue(set(result['metadata']) <= {'name', 'source_revisions', 'predicate', 'splits', 'tree_view', 'annotation_scope'})
                result.pop('metadata')
            return result
        finally:
            sys.setprofile(prior)

    def test_verified_forward_and_inverse_are_detached(self):
        removed = next(iter(self.original))
        self.assertEqual(self.read(self.root, self.delta), {'added': {self.key: 'a' * 64}, 'removed': [removed]})
        result = self.read(self.delta, self.root)
        self.assertEqual(result, {'added': {removed: self.original[removed]}, 'removed': [self.key]})
        result['added'].clear()
        self.assertEqual(len(self.read(self.delta, self.root)['added']), 1)

    def test_membership_eviction_keeps_forward_but_declines_inverse_removals(self):
        parent = self.delta
        for _ in range(10):
            parent = self.create(parent, {str(uuid.uuid4()): 'b' * 64})
            self.history.members(parent)
        self.assertNotIn(self.root, self.history._member_views)
        self.assertIsNotNone(self.read(self.root, self.delta))
        self.assertIsNone(self.read(self.delta, self.root))
        # Undoing pure addition needs no parent view.
        child = self.create(self.root, {str(uuid.uuid4()): 'c' * 64})
        self.history._member_views.clear()
        self.assertIsNotNone(self.read(child, self.root))

    def test_missing_header_or_oversize_does_not_read_storage(self):
        with patch.object(type(self.history.Revision), '__and__', side_effect=AssertionError('storage read')):
            self.assertIsNone(self.read(self.root, self.delta, limit=1))
            cached = self.history._headers.pop(self.root)
            self.assertIsNone(self.read(self.root, self.delta))
            self.history._headers[self.root] = cached
            self.history._headers.pop(self.delta)
            self.assertIsNone(self.read(self.root, self.delta))

    def test_depth_sixteen_never_flattens_during_projection(self):
        parent = self.delta
        for _ in range(18):
            child = self.create(parent, {str(uuid.uuid4()): 'd' * 64})
            self.history.members(child)
            self.assertIsNotNone(self.read(parent, child))
            self.assertIsNotNone(self.read(child, parent))
            parent = child

    def test_deleted_revision_or_unrelated_identity_declines(self):
        self.assertIsNone(self.read(self.root, str(uuid.uuid4())))
        self.assertIsNone(self.read(self.root, self.root))
        self.case.explorer_revisions.rows[:] = [row for row in self.case.explorer_revisions.rows if row['revision_uuid'] != self.root]
        self.assertIsNone(self.read(self.root, self.delta))
        self.assertIsNone(self.read(self.delta, self.root))

    def test_custom_reader_declines_before_touching_cache_or_storage(self):
        with patch.object(self.history, 'header', side_effect=AssertionError('custom read')):
            self.assertIsNone(self.history.prepared_delta(self.root, self.delta))
        with patch.object(ExplorerHistory, 'members', side_effect=AssertionError('custom members')):
            self.assertIsNone(self.history.prepared_delta(self.root, self.delta))

    def test_multiple_merges_and_undo_have_exact_net_membership(self):
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        one = self.create(self.root, {first: '1' * 64})
        two = self.create(one, {second: '2' * 64})
        self.assertEqual(self.read(self.root, two), {'added': {first: '1' * 64, second: '2' * 64}, 'removed': []})
        self.history._member_views.clear()
        self.assertEqual(self.read(two, self.root), {'added': {}, 'removed': [second, first]})
        self.assertEqual(self.read(two, one), {'added': {}, 'removed': [second]})

    def test_remove_readd_keeps_replacement_fingerprint(self):
        key = next(iter(self.original))
        one = self.create(self.root, {}, [key])
        two = self.create(one, {key: 'e' * 64})
        self.assertEqual(self.read(self.root, two), {'added': {key: 'e' * 64}, 'removed': [key]})
        self.assertEqual(self.read(two, self.root), {'added': {key: self.original[key]}, 'removed': [key]})

    def test_sibling_chain_and_cancelled_addition(self):
        key = str(uuid.uuid4())
        one = self.create(self.root, {key: '1' * 64})
        two = self.create(one, {}, [key])
        self.assertEqual(self.read(self.root, two), {'added': {}, 'removed': []})
        self.history._member_views.clear()
        self.assertEqual(self.read(two, self.root), {'added': {}, 'removed': []})
        # Restore proof explicitly for creating another branch, not in the read.
        self.history.members(self.root)
        other = str(uuid.uuid4())
        branch = self.create(self.root, {other: '2' * 64})
        self.assertEqual(self.read(one, branch), {'added': {other: '2' * 64}, 'removed': [key]})

    def test_total_unique_touched_is_checked_before_storage(self):
        one = self.create(self.root, {str(uuid.uuid4()): '1' * 64})
        two = self.create(one, {str(uuid.uuid4()): '2' * 64})
        with patch.object(type(self.history.Revision), '__and__', side_effect=AssertionError('storage read')):
            self.assertIsNone(self.read(self.root, two, limit=1))
        key = str(uuid.uuid4())
        one = self.create(self.root, {key: '3' * 64})
        two = self.create(one, {}, [key])
        self.assertEqual(self.read(self.root, two, limit=1), {'added': {}, 'removed': []})

    def test_chain_link_budget_and_evicted_intermediate_header(self):
        current = self.root
        for _ in range(64):
            current = self.create(current, {})
        self.assertEqual(self.read(self.root, current), {'added': {}, 'removed': []})
        extra = self.create(current, {})
        self.assertIsNone(self.read(self.root, extra))
        self.history._headers.pop(current)
        self.assertIsNone(self.read(self.root, extra))

    def test_metadata_is_small_and_detached(self):
        result = self.history.prepared_delta(self.root, self.delta)
        self.assertEqual(result['metadata']['name'], 'Delta')
        result['metadata']['tree_view']['fields'].clear()
        self.assertTrue(self.history.prepared_delta(self.root, self.delta)['metadata']['tree_view']['fields'])
