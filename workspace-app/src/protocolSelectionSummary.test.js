import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

function text(node){
 return node.children.map(child=>typeof child==='string'?child:text(child)).join(' ');
}
test('protocol rule display preserves empty AND, empty OR and nested negation truth',async()=>{
 const h=await createWorkflowHarness();
 try{
  const Summary=await h.component('ProtocolSelectionSummary');
  for(const [predicate,expected,forbidden] of [
   [{all:[]},'All project recordings','No project recordings'],
   [{any:[]},'No project recordings','All project recordings'],
   [{not:{any:[]}},'NOT No project recordings','All project recordings'],
   [{not:{all:[]}},'NOT All project recordings','No project recordings'],
   [{all:[{any:[]}]},'No project recordings','All project recordings'],
  ]){
   await h.mount(Summary,{data:{effective_query:predicate,counts:{epochs:0,cells:0,included:0}},filters:{}});
   const rendered=text(h.root.findByProps({className:'protocol-rule-summary'}));
   assert.equal(rendered,expected);assert.ok(!rendered.includes(forbidden));
  }
 }finally{await h.close();}
});
