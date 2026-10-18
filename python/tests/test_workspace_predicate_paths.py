"""Search predicate paths: per-generation tag states, per-value leaves, O(1) polls.

Results must equal the unmemoized reference exactly; work must not grow with
project epochs on a warm request. The SQL doubles and the production
StateGenerationAuthority come from the slow-read memo fixture.
"""
import threading
import unittest
from unittest.mock import patch
import uuid

from disco.decisions.annotations import SharedAnnotations
from disco.decisions.curation import CurationStore
import disco.navigation.tag_predicates as tag_predicates
from disco.navigation.tag_predicates import TagPredicates
from disco.workbench.recipes import checksum
import test_workspace_explore_queries as explore_fixture
import test_workspace_slow_read_memos as memo_fixture

MemoFixture = memo_fixture.MemoFixture


class StubService:
    """Minimal service surface for TagPredicates over many synthetic epochs."""
    def __init__(self, epochs, tagged):
        self.protocol = str(uuid.uuid4())
        self.rows = {}
        for index in range(epochs):
            key = str(uuid.UUID(int=index + 1))
            self.rows[key] = {'epoch_uuid': key, 'cell_uuid': str(uuid.UUID(int=10**9 + index % 7))}
        self._fingerprints = {key: '0' * 64 for key in self.rows}
        self.protocols = {self.protocol: {'definition': {'name': 'Stub'}}}
        keys = list(self.rows)
        self.saved = {key: {'tags': ['flag'] if index % 2 else ['flag', 'other'], 'revision': 1}
                      for index, key in enumerate(keys[:tagged])}
        self.provider_calls = 0
        self.annotation_provider = self.provide

    def provide(self, protocol, fingerprints):
        self.provider_calls += 1
        return {key: dict(value) for key, value in self.saved.items()}

    def _registered_tree_fields(self):
        return {'fields': []}, {}

    def _match_metadata_predicate(self, predicate, ids):
        raise AssertionError('No metadata leaves in these predicates')


def reference_match(service, predicate, ids):
    """The previous per-epoch evaluation, kept as an executable oracle."""
    field = f'curation/{service.protocol}/tags'
    states = {key: sorted(state['tags']) for key, state in service.saved.items() if state['tags']}

    def leaf(node, identity):
        if 'all' in node:
            return all(leaf(child, identity) for child in node['all'])
        if 'any' in node:
            return any(leaf(child, identity) for child in node['any'])
        if 'not' in node:
            return not leaf(node['not'], identity)
        return tag_predicates.matches(node, {field: states.get(identity, [])})
    return [identity for identity in ids if leaf(predicate, identity)]


class PerValueLeafTests(unittest.TestCase):
    def predicates(self, field):
        contains = {'field': field, 'operator': 'contains', 'value': 'flag'}
        return [contains, {'not': contains},
                {'field': field, 'operator': 'eq', 'value': ['flag', 'other']},
                {'field': field, 'operator': 'ne', 'value': ['flag']},
                {'field': field, 'operator': 'exists'}, {'field': field, 'operator': 'missing'},
                {'any': [{'field': field, 'operator': 'contains', 'value': 'other'},
                         {'not': {'field': field, 'operator': 'contains', 'value': 'flag'}}]}]

    def test_tag_leaves_match_reference_with_work_per_distinct_value(self):
        for epochs in (500, 5000):
            service = StubService(epochs, tagged=40)
            field = f'curation/{service.protocol}/tags'
            ids = list(service.rows)
            original = tag_predicates.matches
            for predicate in self.predicates(field):
                calls = []

                def counted(node, current):
                    calls.append(1)
                    return original(node, current)
                with self.subTest(epochs=epochs, predicate=predicate), \
                        patch.object(tag_predicates, 'matches', counted):
                    _, matched, evidence = TagPredicates(service).match(predicate, ids)
                    leaf_calls = len(calls)
                self.assertEqual(matched, reference_match(service, predicate, ids))
                # Two distinct saved arrays plus the implicit empty array per leaf.
                self.assertLessEqual(leaf_calls, 3 * 2, (epochs, predicate, leaf_calls))
                self.assertEqual(evidence['protocols'][0]['records'],
                                 [dict(epoch_uuid=key, revision=1, tags=sorted(value['tags']))
                                  for key, value in sorted(service.saved.items())])

    def test_snapshot_states_and_revision_equal_previous_construction(self):
        service = StubService(300, tagged=12)
        field = f'curation/{service.protocol}/tags'
        states, evidence = TagPredicates(service).snapshot({field})
        records = [dict(epoch_uuid=key, revision=1, tags=sorted(value['tags']))
                   for key, value in sorted(service.saved.items())]
        revision = checksum({'registered_epoch_universe': checksum(sorted(service._fingerprints)), 'records': records})
        self.assertEqual(evidence, {'version': 1, 'revision': checksum([(service.protocol, revision)]),
                                    'protocols': [dict(protocol_uuid=service.protocol, field=field,
                                                       revision=revision, records=records)]})
        self.assertEqual(states, {field: {key: sorted(value['tags']) for key, value in service.saved.items()}})


class GenerationMemoTests(MemoFixture):
    shared_predicate = {'field': 'annotations/effective/tags', 'operator': 'contains', 'value': 'drift'}

    def preview(self, predicate):
        response = self.client.post('/api/explore/preview', json={'predicate': predicate, 'splits': 'cell'},
                                    headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def reference(self, predicate):
        with self.unmemoized():
            return self.preview(predicate)

    def test_warm_tag_predicates_reuse_generation_states_and_match_reference(self):
        self.fixture.edit('epoch', self.ids[0], ['drift'])
        self.save_curation(tags_add=['protocol-flag'])
        protocol_predicate = {'field': f'curation/{self.protocol}/tags', 'operator': 'contains', 'value': 'protocol-flag'}
        for predicate in (self.shared_predicate, protocol_predicate,
                          {'any': [self.shared_predicate, {'not': protocol_predicate}]}):
            with self.subTest(predicate=predicate):
                cold = self.preview(predicate)
                # Class-level patches keep the native-method identity the witness checks.
                with patch.object(CurationStore, 'read', autospec=True,
                                  side_effect=AssertionError('warm request rereads curation')), \
                     patch.object(SharedAnnotations, 'snapshot', autospec=True,
                                  side_effect=AssertionError('warm request snapshots shared tags')):
                    warm = self.preview(predicate)
                self.assertEqual(warm, cold)
                self.assertEqual(warm, self.reference(predicate))

    def test_each_scope_write_invalidates_and_matches_reference(self):
        self.preview(self.shared_predicate)
        self.fixture.edit('epoch', self.ids[1], ['drift'])
        after_shared = self.preview(self.shared_predicate)
        self.assertEqual(after_shared['matched_count'], 1)
        self.assertEqual(after_shared, self.reference(self.shared_predicate))
        protocol_predicate = {'field': f'curation/{self.protocol}/tags', 'operator': 'contains', 'value': 'later'}
        self.assertEqual(self.preview(protocol_predicate)['matched_count'], 0)
        self.save_curation(ids=self.ids[1:], tags_add=['later'])
        after_protocol = self.preview(protocol_predicate)
        self.assertEqual(after_protocol['matched_count'], 1)
        self.assertEqual(after_protocol, self.reference(protocol_predicate))

    def test_unavailable_or_changing_witness_never_stores_a_memo(self):
        self.service._tag_predicate_memo = None
        with self.unmemoized():
            self.preview(self.shared_predicate)
        self.assertFalse(getattr(self.service, '_tag_predicate_memo', None))
        original = TagPredicates._build

        def concurrent(instance, fields, derived):
            entry = original(instance, fields, derived)
            self.fixture.edit('epoch', self.ids[1], ['drift'])
            return entry
        with patch.object(TagPredicates, '_build', concurrent):
            TagPredicates(self.service).match(self.shared_predicate, self.ids)
        self.assertFalse(getattr(self.service, '_tag_predicate_memo', None))
        self.assertEqual(TagPredicates(self.service).match(self.shared_predicate, self.ids)[1], [self.ids[1]])


class TagTimeWithoutTimeTableTests(MemoFixture):
    def test_tag_time_leaf_reads_records_not_every_epoch_chip(self):
        self.assertIsNone(self.shared.TagTime)
        self.fixture.edit('epoch', self.ids[1], ['late'])
        self.fixture.edit('cell', self.service.rows[self.ids[0]]['cell_uuid'], ['late'])
        node = lambda field, value: {'field': field, 'operator': 'contains', 'value': value}
        cases = [node('annotations/epoch/tag_times', {'tag': 'late', 'after': '2000-01-01T00:00:00Z'}),
                 node('annotations/effective/tag_times', {'tag': 'late', 'after': '2000-01-01T00:00:00Z'}),
                 node('annotations/cell/tag_times', {'tag': 'late', 'before': '2000-01-01T00:00:00Z'}),
                 {'not': node('annotations/cell/tag_times', {'tag': 'late', 'after': '2000-01-01T00:00:00Z'})}]
        expected = []
        for predicate in cases:
            with self.unmemoized(), patch.object(TagPredicates, '_approximate_times', return_value=None):
                expected.append(TagPredicates(self.service).match(predicate, self.ids)[1])
        with patch.object(self.shared, 'for_epochs', side_effect=AssertionError('hydrated every epoch')):
            actual = [TagPredicates(self.service).match(predicate, self.ids)[1] for predicate in cases]
        self.assertEqual(actual, expected)
        self.assertEqual(expected[0], [self.ids[1]])


class SummaryPollTests(unittest.TestCase):
    setUp = explore_fixture.RequestedSummaryTests.setUp
    join = explore_fixture.RequestedSummaryTests.join
    submit = explore_fixture.RequestedSummaryTests.submit

    def test_pending_poll_does_not_wait_behind_the_worker(self):
        self.jobs.autostart = False
        response = self.submit()
        self.assertEqual(response.status_code, 202, response.get_json())
        request_id = response.get_json()['request_id']
        held, release = threading.Event(), threading.Event()

        def worker():
            with self.jobs.db_lock:
                held.set()
                release.wait(10)
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            held.wait(5)
            with patch.object(self.jobs, '_fence', side_effect=AssertionError('pending poll fenced behind worker')):
                result = []
                poller = threading.Thread(target=lambda: result.append(self.jobs.poll(request_id)))
                poller.start()
                poller.join(2)
                self.assertFalse(poller.is_alive(), 'poll waited for the database lock')
            self.assertEqual(result[0]['status'], 'pending')
        finally:
            release.set()
            thread.join(5)
        # With the lock free, a pending poll still refuses a changed generation.
        with patch('disco.metadata.explore_queries.generation', return_value={'changed': True}):
            self.assertEqual(self.jobs.poll(request_id)['status'], 'stale')


class WholeCatalogEligibilityTests(unittest.TestCase):
    """Preview eligibility is kept per publication and selected by source (B9)."""
    join = explore_fixture.RequestedSummaryTests.join

    def setUp(self):
        from pathlib import Path
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.metadata.typed_lifecycle import prepare
        explore_fixture.RequestedSummaryTests.setUp(self)
        path = Path(self.fixture.temp.name) / 'cache' / 'metadata' / ('e' * 64 + '.sqlite')
        index = DiskMetadataIndex.build(path, self.service.rows, self.service.details,
            self.service.sources, 'e' * 64, self.service.project['project_uuid'])
        self.service.disk_index = index
        self.service.typed_index, _ = prepare(index)
        self.service._explore_publication = 'first-publication'

    def predicate(self):
        return {'field': 'cell', 'operator': 'eq', 'value': self.service.rows[self.service.ids[0]]['cell_uuid']}

    def reference(self, predicate):
        ids = [row['epoch_uuid'] for row in sorted(
            (row for row in self.service.rows.values()
             if row['source_sha256'] in set(self.service.source_scope()['active_source_revisions'])),
            key=lambda row: (row['date'], row['start_time'], row['epoch_uuid']))]
        return self.service.match_predicate(predicate, ids)

    def test_whole_catalog_scope_is_cached_and_selected_by_source(self):
        from disco.metadata.typed_index import TypedMetadataIndex
        scopes = []
        original = TypedMetadataIndex.iter_membership

        def observed(reader, predicate=None, scope=None):
            scopes.append(dict(scope) if isinstance(scope, dict) else scope)
            return original(reader, predicate, scope)
        with patch.object(TypedMetadataIndex, 'iter_membership', observed):
            first = self.service.explore_preview(self.predicate(), 'cell', include_tree=False, include_catalog_summary=False)
            second = self.service.explore_preview(self.predicate(), 'cell', include_tree=False, include_catalog_summary=False)
        self.assertEqual(first, second)
        self.assertEqual([set(scope) for scope in scopes], [{'sources'}, {'sources'}])
        self.assertIs(self.service._eligible()[1], self.service._eligible()[1])
        expected = self.reference(self.predicate())
        self.assertEqual([item['uuid'] for item in first['membership']], sorted(expected[1]))
        self.assertEqual(self.service.match_predicate(self.predicate())[1], expected[1])

    def test_publication_and_source_scope_invalidate_cached_eligibility(self):
        before = self.service._eligible()[1]
        self.service._explore_publication = 'next-publication'
        self.assertIsNot(self.service._eligible()[1], before)
        self.assertEqual(self.service._eligible()[1], before)
        excluded = self.service.rows[self.service.ids[0]]['source_sha256']
        with patch.object(self.service, 'source_state_provider',
                          lambda: {excluded: {'archived': False, 'query_excluded': True, 'version': 1}}):
            self.assertNotIn(self.service.ids[0], self.service._eligible()[1])
            self.assertEqual(list(self.service.match_predicate({'all': []})[1]),
                             list(self.service._eligible()[1]))


if __name__ == '__main__':
    unittest.main()
