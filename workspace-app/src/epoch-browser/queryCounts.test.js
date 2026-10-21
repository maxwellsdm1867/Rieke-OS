import test from 'node:test';
import assert from 'node:assert/strict';
import {pendingCountsRequest,queryCountsResult,withQueryCounts} from './queryCounts.js';

const pendingRun={matched_count:null,tree:{count:null,split_order:['date']},catalog:{total:null,fields:[]},last_run:{epoch_count:null,cell_count:null,ran_at:'t'},tree_revision:'R',counts:{status:'pending',request_id:'job-1'}};
test('a pending run names its counts job; single-field runs name none',()=>{
  assert.equal(pendingCountsRequest(pendingRun),'job-1');
  assert.equal(pendingCountsRequest({matched_count:4,tree_revision:'R'}),null);
  assert.equal(pendingCountsRequest({counts:{status:'ready',request_id:'job-1'}}),null);
});
test('ready counts fill only the null totals and never invent a count',()=>{
  assert.equal(withQueryCounts(pendingRun,{status:'pending'}),pendingRun);
  const counted=withQueryCounts(pendingRun,{status:'ready',result:{matched_count:12,cell_count:3}});
  assert.equal(counted.matched_count,12);assert.equal(counted.tree.count,12);assert.equal(counted.catalog.total,12);
  assert.deepEqual([counted.last_run.epoch_count,counted.last_run.cell_count],[12,3]);assert.equal(counted.counts.status,'ready');
  assert.equal(pendingRun.matched_count,null,'the response is not mutated');
  const single={matched_count:4,tree_revision:'R'};assert.equal(withQueryCounts(single,{status:'ready',result:{matched_count:12,cell_count:3}}),single);
});
test('counts job receipts must match the job and carry exact counts',()=>{
  assert.deepEqual(queryCountsResult({request_id:'job-1',status:'ready',result:{matched_count:0,cell_count:0}},'job-1'),{matched_count:0,cell_count:0});
  assert.throws(()=>queryCountsResult({request_id:'other',result:{matched_count:1,cell_count:1}},'job-1'));
  assert.throws(()=>queryCountsResult({request_id:'job-1',result:{matched_count:null,cell_count:1}},'job-1'));
});
