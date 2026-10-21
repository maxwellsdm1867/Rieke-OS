"""Pure prepared navigation against the unchanged legacy grouping/page oracle."""
import cProfile
import random
import unittest
import uuid
from types import SimpleNamespace

from disco.navigation.prepared_tree import PreparedTree
from disco.navigation.tree_pages import TreePages, TreePath


def fixture(count=180):
    rows, values = [], {}
    variants = [None, '', True, 1, 1.0, -0.0, 0.0, [1, 2], {'a': 1}, 'alpha']
    for n in range(count):
        identity = str(uuid.UUID(int=n))
        row = dict(epoch_uuid=identity, cell_uuid=f'cell-{n % 13}', cell_label=f'Cell{n % 13}',
                   date=f'2026-10-{1 + n // 100:02d}', start_time=f'2026-10-01 12:{n // 60 % 60:02d}:{n % 60:02d}',
                   epoch_number=n, block_uuid=f'block-{n % 7}',
                   block_start_time=f'10/01/2026 11:{6 - n % 7:02d}:00',
                   duration_seconds=None if n == 12 else [1e16, 1.0, -1e16, 0.125][n % 4])
        rows.append(row)
        value = {'date': row['date'], 'cell': row['cell_uuid'], 'block': row['block_uuid']}
        if n % 11 != 10:
            value['parameters/value'] = variants[n % 11]
        if n % 5:
            value['parameters/other'] = None if n % 3 else False
        values[identity] = value
    rows.sort(key=lambda row: (row['date'], row['start_time'], row['epoch_uuid']))
    definitions = {field: {'id': field, 'label': field} for field in
                   ('date', 'cell', 'block', 'parameters/value', 'parameters/other')}
    definitions['joint/test'] = {'id': 'joint/test', 'label': 'joint',
                                 'components': ['parameters/value', 'parameters/other']}
    ranks = {row['epoch_uuid']: (row['date'], row['start_time'], row['epoch_uuid']) for row in rows}
    return rows, values, definitions, ranks


def legacy(rows, values, definitions, order):
    structural = TreePath(order, definitions)
    def render(representatives, catalog, scoped, field):
        children = []
        for row in representatives:
            present, value = structural.datum(scoped[row['epoch_uuid']], field)
            children.append({'value': value, 'missing': not present, 'label': str(value)})
        return {'children': children}
    service = SimpleNamespace(_render_tree=render, source_scope=lambda: {'revision': 'source'})
    pager = TreePages(service)
    scope = lambda body: (rows, {'fields': list(definitions.values())}, values, definitions, list(order), 'a' * 64)
    return lambda **body: pager._page({'revision': 'a' * 64, **body}, scope)


class PreparedTreeTests(unittest.TestCase):
    def assert_page(self, prepared, reference):
        for field in ('path', 'depth', 'offset', 'limit', 'kind', 'total', 'total_epochs', 'count',
                      'cells', 'duration_seconds', 'selection', 'has_more', 'anchor'):
            if field == 'selection':
                actual = {key: value for key, value in prepared[field].items() if key != 'duration_status'}
                self.assertEqual(actual, reference[field])
            elif field in reference:
                self.assertEqual(prepared[field], reference[field], field)
        for name in ('branches', 'ancestors'):
            self.assertEqual(len(prepared[name]), len(reference[name]))
            for actual, expected in zip(prepared[name], reference[name]):
                for field in ('key', 'value', 'missing', 'path', 'has_children', 'count', 'cells',
                              'duration_seconds', 'parent_offset'):
                    if field in expected:
                        self.assertEqual(actual[field], expected[field], (name, field))
        self.assertEqual([row['epoch_uuid'] for row in prepared['epochs']],
                         [row['epoch_uuid'] for row in reference['epochs']])

    def test_all_pages_and_anchors_match_legacy_typed_missing_joint_and_block_order(self):
        rows, values, definitions, ranks = fixture()
        for order in [('date', 'cell', 'block'), ('parameters/value', 'block'), ('joint/test',), ()]:
            with self.subTest(order=order):
                tree = PreparedTree.build(rows, values, definitions, order, scope_keys=ranks)
                oracle = legacy(rows, values, definitions, order)
                def walk(path):
                    first = tree.page(path, limit=7)
                    for offset in range(0, max(1, first['total']), 7):
                        for counts_only in (True, False):
                            self.assert_page(tree.page(path, offset, 7, counts_only=counts_only),
                                             oracle(path=list(path), offset=offset, limit=7, counts_only=counts_only))
                    if first['kind'] == 'branches':
                        for child in tree.page(path, limit=100)['branches']:
                            walk(child['path'])
                walk(())
                for row in rows[::17]:
                    identity = row['epoch_uuid']
                    self.assert_page(tree.page(anchor_uuid=identity, limit=7), oracle(anchor_uuid=identity, limit=7))
                self.assertEqual(set(tree.select()), set(ranks))
                self.assertGreater(tree.estimated_bytes, 0)

    def test_selection_exact_legacy_dfs_and_bound(self):
        rows, values, definitions, ranks = fixture(350)
        order = ('parameters/value', 'block')
        tree = PreparedTree.build(rows, values, definitions, order, scope_keys=ranks)
        oracle = legacy(rows, values, definitions, order)
        def visit(path):
            first = oracle(path=path, limit=100, counts_only=True)
            result = []
            for offset in range(0, first['total'], 100):
                page = first if offset == 0 else oracle(path=path, offset=offset, limit=100, counts_only=True)
                if page['kind'] == 'epochs':
                    result.extend(row['epoch_uuid'] for row in page['epochs'])
                else:
                    for branch in page['branches']:
                        result.extend(visit(branch['path']))
            return result
        self.assertEqual(tree.select(), tuple(visit([])))
        with self.assertRaises(ValueError):
            tree.select(max_count=100)
        with self.assertRaises(KeyError):
            tree.page(anchor_uuid='unknown')
        with self.assertRaises(KeyError):
            tree.page(path=['f' * 64])

    def test_delta_counts_representatives_ancestors_and_exact_duration_repair(self):
        rows, values, definitions, ranks = fixture(240)
        order = ('parameters/value', 'block')
        current = rows[:160]
        original = PreparedTree.build(current, values, definitions, order, scope_keys=ranks)
        before = original.page()
        removed = [row['epoch_uuid'] for row in current[::9]]
        added = rows[160:200]
        changed = original.apply(removals=removed, additions=added, values=values, scope_keys=ranks)
        self.assertEqual(original.page(), before)
        remaining = sorted([row for row in current if row['epoch_uuid'] not in removed] + added,
                           key=lambda row: ranks[row['epoch_uuid']])
        expected = PreparedTree.build(remaining, values, definitions, order, scope_keys=ranks)
        self.assertEqual(changed.select(), expected.select())
        self.assertEqual(changed.page()['cells'], len({row['cell_uuid'] for row in remaining}))
        self.assertEqual(changed.page()['duration_status'], 'pending')
        self.assertIsNone(changed.page()['duration_seconds'])
        self.assertEqual(changed.page(counts_only=True)['selection'], {'count': len(remaining)})
        self.assertGreaterEqual(changed.estimated_bytes, original.estimated_bytes)
        finished = changed.finish_durations()
        self.assertEqual(changed.page()['duration_status'], 'pending')
        self.assertEqual(finished.page(), expected.page())
        for row in remaining[::9]:
            self.assertEqual(finished.page(anchor_uuid=row['epoch_uuid']), expected.page(anchor_uuid=row['epoch_uuid']))

    def test_insert_before_replaces_block_representative_and_sort_position(self):
        rows, values, definitions, ranks = fixture(20)
        # A block's ordering uses its first canonical scope row, not its UUID.
        rows[0]['block_start_time'] = '10/01/2026 09:00:00'
        tree = PreparedTree.build(rows[1:], values, definitions, ('block',), scope_keys=ranks)
        changed = tree.apply(additions=[rows[0]], values=values, scope_keys=ranks).finish_durations()
        expected = PreparedTree.build(rows, values, definitions, ('block',), scope_keys=ranks)
        self.assertEqual(changed.page(), expected.page())
        removed = changed.apply(removals=[rows[0]['epoch_uuid']]).finish_durations()
        self.assertEqual(removed.page(), tree.page())

    def test_random_atomic_deltas_equal_fresh_rebuild(self):
        rows, values, definitions, ranks = fixture(120)
        active = {row['epoch_uuid']: row for row in rows[:60]}
        tree = PreparedTree.build(active.values(), values, definitions, ('cell', 'block'), scope_keys=ranks)
        rng = random.Random(91)
        for _ in range(40):
            row = rng.choice(rows)
            identity = row['epoch_uuid']
            if identity in active:
                changed = tree.apply(removals=[identity])
                del active[identity]
            else:
                changed = tree.apply(additions=[row], values=values, scope_keys=ranks)
                active[identity] = row
            expected = PreparedTree.build(sorted(active.values(), key=lambda row: ranks[row['epoch_uuid']]),
                                          values, definitions, ('cell', 'block'), scope_keys=ranks)
            tree = changed.finish_durations()
            self.assertEqual(tree.page(), expected.page())
            self.assertEqual(tree.select(), expected.select())
        before = tree.page()
        with self.assertRaises(KeyError):
            tree.apply(removals=[next(iter(active)), 'not-present'])
        self.assertEqual(tree.page(), before)

    def test_leaf_window_anchor_and_delta_operation_growth_is_logarithmic(self):
        work = []
        for count in (100, 10000):
            rows, values, definitions, ranks = fixture(count)
            for row in rows:
                values[row['epoch_uuid']]['cell'] = 'one-cell'
            tree = PreparedTree.build(rows, values, definitions, ('cell',), scope_keys=ranks)
            profile = cProfile.Profile()
            profile.enable()
            page = tree.page(anchor_uuid=rows[-5]['epoch_uuid'], limit=4)
            changed = tree.apply(removals=[rows[-5]['epoch_uuid']])
            changed.page(path=page['path'], offset=count - 6, limit=4)
            profile.disable()
            calls = sum(item.callcount for item in profile.getstats()
                        if hasattr(item.code, 'co_filename') and item.code.co_filename.endswith('prepared_tree.py'))
            work.append(calls)
            self.assertEqual(len(page['epochs']), 4)
        self.assertLess(work[1], work[0] * 3, work)

    def test_high_fanout_branch_offsets_and_deltas_are_bounded_and_balanced(self):
        measured = []
        for count in (100, 10000):
            rows, values, definitions, ranks = fixture(count)
            for row in rows:
                values[row['epoch_uuid']]['cell'] = row['epoch_uuid']
            tree = PreparedTree.build(rows, values, definitions, ('cell', 'block'), scope_keys=ranks)
            def calls(action):
                profile = cProfile.Profile()
                profile.enable()
                result = action()
                profile.disable()
                total = sum(item.callcount for item in profile.getstats()
                            if hasattr(item.code, 'co_filename') and item.code.co_filename.endswith('prepared_tree.py'))
                return result, total
            page, read_cost = calls(lambda: tree.page(offset=count - 5, limit=4))
            changed, delta_cost = calls(lambda: tree.apply(removals=[rows[0]['epoch_uuid'], rows[-1]['epoch_uuid']]))
            self.assertEqual(len(page['branches']), 4)
            self.assertEqual(changed.page()['count'], count - 2)
            self.assertEqual(changed.page()['branches'][0]['duration_status'], 'ready')
            measured.append((read_cost, delta_cost))
            seen = set()
            def verify(node):
                if node is None or id(node) in seen:
                    return
                seen.add(id(node))
                if hasattr(node, 'height'):
                    left_size, right_size = (node.left.size if node.left else 0), (node.right.size if node.right else 0)
                    left_height, right_height = (node.left.height if node.left else 0), (node.right.height if node.right else 0)
                    self.assertEqual(node.size, 1 + left_size + right_size)
                    self.assertEqual(node.height, 1 + max(left_height, right_height))
                    self.assertLessEqual(abs(left_height - right_height), 1)
                    verify(node.left); verify(node.right); verify(node.value)
                elif hasattr(node, 'children'):
                    for content in (node.children, node.lookup, node.leaves, node.cells):
                        verify(content)
            verify(changed._root)
            verify(changed._entries)
        self.assertLess(measured[1][0], measured[0][0] * 3, measured)
        self.assertLess(measured[1][1], measured[0][1] * 3, measured)

    def test_group_values_are_owned_bounded_copies_and_empty_layout_needs_no_projection(self):
        rows, values, definitions, ranks = fixture(20)
        tree = PreparedTree.build(rows, values, definitions, ('parameters/value',), scope_keys=ranks)
        before = tree.page()
        branch = next(child for child in before['branches'] if isinstance(child['value'], list))
        branch['value'].append('changed')
        branch['values']['parameters/value'].append('also changed')
        after = tree.page()
        current = next(child for child in after['branches'] if child['key'] == branch['key'])
        self.assertEqual(current['value'], [1, 2])
        self.assertEqual(current['values']['parameters/value'], [1, 2])
        empty_layout = PreparedTree.build(rows, {}, definitions, (), scope_keys=ranks)
        self.assertEqual(empty_layout.page()['total'], len(rows))

    def test_duration_repair_preserves_canonical_sum_instead_of_subtracting(self):
        rows, values, definitions, ranks = fixture(3)
        for row, duration in zip(rows, (1e16, 1.0, -1e16)):
            row['duration_seconds'] = duration
        tree = PreparedTree.build(rows, {}, definitions, (), scope_keys=ranks)
        self.assertEqual(tree.page()['duration_seconds'], sum(row['duration_seconds'] for row in rows))
        changed = tree.apply(removals=[rows[1]['epoch_uuid']])
        self.assertIsNone(changed.page()['duration_seconds'])
        self.assertEqual(changed.finish_durations().page()['duration_seconds'], 0.0)
        self.assertEqual(tree.page()['duration_seconds'], 0.0)

    def test_empty_scope_empty_split_and_invalid_deltas(self):
        rows, values, definitions, ranks = fixture(3)
        tree = PreparedTree.build([], {}, definitions, ())
        self.assertEqual(tree.page()['duration_seconds'], 0)
        self.assertEqual(tree.select(), ())
        filled = tree.apply(additions=rows, values=values, scope_keys=ranks)
        empty = filled.apply(removals=list(ranks)).finish_durations()
        self.assertEqual(empty.page(), tree.page())
        with self.assertRaises(ValueError):
            filled.apply(additions=[rows[0]], values=values, scope_keys=ranks)
        with self.assertRaises(ValueError):
            filled.apply(removals=[rows[0]['epoch_uuid']] * 2)
        with self.assertRaises(ValueError):
            PreparedTree.build(list(reversed(rows)), values, definitions, (), scope_keys=ranks)


if __name__ == '__main__':
    unittest.main()
