"""Search predicate paths: per-generation tag states, per-value leaves, O(1) polls.

Results must equal the unmemoized reference exactly; work must not grow with
project epochs on a warm request. The SQL doubles and the production
StateGenerationAuthority come from the slow-read memo fixture.
"""
import cProfile
import pstats
import threading
import unittest
from unittest.mock import patch
import uuid

from disco.decisions.annotations import SharedAnnotations
from disco.decisions.curation import CurationStore
from disco.navigation.predicates import matches
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
        return matches(node, {field: states.get(identity, [])})
    return [identity for identity in ids if leaf(predicate, identity)]


def previous_catalog_field(definition, ids, states):
    """The previous per-epoch annotation catalog construction, kept as an oracle."""
    from disco.navigation.predicates import predicate_catalog
    from disco.navigation.tree import value_key, value_label, value_order
    key = definition['id']
    values = {identity: {key: states.get(identity, [])} for identity in ids}
    distinct = {value_key(current[key]): current[key] for current in values.values()}
    examples = [value_label(value)[:160] for value in sorted(distinct.values(), key=value_order)[:5]]
    field = {**definition, 'count': len(ids), 'distinct_count': len(distinct), 'recorded_distinct_count': len(distinct),
             'missing_count': 0, 'null_count': 0, 'varying': len(distinct) > 1, 'examples': examples,
             'grouping_role': 'annotation', 'grouping_priority': 100, 'varies_within_cell': False,
             'suggested_rank': None, 'suggestion_reason': '', 'high_cardinality': len(distinct) > 24}
    field = predicate_catalog({'fields': [field]}, values)['fields'][0]
    field.update(active_types=field['types'], types=['array'], types_scope='project_annotations', element_types=['string'])
    return field


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
            for predicate in self.predicates(field):
                with self.subTest(epochs=epochs, predicate=predicate):
                    profile = cProfile.Profile()
                    profile.enable()
                    try:
                        _, matched, evidence = TagPredicates(service).match(predicate, ids)
                    finally:
                        profile.disable()
                    leaf_calls = sum(primitive for (filename, _line, name), (primitive, *_rest)
                                     in pstats.Stats(profile).stats.items()
                                     if name == 'matches' and filename.endswith('navigation/predicates.py'))
                self.assertEqual(matched, reference_match(service, predicate, ids))
                # Two distinct saved arrays plus the implicit empty array per leaf.
                self.assertLessEqual(leaf_calls, 3 * 2, (epochs, predicate, leaf_calls))
                self.assertEqual(evidence['protocols'][0]['records'],
                                 [dict(epoch_uuid=key, revision=1, tags=sorted(value['tags']))
                                  for key, value in sorted(service.saved.items())])

    def test_supplied_universe_and_sparse_order_equal_the_scanned_order(self):
        service = StubService(2000, tagged=40)
        field = f'curation/{service.protocol}/tags'
        ids = tuple(reversed(list(service.rows)))
        rank = {key: index for index, key in enumerate(ids)}
        calls = []

        def order(found):
            calls.append(len(found))
            return sorted(found, key=rank.__getitem__)
        for predicate in self.predicates(field):
            with self.subTest(predicate=predicate):
                fast = TagPredicates(service).match(predicate, ids, universe=frozenset(ids), order=order)[1]
                self.assertEqual(fast, reference_match(service, predicate, ids))
        # Sparse results (40 of 2000) use the order function; dense ones scan.
        self.assertTrue(calls and max(calls) <= 40, calls)


    def test_catalog_fields_equal_the_per_epoch_construction(self):
        service = StubService(3000, tagged=0)
        keys = list(service.rows)
        long_tag = 'x' * 170
        for index, key in enumerate(keys[:400]):
            tags = [f'tag-{index % 70}', 'caf\u00e9 "q"'] if index % 3 else [long_tag + str(index % 2)]
            service.saved[key] = {'tags': tags, 'revision': 2}
        field = f'curation/{service.protocol}/tags'
        definition = next(item for item in TagPredicates(service).definitions() if item['id'] == field)
        states = {key: sorted(value['tags']) for key, value in service.saved.items()}
        for ids in (keys, list(reversed(keys)), keys[100:2500:3], []):
            with self.subTest(size=len(ids)):
                self.assertEqual(TagPredicates(service).catalog_fields(ids), [previous_catalog_field(definition, ids, states)])

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

    def test_shared_evidence_revision_is_the_previous_checksum(self):
        self.fixture.edit('epoch', self.ids[0], ['drift'])
        self.save_curation(tags_add=['protocol-flag'])
        links = sorted((key, row['cell_uuid']) for key, row in self.service.rows.items())
        for fields in ({'annotations/epoch/tags'}, {'annotations/effective/tag_times', 'annotations/cell/tags'},
                       {'annotations/epoch/tags', f'curation/{self.protocol}/tags'}):
            with self.subTest(fields=fields):
                evidence = TagPredicates(self.service).snapshot(fields)[1]
                shared = sorted(field for field in fields if field.startswith('annotations/'))
                self.assertEqual(evidence['revision'], checksum({
                    'protocols': [(item['protocol_uuid'], item['revision']) for item in evidence['protocols']],
                    'shared_revision': evidence['shared']['revision'], 'shared_fields': shared,
                    'registered_cell_links': links}))


    def test_shared_catalog_fields_equal_the_shared_index(self):
        from disco.navigation.tag_predicates import SHARED_FIELDS
        cell = self.service.rows[self.ids[0]]['cell_uuid']
        self.fixture.edit('cell', cell, ['caf\u00e9', 'q"uote', 'y' * 200])
        self.fixture.edit('epoch', self.ids[1], ['b\\slash', 'y' * 200 + 'z'])
        rows = [self.service.rows[key] for key in self.ids]
        expected = self.shared.catalog_fields(rows, set(SHARED_FIELDS))
        definitions = {item['id']: item for item in TagPredicates(self.service).definitions()}
        actual = {item['id']: item for item in TagPredicates(self.service).catalog_fields(self.ids, only=set(SHARED_FIELDS))}
        self.assertEqual(actual, {key: {**definitions[key], **value} for key, value in expected.items()})

    def test_tag_field_summaries_equal_the_per_epoch_loop(self):
        import disco.metadata.explore_queries as queries
        from disco.navigation.predicates import equality_key, kind
        self.fixture.edit('epoch', self.ids[0], ['drift', 'z'])
        self.fixture.edit('cell', self.service.rows[self.ids[1]]['cell_uuid'], ['good cell'])
        self.save_curation(tags_add=['protocol-flag'])
        fields = ['annotations/effective/tags', 'annotations/epoch/tags', f'curation/{self.protocol}/tags']
        context = {'predicate': {'all': []}, 'scope': {}, 'protocol_uuid': None, 'filters': {}, 'summary_fields': fields}
        result = queries._native_summaries(self.service, context, lambda: False)
        states = TagPredicates(self.service).snapshot(set(fields))[0]
        ids = list(self.service.match_predicate({'all': []})[1])
        for field in fields:
            values, seen = [], {}
            for identity in ids:
                value = states[field].get(identity, [])
                bucket = seen.get(equality_key(value))
                if bucket is None:
                    bucket = seen[equality_key(value)] = {'value': value, 'type': kind(value), 'count': 0}
                    values.append(bucket)
                bucket['count'] += 1
            self.assertEqual(result['summaries'][field], {'values': values, 'present_count': len(ids),
                             'missing_count': 0, 'values_truncated': False})
        self.assertEqual(result['matched_count'], len(ids))

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
        self.service._explore_publication = 'changed-publication'
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

    def test_whole_catalog_native_page_matches_listed_rows_reference(self):
        from workspace_service import WorkspaceService
        predicate = {'not': {'field': f'curation/{self.service.protocol_id}/tags', 'operator': 'contains', 'value': 'x'}}
        ids = list(self.service._eligible()[1])
        expected = sorted((self.service.rows[key] for key in self.service.match_predicate(predicate, ids)[1]),
                          key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid']))
        with patch.object(WorkspaceService, '_tree_rows', autospec=True,
                          side_effect=AssertionError('listed every row')):
            first = self.service.explore_page(predicate, limit=1)
            second = self.service.explore_page(predicate, limit=1, cursor=first['cursor'])
        self.assertEqual(first['rows'] + second['rows'], expected)
        self.assertEqual(len(expected), 2)
        self.assertIsNone(second['cursor'])

if __name__ == '__main__':
    unittest.main()
