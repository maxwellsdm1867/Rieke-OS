import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
import {incomingTreeSelectionScope} from './incoming-workbench/incomingSelection.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} keeps saved tags separate from binary selection and clears stale first paint`,async()=>{
 const h=await createWorkflowHarness();let release;
 const page={revision:'a'.repeat(64),candidate_scope_revision:'scope-1',kind:'branches',path:[],depth:0,offset:0,limit:60,total:3,total_epochs:9,count:9,cells:3,duration_seconds:0,selection:{count:9},split_order:['date'],levels:[{field:'date',label:'Recording date'}],ancestors:[],epochs:[],has_more:false,
  branches:[3,1,0].map((tagged,index)=>({key:`group-${index}`,path:[`group-${index}`],label:`Group ${index}`,value:`group-${index}`,count:3,cells:1,duration_seconds:0,shared_tag_coverage:{total_epochs:3,tagged_epochs:tagged}}))};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?page:fallback();
 const props={setSelectedEpochs:()=>{},protocolId:'protocol-A',readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'},splits:'date',revision:0};
 const withClass=value=>h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes(value));
 try{
  const Tree=await h.component(name),firstCommit=[];
  function ObservedTree(current){
   useLayoutEffect(()=>{if(current.revision)firstCommit.push([withClass('tag-coverage-all').length,withClass('incoming-branch-on').length]);},[current.revision]);
   return createElement(Tree,current);
  }
  await h.mount(ObservedTree,props);
  await h.waitFor(()=>withClass('tag-coverage-all').length===1);
  assert.equal(withClass('tag-coverage-partial').length,1);assert.equal(withClass('tag-coverage-none').length,1);
  assert.ok(h.root.findAllByProps({className:'tree-tag-coverage'}).some(node=>node.children.join('')==='All 3 epochs tagged'));
  assert.ok(h.root.findAllByProps({className:'tree-tag-coverage'}).some(node=>node.children.join('')==='1 of 3 tagged'));
  assert.equal(withClass('incoming-branch-on').length,0,'saved tags cannot turn a selection branch green');
  assert.equal(withClass('incoming-branch-off').length,3);
  await h.render(ObservedTree,{...props,treeSelectionIntent:{scope:incomingTreeSelectionScope(props),revision:page.revision,markers:[{path:['group-1'],on:true}]}});
  assert.equal(withClass('incoming-branch-on').length,1,'only explicit branch intent is green');
  assert.equal(h.root.findAll(node=>node.props.role==='switch'&&node.props['aria-checked']===true).length,1);
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?new Promise(resolve=>{release=resolve;}):fallback();
  await h.render(ObservedTree,{...props,revision:1});
  assert.deepEqual(firstCommit,[[0,0]],'same-candidate changed scope must drop green before passive loading effects');
  await h.waitFor(()=>!!release);assert.equal(withClass('tag-coverage-all').length,0,'retained response cannot paint current green');
  await h.act(()=>release({...page,candidate_scope_revision:'scope-1',branches:page.branches.map(row=>({...row,shared_tag_coverage:null}))}));
  await h.settle(20);assert.equal(withClass('tag-coverage-all').length,0,'unavailable coverage stays neutral');
  assert.equal(h.root.findAllByProps({className:'tree-tag-coverage'}).length,0);
 }finally{await h.close();}
});
