import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useState} from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const revision='a'.repeat(64),items={parent:{path:['p'],count:3},child:{path:['p','x'],count:2},other:{path:['p','y'],count:1}};
const idsFor=body=>body.path.length===1?['a','b','c']:body.path[1]==='x'?['a','b']:['c'];
async function fixture(){
 const h=await createWorkflowHarness(),pending=[];let observed;
 const {useIncomingTreeSelection}=await h.module('incoming-workbench/ui/IncomingTreeSelection.jsx');
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/selection')?new Promise(resolve=>{const body=JSON.parse(options.body);pending.push({body,resolve,reply:(extra={})=>resolve({revision,candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,path:body.path,count:body.expected_count,epoch_uuids:idsFor(body),...extra})});}):fallback();
 function Owner({disabled=false,scope='scope'}){
  const [selected,setSelected]=useState([]),[intent,setIntent]=useState(null);
  const props={projectId:'project',protocolId:'p',readContext:{root:'/candidate',candidate_scope_revision:scope,expected_binding_version:2,tree_selection:true},splits:'date,cell',selectedEpochs:selected,setSelectedEpochs:setSelected,treeSelectionIntent:intent,onTreeSelectionIntentChange:setIntent,actionsDisabled:disabled};
  const page={revision,candidate_scope_revision:scope},state=useIncomingTreeSelection(props,page);observed={selected,intent,setSelected,setIntent,state};
  return createElement('div',null,...Object.entries(items).map(([id,item])=>createElement('button',{id,key:id,disabled,'aria-busy':!!state.pending(item,page),onClick:()=>state.select(item,page),'data-on':state.on(item,page)},id)),state.feedback);
 }
 await h.mount(Owner);return {h,Owner,pending,get observed(){return observed;},click:id=>h.root.findByProps({id}).props.onClick()};
}
test('rapid same-branch and parent/child clicks are accepted and committed in order',async()=>{
 const f=await fixture(),{h,pending}=f;
 try{
  await h.act(()=>{f.click('parent');f.click('parent');f.click('parent');f.click('child');});
  assert.equal(pending.length,1);assert.equal(h.root.findByProps({id:'other'}).props.disabled,false);
  await h.act(()=>pending[0].reply());await h.waitFor(()=>pending.length===2);assert.deepEqual(f.observed.selected,['a','b','c']);
  await h.act(()=>pending[1].reply());await h.waitFor(()=>pending.length===3);assert.deepEqual(f.observed.selected,[]);
  await h.act(()=>pending[2].reply());await h.waitFor(()=>pending.length===4);
  await h.act(()=>pending[3].reply());assert.deepEqual(f.observed.selected,['c']);assert.equal(f.observed.state.working,false);
  assert.equal(h.root.findByProps({id:'parent'}).props['data-on'],true);assert.equal(h.root.findByProps({id:'child'}).props['data-on'],false);
 }finally{await h.close();}
});
test('a failed middle command retires later projected commands without undoing confirmed selection',async()=>{
 const f=await fixture(),{h,pending}=f;
 try{
  await h.act(()=>{f.click('parent');f.click('child');f.click('other');});
  await h.act(()=>pending[0].reply());await h.waitFor(()=>pending.length===2);
  await h.act(()=>pending[1].reply({epoch_uuids:['a','a']}));await h.settle(20);
  assert.equal(pending.length,2);assert.deepEqual(f.observed.selected,['a','b','c']);assert.equal(f.observed.state.working,false);
  assert.equal(h.root.findByProps({id:'child'}).props['data-on'],true);
  await h.act(()=>{f.click('child');});await h.waitFor(()=>pending.length===3);await h.act(()=>pending[2].reply());assert.deepEqual(f.observed.selected,['c']);
 }finally{await h.close();}
});
test('external selection, scope retirement and unmount prevent queued or late publication',async()=>{
 const f=await fixture(),{h,pending}=f;let closed=false;
 try{
  const oldClick=h.root.findByProps({id:'parent'}).props.onClick;
  await h.act(()=>{f.click('parent');f.click('child');});await h.act(()=>f.observed.setSelected(['c']));await h.act(()=>pending[0].reply());assert.deepEqual(f.observed.selected,['c']);assert.equal(pending.length,1);
  await h.act(()=>{f.click('parent');});await h.render(f.Owner,{scope:'other'});await h.act(()=>pending[1].reply());assert.deepEqual(f.observed.selected,['c']);assert.equal(f.observed.intent,null);
  await h.render(f.Owner,{});await h.act(()=>oldClick());assert.equal(pending.length,2,'Retired A-B-A handler cannot enqueue into a new lifetime');await h.act(()=>{f.click('parent');});await h.close();closed=true;pending[2].reply();
 }finally{if(!closed)await h.close();}
});
