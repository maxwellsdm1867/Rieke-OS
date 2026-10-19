"""Delta revisions for additive merges: cost, round trip, exact membership, tampering.

Disposable SQL doubles and the Workbench fixture; no native MySQL or H5.
Set DISCO_MERGE_COST_SIZES=2000,20000,200000 for the full main-size sweep.
"""
import copy
import contextlib
import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch

import test_workspace_workbench as workbench_tests
import test_workspace_workbench_pending as pending_tests


class _Workbench(unittest.TestCase):
    """The cumulative-pending fixture and helpers, without re-running its tests."""
    setUp = workbench_tests.WorkbenchTests.setUp
    get_context = workbench_tests.WorkbenchTests.get_context
    queue = pending_tests.CumulativePendingTests.queue
    prepare = pending_tests.CumulativePendingTests.prepare
    more_import = pending_tests.CumulativePendingTests.more_import
    undo = pending_tests.CumulativePendingTests.undo
    apply_candidate = pending_tests.CumulativePendingTests.apply_candidate
    patch_draft = pending_tests.CumulativePendingTests.patch_draft


class _CountingSha256:
    """hashlib.sha256 stand-in that counts every byte hashed."""
    total = 0

    def __init__(self, data=b''):
        self._hash = _REAL_SHA256()
        self.update(data)

    def update(self, data):
        _CountingSha256.total += len(data)
        self._hash.update(data)

    def digest(self):
        return self._hash.digest()

    def hexdigest(self):
        return self._hash.hexdigest()


_REAL_SHA256 = hashlib.sha256


class DeltaRevisionFixture(_Workbench):
    """Builds a bound main of ``size`` epochs and one pending import."""

    def runTest(self):  # A fixture holder for the cost sweep, not a test.
        pass

    def grow_main(self, size):
        service = self.case.service
        donor = next(iter(self.fixture.before_ids))
        for index in range(size):
            key = str(uuid.UUID(int=10 ** 12 + index))
            service.rows[key] = {**copy.deepcopy(service.rows[donor]), 'epoch_uuid': key}
            service.details[key] = copy.deepcopy(service.details[donor])
            service._fingerprints[key] = service._fingerprints[donor]
        service._explore_publication = str(uuid.uuid4())  # Publish the grown rows.
        main = self.case.explorer_history.protocol_binding(self.protocol)['recipe']
        preview = service.explore_preview(main['predicate'], main['splits'])
        record = self.case.explorer_history.create(preview, service.sources, service.project_dir / 'catalog.json',
                                                   'actor-one', name='Large main')
        self.apply_candidate(record['revision_uuid'])

    def write_counter(self):
        counts = {'rows': 0, 'bytes': 0}

        def size(row):
            return len(json.dumps(row, default=str, sort_keys=True))
        stack = contextlib.ExitStack()
        for table in self.case.connection.tables:
            for method in ('insert1', 'update1'):
                original = getattr(table, method)
                def counted(row, original=original):
                    counts['rows'] += 1
                    counts['bytes'] += size(row)
                    return original(row)
                stack.enter_context(patch.object(table, method, counted))
            original = table.insert
            def inserted(rows, original=original):
                rows = list(rows)
                counts['rows'] += len(rows)
                counts['bytes'] += sum(size(row) for row in rows)
                return original(rows)
            stack.enter_context(patch.object(table, 'insert', inserted))
        return stack, counts

    def measure(self, action):
        stack, writes = self.write_counter()
        deepcopies = {'calls': 0}
        real_deepcopy = copy.deepcopy
        def counting_deepcopy(value, memo=None, _nil=[]):
            deepcopies['calls'] += 1
            return real_deepcopy(value, memo)
        _CountingSha256.total = 0
        with stack, patch('hashlib.sha256', _CountingSha256), patch('copy.deepcopy', counting_deepcopy):
            response = action()
        return response, dict(sql_rows_written=writes['rows'], sql_bytes_written=writes['bytes'],
                              bytes_hashed=_CountingSha256.total,
                              deepcopies=deepcopies['calls'])


class DeltaRevisionTests(_Workbench):
    def post_merge(self):
        queue = self.queue()
        return self.case.client.post(self.case.base + '/workbench/merge-all', json=dict(
            expected_queue_revision=queue['queue_revision'], operation_uuid=str(uuid.uuid4())), headers=self.case.headers)

    def test_merge_and_undo_cost_does_not_grow_with_main(self):
        sizes = [int(value) for value in os.environ.get('DISCO_MERGE_COST_SIZES', '2000,20000').split(',')]
        results = {}
        for size in sizes:
            fixture = DeltaRevisionFixture()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.grow_main(size)
            fixture.more_import()
            # The protocol query revision (protocol-state proof) is the backend
            # lane's protocol-state-v5 token; a constant stands in for it so
            # this sweep pins the Workbench and explorer share of the work.
            fixture.manager.read_revision = lambda protocol: 'protocol-state-v5-stand-in'
            fixture.manager.revision_guard = lambda protocol: (lambda: 'protocol-state-v5-stand-in')
            # One warm-up merge and undo: admits the root seal per process and
            # backfills the lineage index once (O(main), first merge only).
            merged = DeltaRevisionTests.post_merge(fixture)
            self.assertEqual(merged.status_code, 200, merged.get_json())
            fixture.undo(merged.get_json())
            fixture.queue()
            response, merge = fixture.measure(lambda: DeltaRevisionTests.post_merge(fixture))
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()['accepted_epoch_count'], 1)  # The new recording only.
            response, undo = fixture.measure(lambda: fixture.undo(response.get_json()))
            self.assertEqual(response.status_code, 200, response.get_json())
            results[size] = dict(merge=merge, undo=undo)
        print('Merge cost by main size:', json.dumps(results, sort_keys=True))
        baseline = results[sizes[0]]
        for size in sizes[1:]:
            for step in ('merge', 'undo'):
                measured, expected = results[size][step], baseline[step]
                self.assertEqual(measured['sql_rows_written'], expected['sql_rows_written'], (size, step))
                self.assertEqual(measured['deepcopies'], expected['deepcopies'], (size, step))
                # Only count digits (e.g. epoch_count) may lengthen serialized text.
                for field in ('bytes_hashed', 'sql_bytes_written'):
                    self.assertLessEqual(abs(measured[field] - expected[field]), 256, (size, step, field))

    def test_undo_round_trip_restores_main_membership_and_lineage_rows(self):
        first, _ = self.more_import()
        history = self.case.explorer_history
        before = history.protocol_binding(self.protocol)
        before_members = dict(history.members(before['revision_uuid']).items())
        merged = self.post_merge()
        self.assertEqual(merged.status_code, 200, merged.get_json())
        head = history.protocol_binding_header(self.protocol)['revision_uuid']
        header = history.header(head)
        self.assertEqual(header['storage'], 'membership-delta-v1')
        self.assertEqual(header['parent_revision_uuid'], before['revision_uuid'])
        self.assertEqual(sorted(row['uuid'] for row in header['delta']['added']), sorted([self.added, first]))
        rows = [row for row in self.membership.rows if row['added_revision_uuid'] == head]
        self.assertEqual(sorted(row['epoch_uuid'] for row in rows), sorted([self.added, first]))
        self.assertEqual(set(history.verify_lineage(head)), set(before_members) | {self.added, first})
        undone = self.undo(merged.get_json())
        self.assertEqual(undone.status_code, 200, undone.get_json())
        after = history.protocol_binding_header(self.protocol)
        self.assertEqual(after['revision_uuid'], before['revision_uuid'])
        self.assertEqual(dict(history.members(after['revision_uuid']).items()), before_members)
        self.assertFalse([row for row in self.membership.rows if row['added_revision_uuid'] == head])
        self.assertEqual(self.queue()['pending_epoch_count'], 2)
        again = self.post_merge()
        self.assertEqual(again.status_code, 200, again.get_json())
        self.assertEqual(sorted(again.get_json()['accepted_epoch_uuids']), sorted([self.added, first]))

    def test_delta_membership_is_byte_identical_to_the_full_recipe_result(self):
        first, _ = self.more_import()
        history, service = self.case.explorer_history, self.case.service
        main = history.protocol_binding(self.protocol)
        merged = self.post_merge()
        self.assertEqual(merged.status_code, 200, merged.get_json())
        head = history.protocol_binding(self.protocol)
        delta_epochs = json.dumps(head['recipe']['epochs'], sort_keys=True).encode()
        delta_view = json.dumps(service.query_result(self.protocol)['epochs'], sort_keys=True).encode()
        # The full-recipe path publishes the sorted union of main and the accepted epochs.
        union = {row['uuid']: row['metadata_hash'] for row in main['recipe']['epochs']}
        union.update({key: service._fingerprints[key] for key in (self.added, first)})
        full = history.create(dict(predicate=main['recipe']['predicate'], splits=main['recipe']['splits'],
            membership=[dict(uuid=key, metadata_hash=value) for key, value in sorted(union.items())],
            matched_count=len(union), total_source=len(service.rows), metadata_fingerprint_version=2,
            source_revisions=sorted({service.rows[key]['source_sha256'] for key in union}),
            tree=dict(split_order=main['recipe']['tree_view']['fields'])), service.sources,
            service.project_dir / 'catalog.json', 'actor-one', name='Full equivalent')
        self.assertEqual(json.dumps(history.get(full['revision_uuid'])['recipe']['epochs'], sort_keys=True).encode(),
                         delta_epochs)
        history.bind(full['revision_uuid'], self.protocol, head['version'], 'actor-one', {}, len(union))
        self.assertEqual(json.dumps(service.query_result(self.protocol)['epochs'], sort_keys=True).encode(), delta_view)

    def test_merge_and_undo_keep_the_pool_without_re_running_main_query(self):
        first, _ = self.more_import()
        service = self.case.service
        self.queue()
        with patch.object(service, 'match_predicate', wraps=service.match_predicate) as queries:
            merged = self.post_merge()
            self.assertEqual(merged.status_code, 200, merged.get_json())
            self.assertEqual(self.queue()['pending_epoch_count'], 0)
            undone = self.undo(merged.get_json())
            self.assertEqual(undone.status_code, 200, undone.get_json())
            self.assertEqual(self.queue()['pending_epoch_count'], 2)
        # main' = main + accepted keeps main's query and seen recordings, so the
        # pool is the old pool minus the accepted epochs; undo reuses main's pool.
        self.assertEqual(queries.call_count, 0)

    def tamper(self, revision, change):
        history = self.case.explorer_history
        row = next(row for row in self.case.explorer_revisions.rows if row['revision_uuid'] == revision)
        original = copy.deepcopy(row['recipe'])
        change(row['recipe'])
        history._headers.clear(), history._member_views.clear(), history._recipe_cache.clear()
        try:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                history.get(revision)
        finally:
            row['recipe'] = original
            history._headers.clear(), history._member_views.clear(), history._recipe_cache.clear()

    def test_tampered_delta_revisions_are_refused(self):
        self.more_import()
        merged = self.post_merge()
        self.assertEqual(merged.status_code, 200, merged.get_json())
        history = self.case.explorer_history
        head = history.protocol_binding_header(self.protocol)['revision_uuid']
        from disco.workbench.recipes import checksum

        def reseal(recipe):
            body = {key: value for key, value in recipe.items() if key != 'content_sha256'}
            recipe['content_sha256'] = checksum(body)

        def added_fingerprint(recipe):
            recipe['delta']['added'][0]['metadata_hash'] = 'f' * 64

        def added_fingerprint_resealed(recipe):
            added_fingerprint(recipe)
            reseal(recipe)

        def extra_member_resealed(recipe):
            recipe['delta']['added'].append(dict(uuid=str(uuid.uuid4()), metadata_hash='b' * 64))
            recipe['epoch_count'] += 1
            recipe['matched_count'] += 1
            reseal(recipe)

        def parent_seal_resealed(recipe):
            recipe['parent_content_sha256'] = 'f' * 64
            reseal(recipe)

        def removed_existing_resealed(recipe):
            recipe['delta']['removed'].append(recipe['delta']['added'][0]['uuid'])
            reseal(recipe)

        for change in (added_fingerprint, added_fingerprint_resealed, extra_member_resealed, parent_seal_resealed,
                       removed_existing_resealed):
            with self.subTest(change=change.__name__):
                self.tamper(head, change)
        self.assertEqual(len(history.get(head)['recipe']['epochs']), history.header(head)['epoch_count'])


if __name__ == '__main__':
    unittest.main()
