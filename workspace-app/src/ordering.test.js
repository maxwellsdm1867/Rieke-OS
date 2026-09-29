import test from 'node:test';
import assert from 'node:assert/strict';
import { reorderIds, moveShortcut } from './ordering.js';

test('tree reordering preserves exact field identities and input while accounting for source removal', () => {
  const ids = ['date', 'parameters/currentSD', 'cell', 'block'];
  assert.deepEqual(reorderIds(ids, 'date', 'cell', 'after'), ['parameters/currentSD', 'cell', 'date', 'block']);
  assert.deepEqual(reorderIds(ids, 'block', 'date'), ['block', 'date', 'parameters/currentSD', 'cell']);
  assert.deepEqual(reorderIds(ids, 'date', null), ['parameters/currentSD', 'cell', 'block', 'date']);
  assert.deepEqual(ids, ['date', 'parameters/currentSD', 'cell', 'block']);
  for (const placement of ['before', 'after']) for (const source of ids) for (const target of ids) {
    assert.deepEqual([...reorderIds(ids, source, target, placement)].sort(), [...ids].sort());
  }
});

test('invalid or unchanged drops are noops, preventing redundant persistence', () => {
  const ids = ['a', 'b'];
  for (const [source, target, side] of [['x', 'a', 'before'], ['a', 'x', 'before'], ['a', 'a', 'after'], ['a', 'b', 'before'], ['b', null, 'after'], ['a', 'b', 'unknown']]) {
    assert.equal(reorderIds(ids, source, target, side), ids);
  }
});

test('protocol dragging can pin, tuck away, and reorder without changing identity membership', () => {
  const groups = { pinned: [], main: ['a', 'b', 'c'], support: ['d'] };
  const pinned = moveShortcut(groups, 'b', 'pinned');
  assert.deepEqual(pinned, { pinned: ['b'], main: ['a', 'c'], support: ['d'] });
  const tucked = moveShortcut(pinned, 'a', 'support', 'd', 'after');
  assert.deepEqual(tucked, { pinned: ['b'], main: ['c'], support: ['d', 'a'] });
  assert.deepEqual(moveShortcut(tucked, 'a', 'support', 'd'), { pinned: ['b'], main: ['c'], support: ['a', 'd'] });
  assert.deepEqual(Object.values(tucked).flat().sort(), ['a', 'b', 'c', 'd']);
  assert.deepEqual(groups, { pinned: [], main: ['a', 'b', 'c'], support: ['d'] });
});

test('protocol invalid drop locations never lose an item or move across the wrong section', () => {
  const groups = { pinned: ['a'], main: ['b'], support: [] };
  assert.equal(moveShortcut(groups, 'a', 'main', 'a'), groups);
  assert.equal(moveShortcut(groups, 'a', 'unknown'), groups);
  assert.equal(moveShortcut(groups, 'x', 'support'), groups);
  assert.equal(moveShortcut(groups, 'a', 'pinned'), groups);
  assert.equal(moveShortcut(groups, 'a', 'main', 'not-a-protocol'), groups);
});
