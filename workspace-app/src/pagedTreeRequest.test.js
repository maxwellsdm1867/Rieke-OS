import test from 'node:test';
import assert from 'node:assert/strict';
import {treePageRequest,treeNavigationSnapshot,treeNavigationStart,treePreviewScope} from './pagedTreeRequest.js';

test('bounded tree pages preserve filters and opaque paths without posting full memberships',()=>{
  const filters={cell_type:'OFF parasol'};
  const body=treePageRequest({protocolId:'protocol',filters,splits:'date,cell,block'},{path:['opaque-date','opaque-cell'],offset:60,currentRevision:'r1'});
  assert.deepEqual(body,{protocol_uuid:'protocol',filters,splits:'date,cell,block',path:['opaque-date','opaque-cell'],offset:60,limit:60,revision:'r1'});
  assert.equal(Object.hasOwn(body,'predicate'),false);
});
test('explorer page and anchor requests always retain summary revision even on explicit reload',()=>{
  const predicate={all:[{field:'parameters/frequencyCutoff',operator:'eq',value:25}]};
  const scope={predicate,splits:'cell',expectedRevision:'summary-revision'};
  const body=treePageRequest(scope,{reset:true,anchor:'epoch',path:['old'],offset:60,currentRevision:'old-tree'});
  assert.equal(body.revision,'summary-revision');assert.equal(body.predicate,predicate);
  assert.equal(body.anchor_uuid,'epoch');assert.deepEqual(body.path,[]);assert.equal(body.offset,0);
  assert.equal(treePageRequest({protocolId:'p'},{reset:true,currentRevision:'stale'}).revision,undefined);
});
test('design navigation restores exact path and page with its revision, without retaining rows',()=>{
  const revision='a'.repeat(64),path=['b'.repeat(64),'c'.repeat(64)];
  const page={revision,path,offset:120,split_order:['date','cell'],epochs:Array(60).fill({epoch_uuid:'omitted'})};
  const saved=treeNavigationSnapshot(page,320);
  assert.deepEqual(saved,{revision,path,offset:120,split_order:['date','cell'],scrollTop:320});
  assert.equal(Object.hasOwn(saved,'epochs'),false);
  const restored=treeNavigationStart(saved,'date,cell');
  assert.deepEqual(restored,{revisionOverride:revision,path,offset:120,scrollTop:320});
  const body=treePageRequest({protocolId:'p',splits:'date,cell'},{...restored,currentRevision:restored.revisionOverride});
  assert.equal(body.revision,revision);assert.deepEqual(body.path,path);assert.equal(body.offset,120);
  assert.equal(treeNavigationStart(saved,'cell,date'),null);
  assert.equal(treeNavigationStart({...saved,revision:null},'date,cell'),null);
});

test('tree return preserves scroll locally without sending it into scientific page queries',()=>{
  const page={revision:'a'.repeat(64),path:['b'.repeat(64)],offset:60,split_order:['date','cell']};
  const restored=treeNavigationStart(treeNavigationSnapshot(page,487.5),'date,cell');
  assert.equal(restored.scrollTop,487.5);
  assert.equal(Object.hasOwn(treePageRequest({protocolId:'p'},restored),'scrollTop'),false);
  assert.equal(treeNavigationStart({...page,scrollTop:-1},'date,cell').scrollTop,0);
  assert.equal(treeNavigationStart({...page,scrollTop:Infinity},'date,cell').scrollTop,0);
});


test('compact preview revisions stay paired with their own layouts during rapid designer changes',()=>{
 const predicate={all:[]},old={tree_revision:'a'.repeat(64),tree:{count:173,split_order:['date','cell']}};
 const pending={predicate,splits:'date,cell,group,block',...treePreviewScope(old)};
 const body=treePageRequest(pending,{reset:true});
 assert.equal(body.splits,'date,cell');
 assert.equal(body.revision,old.tree_revision);
 const flat={tree_revision:'b'.repeat(64),tree:{count:173,split_order:[]}};
 const refreshed=treePageRequest({...pending,...treePreviewScope(flat)},{reset:true});
 assert.equal(refreshed.splits,'');assert.equal(refreshed.revision,flat.tree_revision);
});
