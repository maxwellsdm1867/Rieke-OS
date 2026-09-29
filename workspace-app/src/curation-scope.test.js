import assert from 'node:assert/strict';
import test from 'node:test';
import {resolveCurationTargets} from './api.js';

test('removing a focused tag never follows hidden bulk targets', () => {
  const selected = ['epoch-a', 'epoch-b'];
  assert.deepEqual(resolveCurationTargets('epoch-c', selected, 'focused'), ['epoch-c']);
  assert.deepEqual(resolveCurationTargets('epoch-c', selected), selected);
  assert.deepEqual(resolveCurationTargets(null, selected, 'focused'), []);
  assert.deepEqual(selected, ['epoch-a', 'epoch-b']);
});

test('explicit bulk actions deduplicate targets and require a known scope', () => {
  assert.deepEqual(resolveCurationTargets('epoch-c', ['epoch-a', 'epoch-a']), ['epoch-a']);
  assert.deepEqual(resolveCurationTargets('epoch-c', []), ['epoch-c']);
  assert.deepEqual(resolveCurationTargets(null, []), []);
  assert.throws(() => resolveCurationTargets('epoch-c', [], 'typo'), /Unknown/);
});
