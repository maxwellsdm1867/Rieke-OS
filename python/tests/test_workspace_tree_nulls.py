"""Nullable built-in grouping agrees across full trees, pages and path matching."""
import copy
from pathlib import Path
import tempfile
import unittest
import uuid

from disco.metadata.disk_index import DiskMetadataIndex
from disco.navigation.tree import joint_id
from disco.navigation.tree_pages import TreePages, TreePath
from disco.workbench.recipes import checksum
from test_workspace_api import FixtureService


class NullableTreeTests(unittest.TestCase):
    def fixture(self, indexed):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        service = FixtureService(temporary.name)
        templates = [copy.deepcopy(service.rows[key]) for key in service.ids]
        service.rows, service.details, service._fingerprints = {}, {}, {}
        for number in range(6):
            identity = str(uuid.UUID(int=number + 1))
            row = {**templates[number // 3], 'epoch_uuid': identity,
                   'epoch_number': number + 1,
                   'start_time': f'09/24/2026 12:00:0{number}:000000'}
            if number < 3:
                row.update(cell_type=None, group_label=None, block_start_time=None)
            service.rows[identity] = row
            parameters = {'value': None} if number < 2 else {'value': 1} if number in (2, 5) else {}
            service.details[identity] = {'parameters': parameters, 'properties': {},
                'metadata': {'epoch': {'uuid': identity}, 'cell': {
                    'uuid': row['cell_uuid'], 'start_time': templates[number // 3]['start_time']}}}
            service._fingerprints[identity] = 'b' * 64
        service.ids = list(service.rows)
        service.protocols[service.protocol_id]['result']['epochs'] = [
            {'uuid': identity, 'metadata_hash': 'b' * 64} for identity in service.ids[:5]]
        if indexed:
            index = DiskMetadataIndex.build(Path(temporary.name) / 'nullable.sqlite',
                service.rows, service.details, service.sources, 'nullable-v1',
                service.project['project_uuid'])
            self.addCleanup(index.close)
            service.disk_index = index
        return service

    def assert_public_parity(self, service, splits, protocol):
        before = copy.deepcopy((service.rows, service.details, service.protocols))
        full = service.tree(protocol, splits=splits)
        body = {'splits': splits, 'limit': 1,
                **({'protocol_uuid': protocol} if protocol else {})}
        pager = TreePages(service)
        root = pager.page(body)
        expected_ids = set(service.ids[:5] if protocol else service.ids)
        paths = {}

        def walk(node, path):
            offset, leaves, seen = 0, [], []
            while True:
                page = pager.page({**body, 'path': path, 'offset': offset,
                                   'revision': root['revision']})
                self.assertEqual(page['selection']['count'], node['count'])
                if 'epoch_uuids' in node:
                    leaves.extend(row['epoch_uuid'] for row in page['epochs'])
                else:
                    field = node['field']
                    children = {checksum({'field': field, 'present': not child['missing'],
                        **({'value': child['value']} if not child['missing'] else {})}): child
                        for child in node['children']}
                    for branch in page['branches']:
                        self.assertIn(branch['key'], children)
                        child = children[branch['key']]
                        self.assertEqual((branch['missing'], branch['value'], branch['label'], branch['count']),
                                         (child['missing'], child['value'], child['label'], child['count']))
                        seen.append(branch['key'])
                        leaves.extend(walk(child, branch['path']))
                if not page['has_more']:
                    break
                offset += page['limit']
            if 'epoch_uuids' in node:
                self.assertCountEqual(leaves, node['epoch_uuids'])
                for identity in leaves:
                    paths[identity] = path
            else:
                self.assertCountEqual(seen, children)
            return leaves

        self.assertCountEqual(walk(full, []), expected_ids)
        for identity in expected_ids:
            anchored = pager.page({**body, 'anchor_uuid': identity})
            self.assertEqual(anchored['path'], paths[identity])
            self.assertIn(identity, [row['epoch_uuid'] for row in anchored['epochs']])
            self.assertEqual([a['key'] for a in anchored['ancestors']], paths[identity])
        self.assertEqual((service.rows, service.details, service.protocols), before)
        return full

    def test_nullable_builtin_branches_match_full_tree_and_locate_exact_members(self):
        for indexed in (False, True):
            for split in ('cell type,metadata/cell/start_time', 'group label', 'block time'):
                for protocol_scope in (False, True):
                    with self.subTest(indexed=indexed, split=split, protocol=protocol_scope):
                        service = self.fixture(indexed)
                        full = self.assert_public_parity(service, split,
                            service.protocol_id if protocol_scope else None)
                        missing = [child for child in full['children'] if child['missing']]
                        self.assertEqual(len(missing), 1)
                        self.assertEqual((missing[0]['label'], missing[0]['count']), ('Not recorded', 3))

    def test_dynamic_explicit_null_missing_and_joint_components_stay_distinct(self):
        for indexed in (False, True):
            for protocol_scope in (False, True):
                with self.subTest(indexed=indexed, protocol=protocol_scope):
                    service = self.fixture(indexed)
                    protocol = service.protocol_id if protocol_scope else None
                    full = self.assert_public_parity(service, 'parameters/value', protocol)
                    nulls = [child for child in full['children'] if child['value'] is None]
                    self.assertEqual({child['missing'] for child in nulls}, {False, True})
                    joint = self.assert_public_parity(service,
                        joint_id(['cell type', 'parameters/value']), protocol)
                    parts = [child['value'] for child in joint['children']]
                    # Built-in nulls are "not recorded" inside joint keys too (predicate contract v2).
                    self.assertTrue(any(value[0] == {'present': False} for value in parts))
                    self.assertFalse(any(value[0] == {'present': True, 'value': None} for value in parts))
                    self.assertTrue(any(value[1] == {'present': True, 'value': None} for value in parts))
                    self.assertTrue(any(value[1] == {'present': False} for value in parts))

    def test_builtin_path_keys_normalize_null_but_preserve_empty_and_dynamic_null(self):
        for field in ('cell type', 'group label', 'block time'):
            with self.subTest(field=field):
                path = TreePath([field], {field: {}})
                missing = checksum({'field': field, 'present': False})
                self.assertEqual(path.key({field: None}, field), missing)
                self.assertEqual(path.key({}, field), missing)
                self.assertNotEqual(path.key({field: ''}, field), missing)
                self.assertTrue(TreePath([field], {field: {}}, [missing]).matches({field: None}))
        dynamic = TreePath(['parameters/value'], {'parameters/value': {}})
        self.assertNotEqual(dynamic.key({}, 'parameters/value'),
                            dynamic.key({'parameters/value': None}, 'parameters/value'))

    def test_predicates_count_builtin_nulls_exactly_as_the_tree_does(self):
        # Predicate contract v2: a built-in recorded as None is "not recorded".
        for indexed in (False, True):
            for field in ('cell type', 'group label', 'block time'):
                with self.subTest(indexed=indexed, field=field):
                    service = self.fixture(indexed)
                    full = service.tree(None, splits=field)
                    missing = sum(child['count'] for child in full['children'] if child['missing'])
                    recorded = {child['value']: child['count'] for child in full['children'] if not child['missing']}
                    def count(node):
                        return len(service.match_predicate(node)[1])
                    self.assertEqual(count({'field': field, 'operator': 'missing'}), missing)
                    self.assertEqual(count({'field': field, 'operator': 'exists'}), sum(recorded.values()))
                    self.assertEqual(count({'field': field, 'operator': 'is_null'}), 0)
                    value = next(iter(recorded))
                    self.assertEqual(count({'field': field, 'operator': 'ne', 'value': value}),
                                     sum(amount for key, amount in recorded.items() if key != value))
                    self.assertEqual(count({'not': {'field': field, 'operator': 'exists'}}), missing)

    def test_reinterpretation_detection_is_limited_to_changed_builtin_leaves(self):
        from disco.navigation.predicates import reinterpretation_required, PREDICATE_VERSION, BUILT_IN_FIELDS
        from disco.navigation.tree import BASE_FIELDS
        self.assertEqual(PREDICATE_VERSION, 2)
        self.assertEqual(BUILT_IN_FIELDS, set(BASE_FIELDS))
        changed = [{'field': 'cell type', 'operator': 'missing'}, {'field': 'cell type', 'operator': 'exists'},
                   {'field': 'group label', 'operator': 'ne', 'value': 'x'},
                   {'field': 'block time', 'operator': 'is_null'}, {'field': 'cell type', 'operator': 'eq', 'value': None},
                   {'any': [{'field': 'parameters/x', 'operator': 'eq', 'value': 1},
                            {'not': {'field': 'cell type', 'operator': 'not_in', 'value': ['a']}}]}]
        unchanged = [{'all': []}, {'field': 'cell type', 'operator': 'eq', 'value': 'ON'},
                     {'field': 'parameters/value', 'operator': 'missing'}, {'field': 'cell', 'operator': 'in', 'value': ['a']}]
        for node in changed:
            self.assertTrue(reinterpretation_required(node, 1), node)
            self.assertFalse(reinterpretation_required(node, 2), node)
        for node in unchanged:
            self.assertFalse(reinterpretation_required(node, 1), node)
