import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readSelectedEpochCellCount} from './selectedEpochCellCount.js';

const context={root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope',expected_binding_version:2,selection_summary:true};
const annotations=rows=>({annotations:Object.fromEntries(rows.map(([epoch_uuid,cell_uuid])=>[epoch_uuid,{epoch_uuid,cell_uuid}]))});
const summary=(ids,cells=['a','b'])=>({candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,epoch_uuids:ids,counts:{epochs:ids.length,cells:cells.length},cells:cells.map(cell_uuid=>({cell_uuid,cell_type:null}))});

test('explicit selected UUIDs count distinct cells across distant pages without a visible-page estimate',async()=>{
 const ids=['epoch-800','epoch-1','epoch-60'],calls=[];
 const count=await readSelectedEpochCellCount({selected:ids,request:async(path,options)=>{calls.push({path,...options});return annotations([['epoch-1','cell-A'],['epoch-60','cell-B'],['epoch-800','cell-A']]);}});
 assert.equal(count,2);assert.equal(calls.length,1);assert.equal(calls[0].path,'/annotations/read');
 assert.deepEqual(calls[0].body,{target_kind:'epoch',target_uuids:['epoch-1','epoch-60','epoch-800']});
 assert.equal(calls[0].background,true);
});

test('missing, mismatched or extra mapping never becomes a partial count or a fake zero',async()=>{
 for(const value of [{},annotations([['a','cell']]),annotations([['a','cell'],['b','']]),annotations([['a','cell'],['b','cell'],['c','other']]),{annotations:{a:{epoch_uuid:'other',cell_uuid:'cell'},b:{epoch_uuid:'b',cell_uuid:'cell'}}}]){
  await assert.rejects(readSelectedEpochCellCount({selected:['a','b'],request:async()=>value}),/could not be verified/);
 }
 let reads=0;assert.equal(await readSelectedEpochCellCount({selected:[],request:()=>reads++}),0);assert.equal(reads,0);
 await assert.rejects(readSelectedEpochCellCount({selected:['a','a'],request:()=>reads++}));assert.equal(reads,0);
});

test('frozen selections use their exact scoped summary and never fall back to global annotations',async()=>{
 const calls=[];
 assert.equal(await readSelectedEpochCellCount({selected:['b','a'],readContext:context,request:async(path,options)=>{calls.push({path,...options});return summary(['a','b']);}}),2);
 assert.equal(calls[0].path,context.root+'/selection-summary');assert.deepEqual(calls[0].body,{candidate_scope_revision:'scope',epoch_uuids:['a','b']});
 await assert.rejects(readSelectedEpochCellCount({selected:['a'],readContext:{...context,selection_summary:false},request:()=>assert.fail('no fallback')}));
 await assert.rejects(readSelectedEpochCellCount({selected:['a','b'],readContext:context,request:async()=>({...summary(['a','b']),candidate_scope_revision:'stale'})}));
});

test('large frozen selections use existing bounded manifests before counting the full selection',async()=>{
 const ids=Array.from({length:1001},(_,i)=>`e${String(i).padStart(4,'0')}`),uploaded=[],calls=[];
 const request=async(path,{body})=>{
  calls.push({path,body});
  if(path.endsWith('/selection-manifest')){
   uploaded.push(...body.epoch_uuids);const count=uploaded.length;
   return {selection_token:body.upload_uuid,count,total:ids.length,complete:count===ids.length,candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,selection_sha256:createHash('sha256').update(JSON.stringify(uploaded)).digest('hex')};
  }
  assert.ok(body.selection_token);assert.equal(body.epoch_uuids,undefined);return summary(ids);
 };
 assert.equal(await readSelectedEpochCellCount({selected:ids,readContext:{...context,selection_manifests:true},request}),2);
 assert.deepEqual(calls.slice(0,2).map(call=>call.body.epoch_uuids.length),[1000,1]);assert.equal(calls.length,3);
});
