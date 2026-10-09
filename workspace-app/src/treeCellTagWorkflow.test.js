import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const props={selectedCells:['cell-0','cell-2'],targetScope:'selected-cells',revision:'fresh-tree',reconcileReceipt:true};
const input=h=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.includes('selected cells'));

const countNotice=h=>h.root.findAllByProps({className:'annotation-scope-note'}).flatMap(node=>node.children.filter(child=>typeof child==='string')).join('');
const tagInput=(h,scope)=>h.root.findByProps({'aria-label':scope==='cell'?'Tag cell':'Tag this epoch'});
const annotationValue=(epoch='epoch-0',cell='cell-0',count)=>({epoch_uuid:epoch,cell_uuid:cell,
 cell_tags:[],epoch_tags:[],effective_tags:[],revisions:{cell:{},epoch:{}},...(count===undefined?{}:{cell_epoch_count:count})});

test('bulk cell composer writes only explicit cells with verified per-author revisions, without promoting epochs',async()=>{
 const h=await createWorkflowHarness();
 try{
  const Tags=await h.component('AnnotationTags');let receipt;
  await h.mount(Tags,{...props,onChange:(_,value)=>{receipt=value;}});
  await h.waitFor(()=>input(h)&&!input(h).props.disabled);
  await h.act(()=>input(h).props.onChange({target:{value:'two cells only'}}));
  await h.act(()=>input(h).parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>receipt);
  const reads=h.fixture.requests.filter(row=>row.path==='/annotations/read'),writes=h.fixture.requests.filter(row=>row.path==='/annotations');
  assert.equal(reads.length,1);assert.equal(writes.length,1);
  assert.deepEqual(reads[0].body,{target_kind:'cell',target_uuids:['cell-0','cell-2']});
  assert.deepEqual(writes[0].body,{target_kind:'cell',target_uuids:['cell-0','cell-2'],profile_uuid:'author',tags_add:['two cells only'],tags_remove:[],expected_revisions:{'cell-0':0,'cell-2':0}});
  assert.deepEqual([...h.fixture.cellAnnotations.keys()].sort(),['cell-0','cell-2']);
  assert.equal(h.fixture.annotations.size,0);assert.ok(receipt.targets.every(target=>target.target_kind==='cell'));
  assert.equal(h.fixture.requests.some(row=>row.path.includes('/undefined')),false);
 }finally{await h.close();}
});

test('changing selected cells cancels a pending revision read without losing unfinished text or writing old targets',async()=>{
 const h=await createWorkflowHarness();let release,read;
 try{
  const Tags=await h.component('AnnotationTags');
  h.fixture.respond=(url,options,fallback)=>{if(url.pathname==='/api/annotations/read'){read=JSON.parse(options.body);return new Promise(resolve=>{release=resolve;});}return fallback();};
  await h.mount(Tags,props);await h.waitFor(()=>input(h)&&!input(h).props.disabled);
  await h.act(()=>input(h).props.onChange({target:{value:'keep this draft'}}));
  await h.act(()=>input(h).parent.props.onSubmit({preventDefault(){}}));
  await h.render(Tags,{...props,selectedCells:['cell-1']});
  await h.act(()=>release({targets:Object.fromEntries(read.target_uuids.map(id=>[id,{target_kind:'cell',target_uuid:id,revisions:{}}]))}));
  assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations').length,0);
  assert.equal(input(h).props.value,'keep this draft');
 }finally{await h.close();}
});

test('tree cell checkboxes retain exact identities across pages and reject stale tree or epoch-derived targets',async()=>{
 const h=await createWorkflowHarness();let selection;
 try{
  const {default:useSelection,treeCellUuid}=await h.module("annotations/useTreeCellSelection.js");
  const a='00000000-0000-4000-8000-000000000001',b='00000000-0000-4000-8000-000000000002';
  assert.equal(treeCellUuid({value:a},{field:'epoch'}),null);
  assert.equal(treeCellUuid({value:'Cell1'},{field:'cell'}),null);
  assert.equal(treeCellUuid({value:a,missing:true},{field:'cell'}),null);
  assert.equal(treeCellUuid({value:a},{field:'cell'}),a);
  function Probe({source}){selection=useSelection(source);return null;}
  const source={protocolId:'protocol',splits:'date,cell',revision:'view-1'};
  await h.mount(Probe,{source});
  await h.act(()=>{selection.metadata({revision:'tree-1'});selection.status({loading:false,error:null});});
  await h.act(()=>selection.toggle({cell_uuid:a,label:'Cell1'},'tree-1',true));
  await h.act(()=>selection.status({loading:true,error:null}));
  await h.act(()=>selection.toggle({cell_uuid:b,label:'Cell1'},'tree-1',true));
  assert.deepEqual(selection.ids,[a],'loading columns cannot add targets');
  await h.act(()=>{selection.metadata({revision:'tree-1'});selection.status({loading:false,error:null});});
  await h.act(()=>selection.toggle({cell_uuid:b,label:'Cell1'},'tree-1',true));
  assert.deepEqual(selection.ids,[a,b],'reused labels remain distinct recorded cells');
  await h.render(Probe,{source:{...source,revision:'view-2'}});
  assert.equal(selection.blocked,true);assert.deepEqual(selection.ids,[]);
  await h.act(()=>selection.toggle({cell_uuid:a,label:'Cell1'},'tree-1',true));assert.deepEqual(selection.ids,[]);
 }finally{await h.close();}
});

test('epoch tags omit the hidden whole-cell count and request it before an explicit whole-cell edit',async()=>{
 const h=await createWorkflowHarness();let release,held=true,confirmed;
 try{
  const Tags=await h.component('AnnotationTags');
  h.fixture.respond=(url,options,fallback)=>{
   if(url.pathname==='/api/epochs/epoch-0/annotations'){
    if(url.searchParams.get('include_cell_epoch_count')==='false')return annotationValue();
    if(held){held=false;return new Promise(resolve=>{release=resolve;});}
    return annotationValue('epoch-0','cell-0',3);
   }
   return fallback();
  };
  await h.mount(Tags,{epoch:{epoch_uuid:'epoch-0',cell_uuid:'cell-0'},revision:0,reconcileReceipt:true,onChange:(_,receipt)=>{confirmed=receipt;}});
  await h.waitFor(()=>!tagInput(h,'epoch').props.disabled);
  assert.deepEqual(h.fixture.requests.filter(row=>row.path.includes('/annotations')).map(row=>row.path),['/epochs/epoch-0/annotations?include_cell_epoch_count=false']);
  assert.equal(countNotice(h),'');
  await h.act(()=>h.root.findAllByType('button').find(node=>node.children.includes('Whole cell')).props.onClick());
  await h.waitFor(()=>release);
  assert.equal(h.fixture.requests.filter(row=>row.path.includes('/annotations')).at(-1).path,'/epochs/epoch-0/annotations');
  assert.equal(tagInput(h,'cell').props.disabled,true);
  assert.match(countNotice(h),/all epochs/);assert.doesNotMatch(countNotice(h),/0 epochs/);
  await h.act(()=>release(annotationValue('epoch-0','cell-0',3)));
  await h.waitFor(()=>!tagInput(h,'cell').props.disabled);
  assert.match(countNotice(h),/3 epochs/);
  await h.act(()=>tagInput(h,'cell').props.onChange({target:{value:'whole-cell tag'}}));
  await h.act(()=>tagInput(h,'cell').parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>confirmed);
  const write=h.fixture.requests.find(row=>row.path==='/annotations');
  assert.deepEqual(write.body,{target_kind:'cell',target_uuids:['cell-0'],profile_uuid:'author',tags_add:['whole-cell tag'],tags_remove:[],expected_revisions:{'cell-0':0}});
  assert.equal(h.fixture.annotations.size,0);assert.deepEqual(h.fixture.cellAnnotations.get('cell-0'),['whole-cell tag']);
 }finally{await h.close();}
});

test('whole-cell counts follow exact epoch and revision while stale responses cannot reenable old targets',async()=>{
 const h=await createWorkflowHarness(),pending=[];
 try{
  const Tags=await h.component('AnnotationTags');
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/annotations')?new Promise(resolve=>pending.push({url,options,resolve})):fallback();
  const first={epoch:{epoch_uuid:'epoch-0',cell_uuid:'cell-0',annotations:annotationValue()},targetScope:'cell',revision:0};
  await h.mount(Tags,first);await h.waitFor(()=>pending.length===1);
  assert.equal(tagInput(h,'cell').props.disabled,true,'a page with tags but no count requests the displayed count');
  await h.render(Tags,{...first,revision:1});await h.waitFor(()=>pending.length===2);
  assert.equal(pending[0].options.signal.aborted,true);
  await h.render(Tags,{...first,epoch:{epoch_uuid:'epoch-500',cell_uuid:'cell-1'},revision:1});await h.waitFor(()=>pending.length===3);
  assert.equal(pending[1].options.signal.aborted,true);assert.equal(tagInput(h,'cell').props.disabled,true);
  await h.act(()=>pending[2].resolve(annotationValue('epoch-500','cell-1',9)));
  await h.waitFor(()=>!tagInput(h,'cell').props.disabled);assert.match(countNotice(h),/9 epochs/);
  await h.act(()=>{pending[0].resolve(annotationValue('epoch-0','cell-0',50));pending[1].resolve(annotationValue('epoch-0','cell-0',99));});
  assert.match(countNotice(h),/9 epochs/);assert.doesNotMatch(countNotice(h),/50 epochs|99 epochs/);
  assert.equal(h.fixture.requests.some(row=>row.path==='/annotations'),false);
 }finally{await h.close();}
});

test('supplied annotation readers keep their existing route and missing-count presentation',async()=>{
 const h=await createWorkflowHarness(),calls=[];
 try{
  const Tags=await h.component('AnnotationTags'),{WorkspaceRequestProvider}=await h.module('workspaceRequest.js');
  const port={identity:'owned-snapshot',request:async path=>{calls.push(path);return annotationValue();}};
  function Owned(){return React.createElement(WorkspaceRequestProvider,{port},React.createElement(Tags,{epoch:{epoch_uuid:'epoch-0',cell_uuid:'cell-0'},revision:0}));}
  await h.mount(Owned);await h.waitFor(()=>!tagInput(h,'epoch').props.disabled);
  assert.deepEqual(calls,['/epochs/epoch-0/annotations']);
  await h.act(()=>h.root.findAllByType('button').find(node=>node.children.includes('Whole cell')).props.onClick());
  assert.match(countNotice(h),/all epochs/);assert.deepEqual(calls,['/epochs/epoch-0/annotations']);
  assert.equal(h.fixture.requests.length,0);
 }finally{await h.close();}
});
