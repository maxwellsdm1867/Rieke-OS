import test from 'node:test';
import assert from 'node:assert/strict';
import {loadIncomingSelection,incomingSelectionCount} from './incomingSelection.js';
const source={kind:'protocol',protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},query:'tag=chosen',queryRevision:'revision'};
const cells=[{cell_uuid:'a',epochs:65},{cell_uuid:'b',epochs:3}];
const page=(cell,offset)=>({query_revision:'revision',offset,total:cell.epochs,epochs:Array.from({length:Math.min(60,cell.epochs-offset)},(_,index)=>({cell_uuid:cell.cell_uuid,epoch_uuid:cell.cell_uuid+(offset+index)}))});
test('whole-view and cell selection capture every frozen filtered page before returning UUIDs',async()=>{
 const calls=[];const request=async path=>{const url=new URL(path,'http://local'),id=url.searchParams.get('cell_uuid'),offset=Number(url.searchParams.get('offset'));calls.push(url);return page(cells.find(cell=>cell.cell_uuid===id),offset);};
 const all=await loadIncomingSelection({source,cells,request});assert.equal(all.length,68);assert.equal(all[60],'a60');assert.equal(all[67],'b2');assert.equal(calls.length,3);
 for(const url of calls){assert.equal(url.pathname,source.readContext.root+'/epochs');assert.equal(url.searchParams.get('tag'),'chosen');assert.equal(url.searchParams.get('candidate_scope_revision'),'scope');}
 assert.deepEqual(await loadIncomingSelection({source,cells,cellUuid:'b',request}),['b0','b1','b2']);
});
test('stale, partial, wrong-cell and duplicate pages cannot become a saved selection',async()=>{
 for(const corrupt of [value=>({...value,query_revision:'new'}),value=>({...value,total:999}),value=>({...value,epochs:value.epochs.slice(1)}),value=>({...value,epochs:value.epochs.map(row=>({...row,cell_uuid:'other'}))}),value=>({...value,epochs:value.epochs.map(row=>({...row,epoch_uuid:'duplicate'}))})]){
  await assert.rejects(loadIncomingSelection({source,cells:[cells[1]],request:async()=>corrupt(page(cells[1],0))}));
 }
});
test('selection cancellation and limit stop before publishing a partial range',async()=>{
 let calls=0,current=true;
 await assert.rejects(loadIncomingSelection({source,cells,request:async()=>{calls++;current=false;return page(cells[0],0);},isCurrent:()=>current}),{name:'AbortError'});assert.equal(calls,1);
 calls=0;await assert.rejects(loadIncomingSelection({source,cells:[{cell_uuid:'large',epochs:1001}],request:async()=>{calls++;}}),/1,000/);assert.equal(calls,0);
 await assert.rejects(loadIncomingSelection({source,cells,cellUuid:'missing',request:async()=>{calls++;}}),/no longer/);assert.equal(calls,0);
});

test('Import count deduplicates explicit UUIDs and never substitutes global or unavailable totals',()=>{
 assert.equal(incomingSelectionCount({targets:['a','a','b'],cells,cell:{cell_uuid:'a'}}),2);
 assert.equal(incomingSelectionCount({targets:['']}),null);
 for(const count of [null,undefined,-1,1.2,NaN])assert.equal(incomingSelectionCount({cells:[{cell_uuid:'a',epochs:count}],cell:{cell_uuid:'a'}}),null);
 assert.equal(incomingSelectionCount({cells:[cells[0],cells[0]],cell:{cell_uuid:'a'}}),null);
 assert.equal(incomingSelectionCount({cells,cell:{cell_uuid:'b',epochs:1000}}),3);
});

const capable={...source,queryRevision:'scope',readContext:{...source.readContext,list_selection:true,expected_binding_version:2}};
const selection=()=>({query_revision:'scope',candidate_scope_revision:'scope',expected_binding_version:2,count:68,
 cells:cells.map(cell=>({...cell,epoch_uuids:Array.from({length:cell.epochs},(_,i)=>cell.cell_uuid+i)})),
 epoch_uuids:cells.flatMap(cell=>Array.from({length:cell.epochs},(_,i)=>cell.cell_uuid+i))});
test('capable incoming list selection verifies one exact ordered bounded response',async()=>{
 const calls=[];const ids=await loadIncomingSelection({source:capable,cells,request:async(path,options)=>{calls.push({path,...options});return selection();}});
 assert.deepEqual(ids,selection().epoch_uuids);assert.equal(calls.length,1);
 assert.equal(calls[0].path,source.readContext.root+'/list-selection');
 assert.deepEqual(calls[0].body,{candidate_scope_revision:'scope',cells,filters:{tag:'chosen'}});
});
test('capable selection refuses partial, reordered, duplicated, stale and cancelled replies',async()=>{
 for(const corrupt of [r=>({...r,candidate_scope_revision:'old'}),r=>({...r,expected_binding_version:3}),r=>({...r,count:69}),
   r=>({...r,cells:[...r.cells].reverse()}),r=>({...r,epoch_uuids:[...r.epoch_uuids].reverse()}),
   r=>({...r,cells:r.cells.map(c=>({...c,epoch_uuids:c.epoch_uuids.map(()=> 'duplicate')}))})]){
   await assert.rejects(loadIncomingSelection({source:capable,cells,request:async()=>corrupt(selection())}));
 }
 let current=true;
 await assert.rejects(loadIncomingSelection({source:capable,cells,isCurrent:()=>current,request:async()=>{current=false;return selection();}}),{name:'AbortError'});
 await assert.rejects(loadIncomingSelection({source:capable,cells:[{cell_uuid:'a',epochs:1001}],request:async()=>assert.fail('must refuse before request')}),/1,000/);
});
