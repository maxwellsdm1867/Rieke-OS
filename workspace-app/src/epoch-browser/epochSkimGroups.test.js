import test from 'node:test';
import assert from 'node:assert/strict';
import {epochSkimGroups} from './epochSkimGroups.js';
test('skim groups preserve chronological order and distinguish reused cell labels by date and UUID',()=>{
  const rows=[{date:'2026-09-23',cell_uuid:'a',cell_label:'Cell1'},{date:'2026-09-23',cell_uuid:'a',cell_label:'Cell1'},{date:'2026-09-24',cell_uuid:'b',cell_label:'Cell1'},{date:'2026-09-24',cell_uuid:'c',cell_label:'Cell1'},{date:'2026-09-24',cell_uuid:'b',cell_label:'Cell1'}];
  const groups=epochSkimGroups(rows,60);
  assert.deepEqual(groups.map(g=>g.epochs.length),[2,1,1,1]);
  assert.deepEqual(groups.flatMap(g=>g.epochs.map(item=>item.epoch)),rows);
  assert.deepEqual(groups.flatMap(g=>g.epochs.map(item=>item.position)),[61,62,63,64,65]);
  assert.equal(new Set(groups.map(g=>g.key)).size,4);
});
