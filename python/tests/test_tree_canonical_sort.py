"""Semantic differential checks; tiny owned metadata fixtures only."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

import workspace_tree as tree
import test_workspace_tree_pages as page_tests


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def old_order(value):
    # Frozen pre-change ordering, including JSON numeric tie breakers.
    if value is None:
        return (4, '')
    if type(value) in (int, float):
        return (0, value, tree.value_key(value))
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, str):
        return (2, value)
    return (3, tree.value_key(value))


class CanonicalSortTests(unittest.TestCase):
    def test_exact_serialized_order_and_stable_ties(self):
        values = [None, False, True, 0, -0.0, 0.0, 1, 1.0, -1, 10**100,
                  1e-100, 1e100, '', '1', 'é', 'e\u0301', [1, True, None],
                  {'b': 2, 'a': 1}, {'a': 1, 'b': 2}, [1.0], [1], 1]
        expected = sorted(enumerate(values), key=lambda pair: old_order(pair[1]))
        actual = sorted(enumerate(values), key=lambda pair: tree.value_order(
            pair[1], canonical=tree.value_key(pair[1])))
        self.assertEqual(encoded(actual), encoded(expected))
        for value in values:
            canonical = tree.value_key(value)
            wanted = encoded(old_order(value))
            with patch.object(tree, 'value_key', side_effect=AssertionError('duplicate encoding')):
                self.assertEqual(encoded(tree.value_order(value, canonical=canonical)), wanted)
                self.assertEqual(encoded(tree.field_value_order('parameters/value', value, canonical=canonical)), wanted)

    def test_joint_components_keep_original_order(self):
        field = tree.joint_id(['parameters/value', 'parameters/other'])
        values = [[{'present': True, 'value': value}, {'present': False}]
                  for value in (None, False, -0.0, 0, 0.0, 1, 1.0, [1, None], {'x': 1})]
        values.append([{'present': False}, {'present': True, 'value': None}])
        self.assertEqual(encoded(sorted(values, key=lambda v: tree.field_value_order(field, v))),
                         encoded(sorted(values, key=lambda v: tree.field_value_order(field, v, canonical=tree.value_key(v)))))

    def test_nonfinite_default_keys_still_reject(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tree.value_order(value)


class CanonicalPageTests(unittest.TestCase):
    def setUp(self):
        page_tests.TreePageTests.setUp(self)
        template = copy.deepcopy(next(iter(self.service.rows.values())))
        self.service.rows = {}; self.service.details = {}; self.service._fingerprints = {}
        values = [-0.0, 0, 0.0, False, True, 1, 1.0, None, '', '1', [1], [1.0],
                  [False, None], 1, 1e-20, 10**30]
        for index, value in enumerate(values + [None]):
            identity = str(uuid.UUID(int=index+1))
            self.service.rows[identity] = {**template, 'epoch_uuid':identity,
                'start_time':f'09/24/2026 12:00:{index:02d}:000000'}
            parameters = {'value':value, 'other':[1,index%2]}
            if index == len(values):parameters.pop('value')
            self.service.details[identity] = {'parameters':parameters,'properties':{},'metadata':{}}
            self.service._fingerprints[identity] = 'b'*64
        self.service.protocols[self.service.protocol_id]['result']['epochs'] = [
            {'uuid':identity,'metadata_hash':'b'*64} for identity in self.service.rows]

    def responses(self, body):
        pages = []
        root = self.pager.page(body)
        def walk(page):
            pages.append(page)
            for branch in page['branches']:
                walk(self.pager.page({**body,'path':branch['path'],'revision':root['revision']}))
            if page['has_more']:
                walk(self.pager.page({**body,'path':page['path'],'offset':page['offset']+page['limit'],
                                     'revision':root['revision']}))
        walk(root)
        for identity in self.service.rows:
            pages.append(self.pager.page({**body,'anchor_uuid':identity}))
        return encoded(pages)

    def test_complete_dtos_pagination_and_every_anchor_match_old_order(self):
        original_field_order = tree.field_value_order
        def legacy(field, value, **ignored):
            return original_field_order(field,value) if field.startswith('joint/') else old_order(value)
        for split in ('parameters/value', 'cell,parameters/value',
                      tree.joint_id(['parameters/value','parameters/other']), 'block'):
            with self.subTest(split=split):
                body = {'splits':split,'limit':2,'protocol_uuid':self.service.protocol_id}
                self.service._tree_page_scope_cache = None
                with patch('workspace_tree_pages.field_value_order', side_effect=legacy):
                    expected = self.responses(body)
                self.service._tree_page_scope_cache = None
                self.assertEqual(self.responses(body),expected)

    def test_nonfinite_rejected_through_actual_page_grouping(self):
        body = {'splits':'parameters/value'}
        scope = self.pager._scope(body)
        for value in (float('nan'), float('inf'), -float('inf')):
            values = copy.deepcopy(scope[2])
            values[next(iter(values))]['parameters/value'] = value
            modified = (*scope[:2], values, *scope[3:])
            with self.subTest(value=value), patch.object(self.pager,'_scope',return_value=modified):
                with self.assertRaises(ValueError):self.pager.page(body)


if __name__ == '__main__':unittest.main()
