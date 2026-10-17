"""Per-tag added times: same-transaction writes, audit backfill and time filters."""
import copy
import datetime as dt
import json
import unittest
from unittest.mock import patch

import test_workspace_api as fixture
from test_workspace_curation import Table
from disco.decisions.annotations import SharedAnnotations
from disco.decisions.shared_tag_index import SharedTagsChanged
from disco.decisions.tag_times import reconcile, tag_digest, filter_with_times, delete_targets
from disco.navigation.tag_predicates import TagPredicates
from workspace_api import create_app
from workspace_service import validate_tag_filter_predicate

TIME_KEYS = ('project_uuid', 'target_kind', 'target_uuid', 'profile_uuid', 'tag_sha256')


class TimeTable(Table):
    """Transactional double plus the bulk insert/delete used by time rows."""
    def __and__(self, restriction):
        return TimeTable(self.keys, self.rows, self.restrictions + (restriction,), self.projected, self.read_log)

    def insert(self, rows, replace=False):
        for row in rows:
            if replace:
                self.rows[:] = [old for old in self.rows if not all(row[k] == old[k] for k in self.keys)]
            self.insert1(row)

    def delete_quick(self):
        def matches(row, restriction):
            if isinstance(restriction, list):
                return any(matches(row, item) for item in restriction)
            return all(row.get(key) == value for key, value in restriction.items())
        self.rows[:] = [row for row in self.rows if not all(matches(row, q) for q in self.restrictions)]


def utc(day, hour=0):
    return dt.datetime(2026, 10, day, hour, 0, 0)


class TagTimeTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.WorkspaceAPITests(); self.case.setUp(); self.addCleanup(self.case.doCleanups)
        self.service = self.case.service
        self.profiles = Table(('project_uuid', 'profile_uuid'))
        self.records = Table(('project_uuid', 'target_kind', 'target_uuid', 'profile_uuid'))
        self.times = TimeTable(TIME_KEYS)
        self.case.connection.tables.extend([self.profiles, self.records, self.times])
        self.store = SharedAnnotations(self.service, (self.profiles, self.records, self.case.events, self.times))
        self.service.shared_annotations = self.store
        self.author = self.store.default_profile['profile_uuid']
        self.first, self.second = self.service.ids
        self.cell, self.other_cell = self.service.cell_ids

    def edit(self, kind, target, add=(), remove=(), store=None):
        store = store or self.store
        rows = [row for row in self.records.rows if row['target_uuid'] == target and row['profile_uuid'] == self.author]
        revision = rows[0]['revision'] if rows else 0
        return store.update(kind, [target], self.author, {'tags_add': list(add), 'tags_remove': list(remove)},
                            {target: revision}, 'OS test actor')

    def time_row(self, target, tag):
        found = [row for row in self.times.rows if row['target_uuid'] == target and row['tag'] == tag]
        return found[0] if found else None

    def chips(self, key):
        return {chip['tag']: chip for chip in self.store.for_epochs([self.service.rows[key]])[key]['effective_tags']}

    def test_write_records_time_in_same_transaction_and_receipt_carries_it(self):
        result = self.edit('epoch', self.first, ['good', 'stable'])
        row = self.records.rows[0]
        for tag in ('good', 'stable'):
            time = self.time_row(self.first, tag)
            self.assertEqual(time['added_at'], row['updated_at'])
            self.assertEqual((time['added_revision'], time['time_source'], time['tag_sha256']), (1, 'recorded', tag_digest(tag)))
        chip = {chip['tag']: chip for chip in result['targets'][self.first]['tags']}['good']
        self.assertEqual(chip['added_at'], row['updated_at'].isoformat() + 'Z')
        self.assertEqual(chip['time_source'], 'recorded')
        self.assertEqual(row['tags'], ['good', 'stable'])  # tags JSON contract unchanged
        # A failing annotation write rolls back the time rows too.
        before = copy.deepcopy((self.records.rows, self.times.rows))
        with patch.object(self.times, 'insert', side_effect=RuntimeError('time write failed')):
            with self.assertRaises(RuntimeError): self.edit('epoch', self.first, ['later'])
        self.assertEqual((self.records.rows, self.times.rows), before)

    def test_remove_deletes_time_and_readd_records_new_time(self):
        self.edit('epoch', self.first, ['keep', 'drop'])
        self.time_row(self.first, 'keep')['added_at'] = utc(1)
        self.time_row(self.first, 'drop')['added_at'] = utc(1)
        self.edit('epoch', self.first, remove=['drop'])
        self.assertIsNone(self.time_row(self.first, 'drop'))
        self.assertEqual(self.time_row(self.first, 'keep')['added_at'], utc(1))  # kept tag keeps its time
        self.edit('epoch', self.first, ['drop'])
        again = self.time_row(self.first, 'drop')
        self.assertGreater(again['added_at'], utc(1))
        self.assertEqual(again['added_revision'], 3)
        self.assertEqual(self.chips(self.first)['keep']['added_at'], '2026-10-01T00:00:00Z')

    def test_stale_or_missing_time_rows_report_approximate_row_time(self):
        self.edit('epoch', self.first, ['x'])
        self.time_row(self.first, 'x')['added_revision'] = 9  # newer than the author's revision
        chip = self.chips(self.first)['x']
        self.assertEqual(chip['time_source'], 'approximate')
        self.assertEqual(chip['added_at'], self.records.rows[0]['updated_at'].isoformat() + 'Z')
        self.times.rows.clear()
        self.assertEqual(self.chips(self.first)['x']['time_source'], 'approximate')

    def legacy_history(self):
        """Edits made before the time table existed: only audit events remain."""
        legacy = SharedAnnotations(self.service, (self.profiles, self.records, self.case.events))
        self.edit('epoch', self.first, ['A'], store=legacy)           # rev 1
        self.edit('epoch', self.first, ['B'], store=legacy)           # rev 2
        self.edit('epoch', self.first, remove=['A'], store=legacy)    # rev 3
        self.edit('epoch', self.first, ['A'], store=legacy)           # rev 4
        self.edit('cell', self.cell, ['C'], store=legacy)             # rev 1
        events = sorted((row for row in self.case.events.rows if row['action'] == 'shared_annotations_updated'),
                        key=lambda row: row['payload']['after'][0]['revision'] + (10 if row['payload']['after'][0]['target_kind'] == 'cell' else 0))
        for day, event in enumerate(events, 2):
            event['occurred_at'] = utc(day, 6)
        for row in self.records.rows:
            row['updated_at'] = utc(20)
        self.assertEqual(self.times.rows, [])

    def test_backfill_uses_exact_audit_times_and_is_idempotent(self):
        self.legacy_history()
        counts = reconcile(self.store)
        self.assertEqual((counts['audit_event'], counts['approximate']), (3, 0))
        self.assertEqual(self.time_row(self.first, 'B')['added_at'], utc(3, 6))
        self.assertEqual(self.time_row(self.first, 'A')['added_at'], utc(5, 6))  # latest re-add, not first add
        self.assertEqual(self.time_row(self.first, 'A')['added_revision'], 4)
        self.assertEqual(self.time_row(self.cell, 'C')['added_at'], utc(6, 6))
        self.assertEqual(self.chips(self.first)['B']['time_source'], 'audit_event')
        snapshot = copy.deepcopy(self.times.rows)
        self.assertEqual(reconcile(self.store)['status'], 'current')
        self.assertEqual(reconcile(self.store, force=True)['status'], 'current')
        self.assertEqual(self.times.rows, snapshot)

    def test_backfill_marks_underivable_times_approximate(self):
        self.legacy_history()
        # Lose the event that added B: the chain from rev 4 breaks at rev 2.
        self.case.events.rows[:] = [row for row in self.case.events.rows
                                    if row['payload'].get('after', [{}])[0].get('revision') != 2
                                    or row['payload']['after'][0]['target_kind'] != 'epoch']
        # A row written outside the audited command (no events at all).
        self.records.insert1({'project_uuid': self.store.project_uuid, 'target_kind': 'epoch', 'target_uuid': self.second,
                              'profile_uuid': self.author, 'tags': ['manual'], 'author_name': 'x', 'revision': 1,
                              'updated_at': utc(21)})
        counts = reconcile(self.store)
        self.assertEqual(self.time_row(self.first, 'B')['time_source'], 'approximate')
        self.assertEqual(self.time_row(self.first, 'B')['added_at'], utc(20))
        self.assertEqual(self.time_row(self.first, 'A')['time_source'], 'audit_event')  # re-added after the gap
        self.assertEqual(self.time_row(self.second, 'manual')['added_at'], utc(21))
        self.assertEqual(self.time_row(self.second, 'manual')['time_source'], 'approximate')
        self.assertEqual(counts['approximate'], 2)

    def test_backfill_refuses_when_current_tags_disagree_with_newest_event(self):
        self.legacy_history()
        self.records.rows[0]['tags'] = ['A', 'B', 'Z']  # out-of-band edit at the same revision
        reconcile(self.store)
        self.assertTrue(all(row['time_source'] == 'approximate' for row in self.times.rows
                            if row['target_uuid'] == self.records.rows[0]['target_uuid']))

    def test_tag_time_predicate_validation_is_fail_closed(self):
        good = {'field': 'annotations/effective/tag_times', 'operator': 'contains',
                'value': {'tag': 'A', 'after': '2026-10-01T00:00:00Z'}}
        self.assertEqual(validate_tag_filter_predicate(json.dumps(good)), good)
        for bad in ({**good, 'operator': 'eq'}, {**good, 'value': {'tag': 'A'}}, {**good, 'value': {'tag': 'A', 'after': '2026-10-01'}},
                    {**good, 'value': {'tag': 'A', 'after': '2026-10-02T00:00:00Z', 'before': '2026-10-01T00:00:00Z'}},
                    {**good, 'value': {'tag': 'A', 'after': '2026-10-01T00:00:00Z', 'extra': 1}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_tag_filter_predicate(json.dumps(bad))

    def timed_fixture(self):
        self.edit('epoch', self.first, ['A']); self.edit('cell', self.cell, ['C']); self.edit('epoch', self.second, ['A'])
        self.time_row(self.first, 'A')['added_at'] = utc(1)
        self.time_row(self.second, 'A')['added_at'] = utc(10)
        self.time_row(self.cell, 'C')['added_at'] = utc(5)

    def test_search_predicates_filter_by_tag_time_with_inheritance(self):
        self.timed_fixture()
        def match(predicate):
            return TagPredicates(self.service).match(predicate, self.service.ids)[1]
        node = lambda field, value: {'field': field, 'operator': 'contains', 'value': value}
        self.assertEqual(match(node('annotations/epoch/tag_times', {'tag': 'A', 'after': '2026-10-05T00:00:00Z'})), [self.second])
        self.assertEqual(match(node('annotations/epoch/tag_times', {'tag': 'A', 'before': '2026-10-05T00:00:00Z'})), [self.first])
        self.assertEqual(match(node('annotations/effective/tag_times', {'tag': 'C', 'after': '2026-10-05T00:00:00Z',
                                                                      'before': '2026-10-05T00:00:01Z'})), [self.first])
        self.assertEqual(match(node('annotations/epoch/tag_times', {'tag': 'C', 'after': '2026-10-01T00:00:00Z'})), [])
        self.assertEqual(match({'not': node('annotations/effective/tag_times', {'tag': 'A', 'after': '2026-10-05T00:00:00Z'})}), [self.first])
        self.assertEqual(match({'all': [node('annotations/effective/tags', 'A'),
                                        node('annotations/effective/tag_times', {'tag': 'A', 'before': '2026-10-02T00:00:00Z'})]}), [self.first])

    def test_view_filter_and_indexed_path_agree_and_fail_closed_on_generation_change(self):
        self.timed_fixture()
        app = create_app(self.case.temp.name, self.case.temp.name, service=self.service, store=self.case.store,
            explorer_history=self.case.explorer_history, data_stores=self.case.data_stores,
            protocol_suggestions=self.case.protocol_suggestions, shared_annotations=self.store)
        client = app.test_client()
        predicate = {'field': 'annotations/effective/tag_times', 'operator': 'contains', 'value': {'tag': 'A', 'after': '2026-10-05T00:00:00Z'}}
        response = client.get('/api/protocols/' + self.service.protocol_id + '/epochs', query_string={'tag_predicate': json.dumps(predicate)})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual([row['epoch_uuid'] for row in response.get_json()['epochs']], [self.second])
        rows = [self.service.rows[key] for key in self.service.ids]
        with patch.object(self.store, 'generation_token', return_value='g1'):
            self.assertEqual(filter_with_times(self.store, rows, {}, predicate), ((self.second,), 'g1'))
        with patch.object(self.store, 'generation_token', side_effect=['g1', 'g1', 'g2']):
            with self.assertRaises(SharedTagsChanged):
                filter_with_times(self.store, rows, {}, predicate)
        # Without a verified generation the canonical chip reader decides.
        self.assertIsNone(filter_with_times(self.store, rows, {}, predicate))

    def test_removed_tag_no_longer_matches_and_deleted_targets_drop_times(self):
        self.timed_fixture()
        self.edit('epoch', self.second, remove=['A'])
        match = TagPredicates(self.service).match({'field': 'annotations/epoch/tag_times', 'operator': 'contains',
            'value': {'tag': 'A', 'after': '2026-01-01T00:00:00Z'}}, self.service.ids)[1]
        self.assertEqual(match, [self.first])
        delete_targets(self.store, [{'project_uuid': self.store.project_uuid, 'target_kind': 'cell', 'target_uuid': self.cell}])
        self.assertIsNone(self.time_row(self.cell, 'C'))
        self.assertIsNotNone(self.time_row(self.first, 'A'))


if __name__ == '__main__':
    unittest.main()
