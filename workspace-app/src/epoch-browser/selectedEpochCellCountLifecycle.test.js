import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';
import {createInspectorHarness} from '../test-support/inspectorHarness.js';

const receipt=(ids,cells=ids.map(()=> 'one-cell'))=>({annotations:Object.fromEntries(ids.map((epoch_uuid,index)=>[epoch_uuid,{epoch_uuid,cell_uuid:cells[index]}]))});

test('cell count masks stale selection/scope receipts, including A-B-A, instead of estimating from visible rows',async()=>{
 const h=await createWorkflowHarness(),pending=[];let current,observations=[];
 const request=(path,options)=>new Promise(resolve=>pending.push({path,...options,resolve}));
 try{
  const {useSelectedEpochCellCount}=await h.module('epoch-browser/useSelectedEpochCellCount.js');
  function Probe(props){current=useSelectedEpochCellCount(props);useLayoutEffect(()=>{observations.push(current.count);});return null;}
  const props={projectId:'project',scope:'query-A:binding-2',selected:['epoch-700','epoch-0','epoch-90'],request,settleMs:0};
  await h.mount(Probe,props);await h.waitFor(()=>pending.length===1);assert.equal(current.count,null);
  await h.act(()=>pending[0].resolve(receipt(pending[0].body.target_uuids,['cell-A','cell-B','cell-A'])));
  assert.equal(current.count,2);
  await h.render(Probe,{...props,scope:'query-B:binding-3'});assert.equal(current.count,null);await h.waitFor(()=>pending.length===2);
  observations=[];await h.render(Probe,props);assert.equal(observations[0],null);await h.waitFor(()=>pending.length===3);
  assert.equal(pending[1].signal.aborted,true);
  await h.act(()=>pending[1].resolve(receipt(pending[1].body.target_uuids)));assert.equal(current.count,null);
  await h.act(()=>pending[2].resolve(receipt(pending[2].body.target_uuids)));assert.equal(current.count,1);
  await h.render(Probe,{...props,selected:[...props.selected].reverse()});assert.equal(current.count,1);assert.equal(pending.length,3,'same exact UUID set reuses its display count');
  await h.render(Probe,{...props,projectId:'other'});assert.equal(current.count,null);await h.waitFor(()=>pending.length===4);
  await h.render(Probe,{...props,selected:[]});assert.equal(current.count,0);assert.equal(pending[3].signal.aborted,true);
 }finally{await h.close();}
});

test('cell count errors and paused reads remain unavailable, never zero for nonempty selections',async()=>{
 const h=await createWorkflowHarness();let current,calls=0;
 const request=async()=>{calls++;throw Error('Identity read unavailable');};
 try{
  const {useSelectedEpochCellCount}=await h.module('epoch-browser/useSelectedEpochCellCount.js');
  function Probe(props){current=useSelectedEpochCellCount(props);return null;}
  const props={projectId:'project',scope:'query-A',selected:['epoch-1'],request,settleMs:0};
  await h.mount(Probe,props);await h.waitFor(()=>current.error);
  assert.equal(current.count,null);assert.equal(current.loading,false);assert.match(current.error,/unavailable/);
  await h.render(Probe,{...props,paused:true});assert.equal(current.count,null);assert.equal(current.error,null);assert.equal(calls,1);
  await h.render(Probe,props);assert.equal(current.count,null);await h.waitFor(()=>calls===2);
 }finally{await h.close();}
});

test('hidden retained routes and panels abort cell-count reads even when another busy operation keeps effects connected',async()=>{
 for(const nested of [false,true]){
  const h=await createWorkflowHarness(),pending=[];let current;
  const request=(path,options)=>new Promise(resolve=>pending.push({...options,resolve}));
  try{
   const {useSelectedEpochCellCount}=await h.module('epoch-browser/useSelectedEpochCellCount.js');
   const {RetainedWorkspaceViews,RetainedWorkspacePanel,useRetainedViewProtection}=await h.module('retainedWorkspaceViews.js');
   function Probe(){useRetainedViewProtection({busy:true});current=useSelectedEpochCellCount({projectId:'project',scope:'query',selected:['a','b'],request,settleMs:0});return null;}
   const presentation={remember(){}};
   function Views({visible}){return createElement(RetainedWorkspaceViews,{route:{key:visible||nested?'a':'b',page:visible||nested?'protocol':'overview'},projectId:'project',projectPath:'/fixture',presentation,render:route=>route.key==='a'?createElement(RetainedWorkspacePanel,{name:'inspect',visible:visible||!nested},createElement(Probe)):null});}
   await h.mount(Views,{visible:true});await h.waitFor(()=>pending.length===1);
   await h.render(Views,{visible:false});assert.equal(current.count,null);assert.equal(pending[0].signal.aborted,true);
   await h.render(Views,{visible:true});await h.waitFor(()=>pending.length===2);
   await h.act(()=>pending[0].resolve(receipt(['a','b'],['old-A','old-B'])));assert.equal(current.count,null);
   await h.act(()=>pending[1].resolve(receipt(['a','b'])));assert.equal(current.count,1);
  }finally{await h.close();}
 }
});

test('Inspector forwards distinct full-selection cells to the shared bar in list and split-tree paths',async()=>{
 for(const tree of [false,true]){
  const h=await createInspectorHarness(),calls=[];
  h.fixture.selectedCellRead=async(path,options)=>{calls.push({path,...options});return receipt(options.body.target_uuids,['cell-A','cell-B','cell-A']);};
  try{
   await h.render({projectId:'project',protocol:{definition:{protocol_uuid:'p'},query_revision:'q',expected_binding_version:2,cells:[]},filters:{},revision:0,initialEpochUuid:'epoch-A'});
   const selected=['off-page-900','off-page-60','epoch-A'];
   await h.act(()=>tree?h.viewer.treePane.treeProps.setSelectedEpochs(selected):h.viewer.treePane.listProps.setTargets(selected));
   assert.equal(h.viewer.selectionActions.cellCount,null);
   await h.act(()=>new Promise(resolve=>setTimeout(resolve,300)));
   assert.equal(h.viewer.selectionActions.cellCount,2);assert.equal(calls.length,1);
   assert.deepEqual(calls[0].body.target_uuids,[...selected].sort());
  }finally{await h.close();}
 }
});

test('Search forwards selected cells independently of its current empty page in list and split-tree modes',async()=>{
 for(const treeMode of [false,true]){
  const h=await createWorkflowHarness(),selected=['epoch-0','epoch-500','epoch-900'];
  const previousObserver=globalThis.ResizeObserver;globalThis.ResizeObserver=class{observe(){}disconnect(){}};
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/explore/epochs')?
    {revision:'search-r',offset:0,total:0,epochs:[],cells:[]}:
    url.pathname.endsWith('/annotations/read')?receipt(JSON.parse(options.body).target_uuids,['cell-A','cell-B','cell-B']):fallback();
  try{
   const Matching=(await h.module('epoch-browser/ui/MatchingEpochs.jsx')).default;
   const Viewer=(await h.module('epoch-browser/ui/EpochViewer.jsx')).default;
   await h.mount(Matching,{projectId:'project',predicate:{all:[]},splits:'date,cell',preview:{tree_revision:'search-r',catalog:{fields:[]}},session:{revision:'search-r',targets:selected,treeMode}});
   await h.waitFor(()=>h.root.findByType(Viewer).props.selectionActions.cellCount===2);
   assert.deepEqual(h.root.findByType(Viewer).props.targets,selected);
   const reads=h.fixture.requests.filter(request=>request.path==='/annotations/read');assert.equal(reads.length,1);
   assert.deepEqual(reads[0].body.target_uuids,selected);
  }finally{await h.close();if(previousObserver===undefined)delete globalThis.ResizeObserver;else globalThis.ResizeObserver=previousObserver;}
 }
});
