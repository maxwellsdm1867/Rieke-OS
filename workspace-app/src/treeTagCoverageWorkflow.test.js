import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
import {incomingTreeSelectionScope} from './incoming-workbench/incomingSelection.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} requests counts only, omits aggregate badges and clears stale selection on first paint`,async()=>{
 const h=await createWorkflowHarness();let release;
 const page={revision:'a'.repeat(64),candidate_scope_revision:'scope-1',kind:'branches',path:[],depth:0,offset:0,limit:60,total:3,total_epochs:9,count:9,cells:3,duration_seconds:0,selection:{count:9},split_order:['date'],levels:[{field:'date',label:'Recording date'}],ancestors:[],epochs:[],has_more:false,
  branches:[3,1,0].map((tagged,index)=>({key:`group-${index}`,path:[`group-${index}`],label:`Group ${index}`,value:`group-${index}`,count:3,cells:1,duration_seconds:0,shared_tag_coverage:{total_epochs:3,tagged_epochs:tagged}}))};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?(assert.equal(JSON.parse(options.body).counts_only,true),page):fallback();
 const props={setSelectedEpochs:()=>{},protocolId:'protocol-A',readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'},splits:'date',revision:0};
 const withClass=value=>h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes(value));
 try{
  const Tree=await h.component(name),firstCommit=[];
  function ObservedTree(current){
   useLayoutEffect(()=>{if(current.revision)firstCommit.push([withClass('tag-coverage-all').length,withClass('incoming-branch-on').length]);},[current.revision]);
   return createElement(Tree,current);
  }
  await h.mount(ObservedTree,props);
  await h.waitFor(()=>withClass('incoming-branch-off').length===3);
  assert.equal(h.root.findAllByProps({className:'tree-tag-coverage'}).length,0);
  assert.equal(h.root.findAllByProps({className:'tp-distribution'}).length,0);
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
  if(name==='HierarchyTree'){await h.render(ObservedTree,{...props,browseOnly:true});await h.settle(20);assert.equal(h.root.findAllByProps({className:'incoming-tree-actions'}).length,0);}
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} keeps committed branch selection while expansion waits`,async()=>{
 const h=await createWorkflowHarness();let release;
 const revision='a'.repeat(64),item={key:'parent',path:['parent'],label:'Parent',value:'parent',count:2};
 const page={revision,candidate_scope_revision:'scope',kind:'branches',path:[],depth:0,offset:0,limit:60,total:1,total_epochs:2,selection:{count:2},split_order:['date'],levels:[{field:'date',label:'Date'}],ancestors:[],epochs:[],branches:[item],has_more:false};
 const child={...page,kind:'epochs',path:['parent'],depth:1,total:2,branches:[],epochs:[{epoch_uuid:'a',cell_uuid:'c'},{epoch_uuid:'b',cell_uuid:'c'}],ancestors:[{...item,parent_offset:0}]};
 const props={protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},splits:'date',revision:0,selectedEpochs:['a','b'],setSelectedEpochs:()=>assert.fail('Navigation must not change selection')};
 props.treeSelectionIntent={scope:incomingTreeSelectionScope(props),revision,markers:[{path:['parent'],on:true}]};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?(JSON.parse(options.body).path.length?new Promise(resolve=>{release=()=>resolve(child);}):page):fallback();
 try{
  const Tree=await h.component(name);await h.mount(Tree,props);
  const switches=()=>h.root.findAll(node=>node.type==='button'&&node.props.role==='switch');
  await h.waitFor(()=>switches().length===1&&switches()[0].props['aria-checked']===true);
  const branch=h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('incoming-branch-on'))[0];
  await h.act(()=>branch.props.onClick());await h.waitFor(()=>!!release);
  assert.equal(switches()[0].props['aria-checked'],true,'loading must not paint the committed switch off');
  assert.equal(switches()[0].props.disabled,true,'loading must keep selection inert');
  assert.ok(h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('incoming-branch-on')).length);
  await h.act(()=>release());await h.settle(25);
  assert.equal(switches()[0].props['aria-checked'],true);
  assert.equal(switches()[0].props.disabled,false);
 }finally{await h.close();}
});
