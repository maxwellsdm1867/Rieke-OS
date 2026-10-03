import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const props={selectedCells:['cell-0','cell-2'],targetScope:'selected-cells',revision:'fresh-tree',reconcileReceipt:true};
const input=h=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.includes('selected cells'));

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
  const {default:useSelection,treeCellUuid}=await h.module('useTreeCellSelection.js');
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
