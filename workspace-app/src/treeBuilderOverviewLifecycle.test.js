import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

// User policy: choosing fields no longer computes scoped catalogs or summaries.
for(const frozen of [false,true])test(`field discovery uses registry identities without summary reads (${frozen?'frozen':'live'})`,async()=>{
 const h=await createWorkflowHarness(),fields=[{id:'date',label:'Recording date',category:'Recording',distinct_count:999,examples:['global-example']},{id:'parameters/history1',label:'History1',category:'Parameters'}];
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/field-registry')?{fields,generation:{metadata:'m'}}:fallback();
 const props={protocolId:'protocol-A',projectId:'p',...(frozen?{readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'}}:{}),queryString:'cell=one',revision:0,value:['date'],onChange:()=>{},preview:{count:9},loading:false};
 try{
  const Builder=await h.component('TreeBuilder'),JointEditor=await h.component('JointGroupingEditor');
  await h.mount(Builder,props);await h.settle(20);
  const field=()=>h.root.findByType(JointEditor).props.fields.find(item=>item.id==='date');
  assert.equal(field()?.distinct_count,undefined);assert.equal(field()?.examples,undefined);
  await h.act(()=>h.root.findByType(JointEditor).props.onOpenChange(true));
  await h.render(Builder,{...props,queryString:'cell=two'});
  await h.act(()=>h.root.findByType(JointEditor).props.onOpenChange(false));
  assert.equal(h.root.findByType(JointEditor).props.fields.some(item=>item.id==='parameters/history1'),true);
  assert.equal(h.fixture.requests.filter(item=>/tree-fields|summary/.test(item.path)).length,0);
  assert.equal(h.root.findAllByProps({className:'metadata-summary-status'}).length,0);
 }finally{await h.close();}
});
