import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
import {createHash} from 'node:crypto';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {selectedSummaryIds,validateSelectionSummary} from './incoming-workbench/incomingSelectionSummary.js';
const context={root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope',expected_binding_version:2,selection_summary:true};
const receipt=(ids,cells=[{cell_uuid:'c',cell_type:'ON'}])=>({candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,epoch_uuids:ids,counts:{epochs:ids.length,cells:cells.length},cells});
test('selection summary refuses incomplete, duplicate and wrong-scope receipts',()=>{
 assert.deepEqual(selectedSummaryIds(['b','a']),['a','b']);
 for(const ids of [null,['a','a'],[true],[''],Array(1001).fill('a')])assert.equal(selectedSummaryIds(ids),null);
 const value=receipt(['a','b']);assert.equal(validateSelectionSummary(value,['a','b'],context),value);
 for(const bad of [{...value,query_revision:'stale'},{...value,expected_binding_version:3},{...value,epoch_uuids:['b','a']},{...value,cells:[]},{...value,counts:{epochs:2,cells:2},cells:[value.cells[0],value.cells[0]]}])assert.throws(()=>validateSelectionSummary(bad,['a','b'],context));
});
test('mounted summary counts actual selection and masks old data on scope, pause and A-B-A transitions',async()=>{
 const h=await createWorkflowHarness(),pending=[];let observations=[];
 const props={projectId:'project',protocolId:'p',readContext:context,selected:['b','a']};
 const metrics=()=>h.root.findAll(node=>node.type==='strong').map(node=>node.children.join(''));
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/selection-summary')?new Promise(resolve=>pending.push({ids:JSON.parse(options.body).epoch_uuids,resolve})):fallback();
 try{
  const Summary=(await h.module('incoming-workbench/ui/IncomingSelectionSummary.jsx')).default;
  function Observed(p){useLayoutEffect(()=>{observations.push(metrics());});return createElement(Summary,p);}
  const status=()=>h.root.findByProps({className:'selection-summary-live'}).children.filter(value=>typeof value==='string').join('');
  await h.mount(Observed,props);await h.waitFor(()=>pending.length===1);assert.equal(status(),'Updating');
  assert.deepEqual(pending[0].ids,['a','b']);assert.deepEqual(metrics(),['Current selection','2','—','—']);
  await h.act(()=>pending[0].resolve(receipt(['a','b'],[{cell_uuid:'c',cell_type:'ON'},{cell_uuid:'d',cell_type:null}])));
  await h.waitFor(()=>metrics()[2]==='2');assert.deepEqual(metrics(),['Current selection','2','2','1']);assert.equal(status(),'Live');
  await h.render(Observed,{...props,paused:true});assert.equal(metrics()[2],'—');assert.equal(status(),'Paused');
  observations=[];await h.render(Observed,props);assert.equal(observations[0][2],'—','first resumed paint cannot expose the previous receipt');
  await h.waitFor(()=>pending.length===2);
  await h.render(Observed,{...props,selected:['x']});await h.waitFor(()=>pending.length===3);
  await h.render(Observed,props);await h.waitFor(()=>pending.length===4);
  await h.act(()=>pending[1].resolve(receipt(['a','b'])));assert.equal(metrics()[2],'—','late same-key receipt from an earlier lifetime is retired');
  await h.act(()=>pending[3].resolve(receipt(['a','b'])));await h.waitFor(()=>metrics()[2]==='1');
  await h.render(Observed,{...props,selected:[]});assert.deepEqual(metrics(),['Current selection','0','0','0']);assert.equal(pending.length,4);
 }finally{await h.close();}
});
test('ten rapid toggles of a 1,500-epoch selection send at most two summary reads and reuse one manifest per selection',async()=>{
 const h=await createWorkflowHarness(),summaries=[],manifests=[],uploads={};
 const manifestContext={...context,selection_manifests:true,draft:{draft_version:0}};
 const base=Array.from({length:1500},(_,index)=>`e${String(index).padStart(5,'0')}`);
 h.fixture.respond=(url,options,fallback)=>{
  const body=options.body?JSON.parse(options.body):null;
  if(url.pathname.endsWith('/selection-manifest')){
   manifests.push(body);const upload=(uploads[body.upload_uuid]||=[]);upload.push(...body.epoch_uuids);const count=body.offset+body.epoch_uuids.length;
   return {selection_token:body.upload_uuid,count,total:body.total,complete:count===body.total,candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,
    selection_sha256:createHash('sha256').update(JSON.stringify(upload)).digest('hex')};
  }
  if(url.pathname.endsWith('/selection-summary')){summaries.push(body);return receipt(uploads[body.selection_token]);}
  return fallback();
 };
 try{
  const Summary=(await h.module('incoming-workbench/ui/IncomingSelectionSummary.jsx')).default;
  // A long settle window keeps this ledger independent of machine load.
  const props={projectId:'project',protocolId:'p',readContext:manifestContext,selected:base,settleMs:1500};
  await h.mount(Summary,props);await h.waitFor(()=>summaries.length===1);
  const uploadsPerSelection=manifests.length;assert.equal(uploadsPerSelection,2,'1,500 ids upload in two 1,000-id batches');
  let selected=base;
  for(let index=0;index<10;index++){selected=index%2?selected.slice(0,-1):[...selected,`extra-${index}`];await h.render(Summary,{...props,selected});await h.settle(100);} // clicks ~100 ms apart
  await h.waitFor(()=>summaries.length>=2,{timeout:6000});await h.settle(100);
  assert.ok(summaries.length<=2,`10 toggles sent ${summaries.length} summary reads`);
  assert.ok(manifests.length<=uploadsPerSelection*2,`${manifests.length} manifest uploads; one for the settled selection`);
  const before=manifests.length;
  await h.render(Summary,{...props,selected,paused:true});await h.render(Summary,{...props,selected});
  await h.waitFor(()=>summaries.length===3,{timeout:6000});
  assert.equal(manifests.length,before,'resuming the same selection reuses its manifest token');
  assert.equal(summaries[2].selection_token,summaries[1].selection_token);
 }finally{await h.close();}
});
