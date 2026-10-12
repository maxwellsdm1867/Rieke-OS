"""Independent native-value oracles for the typed read core, without live data."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from disco.metadata.tests.test_workspace_disk_index import fixture
from disco.metadata.disk_index import DiskMetadataIndex
import disco.navigation.predicates as predicates
from disco.metadata.typed_index import TypedMetadataIndex, QueryCancelled, build


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class TypedIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows, self.details, self.sources = fixture(count=37, history=True)
        for number, row in enumerate(self.rows):
            row['source_sha256'] = 'source' if number % 2 else 'other'
            row['start_time'] = str(37-number)
            self.details[row['epoch_uuid']]['parameters']['unseenBoolean'] = number % 2 == 0
            self.details[row['epoch_uuid']]['parameters']['wide'] = 2**60 if number % 2 else 2
        self.sources.append({'source_sha256': 'other', 'metadata': {'purpose': 'other source'}})
        self.native = DiskMetadataIndex.build(self.root/'native.sqlite', self.rows,
            self.details, self.sources, 'native-generation', 'project')
        self.addCleanup(self.native.close)
        self.native_hash = hashlib.sha256(self.native.path.read_bytes()).hexdigest()
        self.path = self.root/'typed.sqlite'
        self.receipt = build(self.native.path, self.path, min_free_gib=0,
            expected_generation='native-generation', expected_project_uuid='project')
        self.index = TypedMetadataIndex(self.path, expected_generation='native-generation')
        self.addCleanup(self.index.close)
        # These values are independently decoded from unchanged native tables.
        self.values = dict(self.native.values().items())
        self.order = sorted(self.rows, key=lambda r: (r.get('date') or '', r.get('start_time') or '', r['epoch_uuid']))
        self.definitions = self.native.catalog()

    def test_reusable_membership_matches_queries_across_connections_without_readmitting(self):
        from disco.metadata.typed_lifecycle import MembershipCache
        cache = MembershipCache(self.index, self.native)
        ids = [row['epoch_uuid'] for row in self.rows[:20]]
        factory = unittest.mock.Mock(return_value=iter(ids + ids[:2] + ['unknown']))
        handle = cache.get({'revision': 'one'}, ['source'], factory)
        self.assertIs(cache.get({'revision': 'one'}, ['source'], factory), handle)
        factory.assert_called_once()
        with TypedMetadataIndex.open_verified(self.index) as reader:
            plan = reader.explain(scope={'epoch_ids': handle, 'sources': ['source']})
            self.assertTrue(any('IN-OPERATOR' in row[3] for row in plan), plan)
            self.assertFalse(any('LIST SUBQUERY' in row[3] for row in plan), plan)
        for predicate in ({'all': []}, {'field': 'parameters/wide', 'operator': 'gt', 'value': 3},
                          {'field': 'parameters/a~1b~0', 'operator': 'contains', 'value': 1}):
            expected = self.index.preview(predicate, {'epoch_ids': ids, 'sources': ['source']},
                                          facet_fields=['parameters/wide'])
            with TypedMetadataIndex.open_verified(self.index) as reader:
                with patch.object(reader, '_supply_identities', side_effect=AssertionError('readmission')):
                    actual = reader.preview(predicate, {'epoch_ids': handle, 'sources': ['source']},
                                            facet_fields=['parameters/wide'])
                self.assertEqual(actual, expected)
                # Same connection can safely return to a caller-supplied scope.
                self.assertEqual(reader.membership(scope={'epoch_ids': []}), [])

    def test_reusable_membership_rebind_sources_and_live_reader_lifetime(self):
        import gc
        from disco.metadata.typed_lifecycle import MembershipCache
        cache = MembershipCache(self.index, self.native)
        first_id, second_id = [row['epoch_uuid'] for row in self.rows[:2]]
        first = cache.get({'revision': 'one'}, ['other', 'source'], lambda: [first_id])
        with TypedMetadataIndex.open_verified(self.index) as old:
            self.assertEqual(old.membership(scope={'epoch_ids': first, 'sources': ['other', 'source']}), [first_id])
            first_path = first.path
            del first
            for i in range(18):
                latest = cache.get({'revision': str(i)}, ['other', 'source'], lambda: [second_id])
            gc.collect()
            self.assertTrue(first_path.exists())
            self.assertEqual(old.membership(scope={'epoch_ids': old._membership, 'sources': ['source', 'other']}), [first_id])
            self.assertEqual(self.index.membership(scope={'epoch_ids': latest, 'sources': ['other', 'source']}), [second_id])
            with self.assertRaisesRegex(ValueError, 'source scope mismatch'):
                self.index.membership(scope={'epoch_ids': latest, 'sources': []})
        gc.collect()
        self.assertFalse(first_path.exists())

    def test_reusable_membership_failed_build_is_discarded_and_mutation_refuses(self):
        from disco.metadata.typed_lifecycle import MembershipCache
        cache = MembershipCache(self.index, self.native)
        def interrupted():
            yield self.rows[0]['epoch_uuid']
            raise InterruptedError('interrupted')
        with self.assertRaises(InterruptedError):
            cache.get({'revision': 'one'}, ['other'], interrupted)
        self.assertEqual(cache.entries, {})
        self.assertEqual(list(Path(cache.directory.name).iterdir()), [])
        handle = cache.get({'revision': 'one'}, ['other'], lambda: [self.rows[0]['epoch_uuid']])
        with handle.path.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'membership generation changed'):
            self.index.membership(scope={'epoch_ids': handle, 'sources': ['other']})

    def test_reusable_membership_concurrent_first_queries_build_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from disco.metadata.typed_lifecycle import MembershipCache
        cache = MembershipCache(self.index, self.native)
        ids = [row['epoch_uuid'] for row in self.rows]
        factory = unittest.mock.Mock(return_value=ids)
        def query(_):
            handle = cache.get({'revision': 'one'}, ['source', 'other'], factory)
            with TypedMetadataIndex.open_verified(self.index) as reader:
                return reader.membership(scope={'epoch_ids': handle, 'sources': ['source', 'other']})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(query, range(2)))
        self.assertEqual(results, [[row['epoch_uuid'] for row in self.order]] * 2)
        factory.assert_called_once()

    def truth(self, predicate=None, scope=None):
        result = []
        for row in self.order:
            values = self.values[row['epoch_uuid']]
            if predicate is not None and not predicates.matches(predicate, values):
                continue
            if scope:
                if any(not predicates.equal(values.get(k), v) for k, v in scope.items()
                       if k in {'cell', 'block', 'group', 'protocol'}):
                    continue
                if 'sources' in scope and row['source_sha256'] not in scope['sources']:
                    continue
                if 'epoch_ids' in scope and row['epoch_uuid'] not in scope['epoch_ids']:
                    continue
            result.append(row)
        return result

    def expected_facet(self, field, rows):
        buckets = []
        present = 0
        for row in rows:
            values = self.values[row['epoch_uuid']]
            if field not in values:
                continue
            present += 1
            value = values[field]
            found = next((b for b in buckets if predicates.equal(b['value'], value)), None)
            if found is None:
                buckets.append({'value': value, 'type': predicates.kind(value), 'count': 1})
            else:
                found['count'] += 1
        return {'values': buckets[:60], 'missing_count': len(rows)-present,
                'present_count': present, 'values_truncated': len(buckets)>60}

    def test_all_fields_predicates_scopes_compounds_and_validation_match_native_truth(self):
        cases = [{'all': []}, {'any': []}]
        for field in self.index.fields:
            observed = [v[field] for v in self.values.values() if field in v]
            cases.extend({'field': field, 'operator': op} for op in ('exists', 'missing', 'is_null'))
            if observed:
                cases.extend({'field': field, 'operator': op, 'value': value}
                             for value in observed[:2] for op in ('eq', 'ne'))
        cases += [
            {'field': 'parameters/wide', 'operator': 'gt', 'value': 3},
            {'field': 'parameters/a~1b~0', 'operator': 'contains', 'value': 1},
            {'all': [{'field':'parameters/sometimes','operator':'missing'},
                     {'not':{'field':'parameters/unseenBoolean','operator':'eq','value':False}}]},
            {'any': [{'field':'parameters/sometimes','operator':'is_null'},
                     {'field':'parameters/unseenBoolean','operator':'eq','value':False}]},
        ]
        for case in cases:
            outcomes = []
            for fn in (lambda: predicates.validate(case, self.definitions, self.values),
                       lambda: self.index._validate(case)):
                try:
                    outcomes.append(('ok', fn()))
                except ValueError as error:
                    outcomes.append(('error', str(error)))
            self.assertEqual(outcomes[0], outcomes[1], case)
            if outcomes[0][0] != 'ok':
                continue
            for scope in (None, {'cell':'cell-0'}, {'block':'block-0'}, {'group':'group'},
                    {'protocol':'VariableHistoryNoiseCurInject'},
                    {'epoch_ids':['epoch-0','epoch-1','epoch-2','epoch-8','epoch-9','epoch-17']},
                    {'sources':['source'], 'epoch_ids':['epoch-0','epoch-1','epoch-2','epoch-8','epoch-9','epoch-17']},
                    {'epoch_ids':[]}):
                with self.subTest(case=case, scope=scope):
                    expected = self.truth(case, scope)
                    self.assertEqual(list(self.index.iter_membership(case, scope)), [r['epoch_uuid'] for r in expected])
                    self.assertEqual(self.index.count(case, scope), len(expected))

    def test_pagination_exact_dtos_and_group_order(self):
        actual, cursor = [], None
        while True:
            page = self.index.page(cursor=cursor, limit=3)
            actual.extend(page['rows'])
            cursor = page['cursor']
            if cursor is None:
                break
        self.assertEqual(encoded(actual), encoded(self.order))
        for kind in ('cell', 'block'):
            grouped = {}
            for row in self.order:
                grouped.setdefault(row[kind+'_uuid'], []).append(row)
            keys = sorted(grouped) if kind == 'cell' else sorted(grouped,
                key=lambda key: (min(r['block_start_time'] or '' for r in grouped[key]), key))
            expected = [{'uuid': key, 'count': len(grouped[key])} for key in keys]
            result, cursor = [], None
            while True:
                page = self.index.groups(kind, cursor=cursor, limit=2)
                result.extend(page['groups']); cursor = page['cursor']
                if cursor is None:
                    break
            self.assertEqual(result, expected)

    def test_requested_facets_equal_independent_full_results_without_row_decoding(self):
        fields = list(self.index.fields)
        for scope in (None, {'cell':'cell-0'}, {'block':'block-0'}, {'group':'group'},
                      {'epoch_ids':['epoch-0','epoch-1','epoch-2','epoch-9']},
                      {'sources':['source'], 'epoch_ids':['epoch-0','epoch-1','epoch-2','epoch-9']},
                      {'epoch_ids':[]}):
            rows = self.truth(scope=scope)
            full = self.index.summaries(scope=scope, facet_fields=fields)
            for field in fields:
                self.assertEqual(encoded(full['facets'][field]), encoded(self.expected_facet(field, rows)))
            with patch.object(self.index, '_page', side_effect=AssertionError('summaries must not fetch DTOs')):
                selected = self.index.summaries(scope=scope, facet_fields=fields[:2])
            self.assertEqual(selected, {'count':len(rows),'facets':{f:full['facets'][f] for f in fields[:2]}})

    def test_sources_and_streamed_frozen_ids_are_conjunctive(self):
        ids = ['epoch-1', 'epoch-2', 'epoch-2', 'foreign', 'epoch-3', 'epoch-10']
        scope = {'sources':['source'], 'cell':'cell-0', 'epoch_ids':ids}
        expected = self.truth(scope=scope)
        streamed = {**scope, 'epoch_ids':(identity for identity in ids), 'sources':iter(['source'])}
        result = self.index.preview(scope=streamed, facet_fields=['parameters/sometimes'], limit=3)
        self.assertEqual(result['count'], len(expected))
        self.assertEqual(result['rows'], expected[:3])
        self.assertEqual(result['facets']['parameters/sometimes'], self.expected_facet('parameters/sometimes', expected))
        self.assertEqual(self.index.count(scope={'sources':[]}), 0)

    def test_explicit_membership_and_sources_do_not_need_a_structural_parent(self):
        ids = ['epoch-1','epoch-2','epoch-2','foreign','epoch-3','epoch-10']
        for sources in (['source'], ['other'], [], ['missing']):
            expected = self.truth(scope={'sources':sources, 'epoch_ids':ids})
            # Both key orders and one-shot iterators must keep conjunction,
            # duplicate/unknown handling and chronological pagination exact.
            for reverse in (False, True):
                pairs = [('sources', iter(sources)), ('epoch_ids', iter(ids))]
                scoped = dict(reversed(pairs) if reverse else pairs)
                result = self.index.preview(scope=scoped, facet_fields=['parameters/sometimes'], limit=3)
                self.assertEqual(result['rows'], expected[:3])
                self.assertEqual(result['count'], len(expected))
                self.assertEqual(result['facets']['parameters/sometimes'],
                                 self.expected_facet('parameters/sometimes', expected))
        self.assertEqual(self.index.membership(scope=iter(ids)),
                         [row['epoch_uuid'] for row in self.order if row['epoch_uuid'] in ids])

    def test_dictionary_fallback_evaluates_only_values_reachable_from_explicit_members(self):
        ids = ['epoch-1','epoch-2','epoch-9']
        for predicate in ({'field':'parameters/wide','operator':'gt','value':3},
                          {'field':'parameters/a~1b~0','operator':'contains','value':1}):
            expected = self.truth(predicate, {'epoch_ids':ids})
            original = predicates.matches
            visited = []
            def observe(node, values):
                visited.append(values)
                return original(node, values)
            with patch.object(predicates, 'matches', side_effect=observe):
                actual = self.index.membership(predicate, scope=iter(ids))
            self.assertEqual(actual, [row['epoch_uuid'] for row in expected])
            self.assertLessEqual(len(visited), len(ids))
            visited.clear()
            with patch.object(predicates, 'matches', side_effect=observe):
                self.assertEqual(self.index.membership(predicate, scope=[]), [])
            self.assertEqual(visited, [])

    def test_native_detail_decoder_and_source_bytes_preserved(self):
        for row in self.order:
            self.assertEqual(encoded(self.index.detail(row['epoch_uuid'])), encoded(self.native.details[row['epoch_uuid']]))
        self.assertEqual(hashlib.sha256(self.native.path.read_bytes()).hexdigest(), self.native_hash)
        self.assertTrue(self.receipt['no_detail_materialization'])

    def test_registry_is_complete_and_independent_of_returned_mutations(self):
        registry = self.index.field_registry()
        self.assertEqual({f['id'] for f in registry['fields']}, set(self.index.fields))
        self.assertTrue(all('choices' not in f and 'distinct_count' not in f for f in registry['fields']))
        boolean = next(f for f in registry['fields'] if f['id']=='parameters/unseenBoolean')
        self.assertEqual(boolean['types'], ['boolean'])
        registry['fields'].clear()
        self.assertTrue(self.index.field_registry()['fields'])

    def test_dynamic_schema_above_140_fields(self):
        rows, details, sources = fixture(count=2)
        details[rows[0]['epoch_uuid']]['parameters'].update({f'newField{i}':i for i in range(145)})
        native = DiskMetadataIndex.build(self.root/'new-native.sqlite', rows, details, sources, 'new', 'project')
        self.addCleanup(native.close)
        path = self.root/'new-typed.sqlite'
        build(native.path, path, min_free_gib=0)
        with TypedMetadataIndex(path) as index:
            fields = [f['id'] for f in index.field_registry()['fields']]
            self.assertGreater(len(fields), 140)
            self.assertEqual(set(index.summaries(facet_fields=fields)['facets']), set(fields))
            self.assertEqual(index.count({'field':'parameters/newField144','operator':'eq','value':144}),1)

    def test_verified_open_skips_hash_but_rejects_closed_or_changed_donor(self):
        with patch('disco.metadata.typed_index.file_sha', side_effect=AssertionError('No rehash')):
            with TypedMetadataIndex.open_verified(self.index) as reader:
                self.assertIsNot(reader.connection, self.index.connection)
                self.assertEqual(reader.generation_token, self.index.generation_token)
                self.assertEqual(reader.count(),len(self.rows))
        self.index.close()
        with self.assertRaisesRegex(ValueError,'closed'):
            TypedMetadataIndex.open_verified(self.index)

    def test_verified_open_checks_mutations_during_open_and_seal_changes(self):
        original = TypedMetadataIndex._open
        def changed(reader, *args):
            original(reader, *args)
            with reader.source_path.open('ab') as stream:
                stream.write(b'changed')
        with patch.object(TypedMetadataIndex,'_open',changed):
            with self.assertRaisesRegex(ValueError,'generation changed'):
                TypedMetadataIndex.open_verified(self.index)

    def test_seal_change_invalidates_live_reader(self):
        seal = Path(str(self.path)+'.sha256.json')
        seal.write_text(seal.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'generation changed'):
            TypedMetadataIndex.open_verified(self.index)

    def test_changes_after_open_and_wrong_generation_fail_closed(self):
        for kwargs in ({'expected_generation':'other'}, {'expected_project_uuid':'other'}):
            with self.assertRaisesRegex(ValueError,'mismatch'):
                TypedMetadataIndex(self.path, **kwargs)
        with self.native.path.open('ab') as stream:
            stream.write(b'changed')
        for action in (self.index.count, self.index.field_registry,
                       lambda:self.index.detail('epoch-0'), lambda:TypedMetadataIndex.open_verified(self.index)):
            with self.assertRaisesRegex(ValueError,'generation changed'):
                action()

    def test_tampered_sidecar_rejected_on_default_open(self):
        self.index.close()
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE typed_core SET cell_uuid=? WHERE epoch_id=1', ['fake'])
        with self.assertRaisesRegex(ValueError,'seal mismatch'):
            TypedMetadataIndex(self.path)

    def test_cancellation_is_explicit_and_resettable(self):
        self.index.cancel()
        with self.assertRaises(QueryCancelled):
            self.index.count()
        self.index.reset_cancel()
        self.assertEqual(self.index.count(),len(self.rows))

    def test_sql_progress_cancellation_is_not_reported_as_empty_result(self):
        calls = 0
        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 4
        def expensive(*args):
            return self.index.connection.execute('WITH RECURSIVE n(x) AS '
                '(SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(x) FROM n').fetchone()
        self.index.set_cancel_callback(cancelled)
        with patch.object(self.index,'_summaries',expensive):
            with self.assertRaises(QueryCancelled):
                self.index.summaries()
        self.index.set_cancel_callback(None)
        self.index.set_cancel_callback(lambda:True)
        with self.assertRaises(QueryCancelled):
            self.index.summaries(facet_fields=['epoch'])
        self.index.set_cancel_callback(None)
        self.assertEqual(self.index.count(),len(self.rows))

    def test_invalid_inputs_preserve_validation_errors_and_page_limits(self):
        cases = [None, [], {'all':None}, {'field':'foreign','operator':'eq','value':1},
            {'field':'parameters/wide','operator':'eq','value':2**60},
            {'field':'parameters/unseenBoolean','operator':'gt','value':1}]
        for case in cases:
            expected = None
            try:
                predicates.validate(case, self.definitions, self.values)
            except ValueError as error:
                expected = str(error)
            with self.assertRaises(ValueError) as actual:
                self.index._validate(case)
            self.assertEqual(str(actual.exception), expected)
        for limit in (0,101,True):
            with self.assertRaises(ValueError):
                self.index.page(limit=limit)
        for fields in (['epoch','epoch'], ['foreign'], ['epoch',{}], 'epoch'):
            with self.assertRaises(ValueError):
                self.index.summaries(facet_fields=fields)
        for scope in ('epoch-1', {'sources':'source'}, {'cell_uuid':'cell-0'}):
            with self.assertRaises(ValueError):
                self.index.count(scope=scope)

    def test_failed_build_has_no_seal_and_existing_destination_is_preserved(self):
        with self.assertRaises(ValueError):
            build(self.native.path,self.path)
        partial = self.root/'partial.sqlite'
        with self.assertRaisesRegex(RuntimeError,'time budget'):
            build(self.native.path,partial,max_seconds=0,min_free_gib=0)
        self.assertFalse(Path(str(partial)+'.sha256.json').exists())
        with self.assertRaises(OSError):
            TypedMetadataIndex(partial)


if __name__ == '__main__':
    unittest.main()
