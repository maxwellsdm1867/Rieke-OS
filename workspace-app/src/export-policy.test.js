import assert from 'node:assert/strict';
import test from 'node:test';
import {eligibleExportCount} from './api.js';

test('review is optional and reviewed-only uses the included/reviewed intersection', () => {
  const counts = {epochs:13, included:12, excluded:1, approved:3, exportable:12, approved_exportable:2};
  assert.equal(eligibleExportCount(counts, 'include_unreviewed'), 12);
  assert.equal(eligibleExportCount(counts, 'approved_only'), 2);
  assert.equal(eligibleExportCount({...counts, approved_exportable:0}, 'approved_only'), 0);
});
test('missing counts and unknown policies never enable export', () => {
  assert.equal(eligibleExportCount({}, 'include_unreviewed'), undefined);
  assert.equal(eligibleExportCount({included:12}, 'typo'), undefined);
});
