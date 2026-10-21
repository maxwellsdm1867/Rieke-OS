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
            return self.history.prepared_delta(previous, current, **kwargs)
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
