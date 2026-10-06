import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
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
