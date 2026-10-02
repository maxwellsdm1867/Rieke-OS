"""Structural cache agrees with the general tree, including revision safeguards."""
from pathlib import Path
import tempfile
import copy
import unittest
import sys
import gc
import weakref
from unittest.mock import patch

from workspace_disk_index import DiskMetadataIndex
from workspace_tree_pages import TreePages, StaleTreePage, _NavigationValues
from test_workspace_api import FixtureService
import test_workspace_refresh_cache as refresh_fixture


class StructuralNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = FixtureService(self.temp.name)
        # Multiple valid recording dates and Unicode labels; unknown durations.
        for number, row in enumerate(self.service.rows.values()):
            row['date'] = '2026-09-24' if number % 2 else '2026-09-25'
            row['start_time'] = ('09/24/2026' if number % 2 else '09/25/2026') + row['start_time'][10:]
            row['cell_label'] += ' · 日期 α'
            row['duration_seconds'] = None if number == 0 else 1.0
        self.pager = TreePages(self.service)

    def index(self):
        service = self.service
        index = DiskMetadataIndex.build(Path(self.temp.name)/'structural.sqlite',
            service.rows, service.details, service.sources, 'structural-v1',
            service.project['project_uuid'])
        service.disk_index = index
        self.addCleanup(index.close)
        return index

    def pages(self, body):
        root = self.pager.page(body)
        result = []
        def walk(page):
            result.append(page)
            for branch in page['branches']:
                walk(self.pager.page({**body, 'path': branch['path'],
                                     'revision': root['revision']}))
            if page['has_more']:
                walk(self.pager.page({**body, 'path':page['path'],
                    'offset':page['offset']+page['limit'], 'revision':root['revision']}))
        walk(root)
        return result

    def test_all_pages_offsets_anchors_order_counts_and_revisions_match_general_path(self):
        bodies = [{'splits': order, 'limit': 1, **scope}
                  for order in ('date,cell,block', 'block,date,cell', 'cell', 'date')
                  for scope in ({}, {'protocol_uuid':self.service.protocol_id},
                                {'filters':{'cell_type':'ON'}})]
        expected = [self.pages(body) for body in bodies]
        anchors = [{'protocol_uuid':self.service.protocol_id,
                    'splits':'date,cell,block', 'anchor_uuid':identity, 'limit':2}
                   for identity in self.service.rows]
        expected_anchors = [self.pager.page(body) for body in anchors]
        index = self.index()
        # Structural navigation must never read the EAV projection or decorate
        # the entire protocol's rows with curation merely to compute counts.
        with patch.object(index, 'values', side_effect=AssertionError('No EAV matrix')), \
             patch.object(self.service, 'curation_provider', side_effect=AssertionError('No full curation read')):
            self.assertEqual([self.pages(body) for body in bodies], expected)
            self.assertEqual([self.pager.page(body) for body in anchors], expected_anchors)

    def test_cache_refuses_membership_fingerprint_source_binding_and_file_changes(self):
        index = self.index()
        body = {'protocol_uuid':self.service.protocol_id, 'splits':'date,cell,block'}
        root = self.pager.page(body)
        self.service.protocols[self.service.protocol_id]['result']['epochs'].pop()
        with self.assertRaises(StaleTreePage):
            self.pager.page({**body, 'revision':root['revision']})
        root = self.pager.page(body)
        self.service._fingerprints[self.service.ids[0]] = 'c'*64
        with self.assertRaises(StaleTreePage):
            self.pager.page({**body, 'revision':root['revision']})
        source = self.pager.page({'splits':'date'})
        self.service.set_source_state_provider(lambda: {'a'*64:{'query_excluded':True}})
        with self.assertRaises(StaleTreePage):
            self.pager.page({'splits':'date', 'revision':source['revision']})
        self.assertEqual(self.pager.page({'splits':'date'})['count'],0)
        root = self.pager.page(body)
        binding = self.binding(self.service.ids[0], 'c'*64)
        self.service.set_binding_provider(lambda protocol:binding)
        with self.assertRaises(StaleTreePage):
            self.pager.page({**body, 'revision':root['revision']})
        with index.path.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            self.pager.page(body)

    @staticmethod
    def binding(identity, fingerprint='b'*64):
        return {'version':1, 'revision_uuid':'changed', 'recipe':{
            'epochs':[{'uuid':identity, 'metadata_hash':fingerprint}],
            'source_revisions':['a'*64], 'predicate':{'all':[]},
            'tree_view':{'fields':['date','cell','block']},
            'splits':'date,cell,block', 'name':'Custom bound selection'}}

    def test_unmatched_custom_header_uses_full_binding_and_detects_membership_change(self):
        self.index()
        identity = self.service.ids[0]
        binding = self.binding(identity)
        self.service.set_binding_provider(lambda protocol:binding,
                                          header_provider=lambda protocol:None)
        body = {'protocol_uuid':self.service.protocol_id, 'splits':'date,cell,block'}
        root = self.pager.page(body)
        self.assertEqual(root['count'],1)
        leaf = self.pager.page({**body, 'anchor_uuid':identity})
        self.assertEqual([row['epoch_uuid'] for row in leaf['epochs']],[identity])
        binding['recipe']['epochs'] = [{'uuid':self.service.ids[1], 'metadata_hash':'b'*64}]
        with self.assertRaises(StaleTreePage):
            self.pager.page({**body, 'revision':root['revision']})
        self.assertEqual(self.pager.page({**body, 'anchor_uuid':self.service.ids[1]})['count'],1)

    def test_custom_membership_policies_are_authoritative_on_each_page(self):
        self.index()
        body = {'protocol_uuid':self.service.protocol_id, 'splits':'date,cell,block'}
        for method in ('query_result', 'filtered_rows', '_tree_rows', '_filter_rows'):
            # A native cache populated before installing the policy is unsafe too.
            self.pager.page(body)
            original = getattr(self.service,method)
            chosen = [self.service.ids[0]]
            def custom(*args, **kwargs):
                result = original(*args, **kwargs)
                if method == 'query_result':
                    result['epochs'] = [member for member in result['epochs'] if member['uuid'] in chosen]
                    return result
                return [row for row in result if row['epoch_uuid'] in chosen]
            with self.subTest(method=method), patch.object(self.service,method,side_effect=custom):
                root = self.pager.page(body)
                self.assertEqual(root['count'],1)
                leaf = self.pager.page({**body, 'anchor_uuid':chosen[0]})
                self.assertEqual([row['epoch_uuid'] for row in leaf['epochs']],chosen)
                chosen[:] = [self.service.ids[1]]
                with self.assertRaises(StaleTreePage):
                    self.pager.page({**body, 'revision':root['revision']})
                self.assertEqual(self.pager.page({**body, 'anchor_uuid':chosen[0]})['count'],1)

    def test_borrowed_scope_is_reused_across_depths_and_anchor_requests(self):
        self.index()
        body = {'protocol_uuid':self.service.protocol_id, 'splits':'date,cell,block'}
        root = self.pager.page(body)
        scope = next(iter(self.service._tree_page_scope_cache[1].values()))[0]
        self.assertIs(scope[2].rows, self.service.rows)
        self.assertTrue(all(row is self.service.rows[row['epoch_uuid']] for row in scope[0]))
        with patch.object(self.pager, '_build_scope', side_effect=AssertionError('Reuse structural scope')):
            self.pager.page({**body, 'path':root['branches'][0]['path'], 'revision':root['revision']})
            self.pager.page({**body, 'anchor_uuid':self.service.ids[0]})
        self.assertEqual(len(self.service._tree_page_scope_cache[1]), 1)

    def test_replaced_rows_release_previous_cached_values_on_next_navigation(self):
        self.index()
        body = {'splits':'date,cell,block'}
        root = self.pager.page(body)
        old = weakref.ref(next(iter(self.service._tree_page_scope_cache[1].values()))[0][2])
        self.service.rows = copy.deepcopy(self.service.rows)
        self.assertEqual(self.pager.page(body), root)
        gc.collect()
        self.assertIsNone(old())

    def test_matching_immutable_binding_owner_and_mismatched_header_owner(self):
        from workspace_explorer import ExplorerHistory
        from test_workspace_curation import Table
        self.index()
        service = self.service
        bindings = Table(('project_uuid', 'protocol_uuid'))
        revisions = Table(('project_uuid', 'revision_uuid'))
        events = Table(('event_uuid',))
        history = ExplorerHistory(object(), service.project['project_uuid'],
                                  event_table=events, revision_table=revisions, binding_table=bindings)
        first = self.binding(service.ids[0])
        history._recipe_cache['first'] = first['recipe']
        bindings.insert1({'project_uuid':service.project['project_uuid'],
                          'protocol_uuid':service.protocol_id, 'version':1, 'revision_uuid':'first'})
        service.set_binding_provider(history.protocol_binding, header_provider=history.protocol_binding_header)
        body = {'protocol_uuid':service.protocol_id, 'splits':'date,cell,block'}
        root = self.pager.page(body)
        self.assertEqual(root['count'], 1)
        self.assertIsInstance(next(iter(service._tree_page_scope_cache[1].values()))[0][2], _NavigationValues)
        with patch.object(self.pager, '_build_scope', side_effect=AssertionError('Warm bound scope')):
            self.assertEqual(self.pager.page(body), root)
        history._recipe_cache['second'] = self.binding(service.ids[1])['recipe']
        bindings.rows[0].update(version=2, revision_uuid='second')
        with self.assertRaises(StaleTreePage):
            self.pager.page({**body, 'revision':root['revision']})
        self.assertEqual(self.pager.page({**body, 'anchor_uuid':service.ids[1]})['count'], 1)
        other = ExplorerHistory(object(), service.project['project_uuid'],
                                event_table=events, revision_table=revisions,
                                binding_table=Table(('project_uuid', 'protocol_uuid')))
        service.set_binding_provider(history.protocol_binding, header_provider=other.protocol_binding_header)
        scope = self.pager._scope(body)
        self.assertNotIsInstance(scope[2], _NavigationValues)
        self.assertEqual([row['epoch_uuid'] for row in scope[0]], service.ids[1:])

    def test_group_cache_reservation_bounds_lazy_growth(self):
        self.index()
        self.pages({'splits':'date,cell,block', 'limit':1})
        for result, _, retained in self.service._tree_page_scope_cache[1].values():
            values = result[2]
            self.assertIsInstance(values, _NavigationValues)
            self.assertLessEqual(values.group_bytes, values.grouping_budget)
            self.assertLessEqual(len(values.group_cache),128)
            self.assertGreaterEqual(retained, values.grouping_budget)
            # Measure allocations actually reachable from the populated cache,
            # excluding immutable rows/scalars/field names borrowed elsewhere.
            # This checks the estimate independently of its own byte counter.
            borrowed = {id(row) for row in self.service.rows.values()}
            borrowed.update(id(value) for row in self.service.rows.values()
                            for value in row.values())
            borrowed.update(id(field) for field in values.fields)
            borrowed.update(id(key) for entry in values.group_cache.values()
                            for bucket in entry[1] for key in bucket)
            borrowed.update(id(key) for entry in values.group_cache.values()
                            for bucket in entry[1] for key in bucket['summary'])
            seen = set(borrowed)
            def allocated(value):
                if id(value) in seen:
                    return 0
                seen.add(id(value))
                cost = sys.getsizeof(value)
                if isinstance(value,dict):
                    cost += sum(allocated(key)+allocated(item) for key,item in value.items())
                elif isinstance(value,(list,tuple)):
                    cost += sum(allocated(item) for item in value)
                return cost
            self.assertLessEqual(allocated(values.group_cache), values.group_bytes)


class NavigationGroupAdmissionTests(unittest.TestCase):
    def test_high_fanout_groups_are_summarized_before_oversize_rejection(self):
        rows = [{'cell_uuid':str(number), 'duration_seconds':1.0} for number in range(100)]
        values = _NavigationValues(dict(enumerate(rows)), ['cell'])
        buckets = [{'row':row, 'value':row['cell_uuid'], 'rows':[row]} for row in rows]
        values.remember_groups(('cell', id(rows)), rows, buckets)
        self.assertTrue(all(bucket['summary']['count'] == 1 for bucket in buckets))
        self.assertEqual(values.group_cache, {})
        self.assertEqual(values.group_bytes, 0)

    def test_distinct_groups_evict_within_reservation_and_entry_limit(self):
        row = {'cell_uuid':'one', 'duration_seconds':1.0}
        values = _NavigationValues({'one':row}, ['cell'])
        first = None
        currents = []  # Keep evicted list identities alive for a deterministic test.
        for number in range(150):
            current = [row]
            currents.append(current)
            key = ('cell', id(current))
            if first is None:
                first = key
            values.remember_groups(key, current, [{'row':row, 'value':'one', 'rows':[row]}])
            self.assertLessEqual(values.group_bytes, values.grouping_budget)
            self.assertLessEqual(len(values.group_cache), 128)
        self.assertNotIn(first, values.group_cache)
        self.assertEqual(values.group_bytes, sum(entry[2] for entry in values.group_cache.values()))


class NavigationRefreshLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = refresh_fixture.RefreshCacheTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service

    def test_successful_publication_releases_previous_navigation_generation(self):
        TreePages(self.service).page({'splits':'date,cell,block'})
        cache = self.service._tree_page_scope_cache
        values = next(iter(cache[1].values()))[0][2]
        old_values = weakref.ref(values)
        del values, cache
        old_rows = self.service.rows
        previous_index = self.service.disk_index
        result = self.service.refresh()
        self.assertEqual(result['metadata_index'], 'reused')
        self.assertTrue(result['discovery_indexes_preserved'])
        self.assertEqual(self.service.disk_index.generation, previous_index.generation)
        self.assertEqual(self.service.disk_index.path, previous_index.path)
        self.assertTrue(self.service._tree_page_scope_cache is None,
                        'Verified unchanged-index publication must release navigation cache')
        self.assertIsNot(self.service.rows,old_rows)
        gc.collect()
        self.assertIsNone(old_values())

    def test_new_generation_publication_releases_previous_navigation_cache(self):
        TreePages(self.service).page({'splits':'date,cell,block'})
        old = weakref.ref(next(iter(self.service._tree_page_scope_cache[1].values()))[0][2])
        generation = self.service.disk_index.generation
        self.fixture.add_source('three')
        result = self.service.refresh()
        self.assertEqual(result['metadata_index'], 'built')
        self.assertNotEqual(self.service.disk_index.generation, generation)
        self.assertTrue(self.service._tree_page_scope_cache is None,
                        'Verified new-generation publication must release navigation cache')
        gc.collect()
        self.assertIsNone(old())

    def test_failed_verification_does_not_replace_published_navigation_cache(self):
        TreePages(self.service).page({'splits':'date,cell,block'})
        cache, rows = self.service._tree_page_scope_cache, self.service.rows
        metadata = Path(self.fixture.records[0]['manifest']['metadata_path'])
        metadata.write_text(metadata.read_text().replace('30.0','31.0'))
        with self.assertRaisesRegex(ValueError,'metadata checksum changed'):
            self.service.refresh()
        self.assertIs(self.service._tree_page_scope_cache,cache)
        self.assertIs(self.service.rows,rows)


if __name__ == '__main__':
    unittest.main()
