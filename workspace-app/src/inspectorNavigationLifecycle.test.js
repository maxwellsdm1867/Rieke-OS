import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';
import {createInspectionHarness,cells,sourceA,pageAt} from './test-support/inspectionTreeHarness.js';
const epochs=['A','B','C'].map(letter=>({epoch_uuid:`epoch-${letter}`,cell_uuid:'cell-A',curation:{included:true,tags:[],review_state:'unreviewed'}}));
const props={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',expected_binding_version:2,cells:[{cell_uuid:'cell-A',epochs:100}]},filters:{},revision:0,initialEpochUuid:'epoch-A'};
const page={offset:0,total:100,epochs,cells:props.protocol.cells,query_revision:'query-A',expected_binding_version:2};
function resource(path,data,loading=false,error=null){return {path,data,loading,error,reload(){}};}

test('ready page A/B/C/A focus uses native UUID and cell ownership without anchor/page churn',async()=>{
 const h=await createInspectorHarness();try{
  h.fixture.page=page;await h.render(props);h.fixture.resources.length=0;
  for(const index of [0,1,2,0]){
   h.fixture.epoch=epochs[index];await h.act(()=>h.viewer.treePane.listProps.onFocus(epochs[index].epoch_uuid,epochs[index]));
   assert.equal(h.viewer.epoch.epoch_uuid,epochs[index].epoch_uuid);
   assert.equal(h.viewer.navigation.loading,false);assert.equal(h.viewer.treePane.listProps.disabled,false);
  }
  assert.ok(h.fixture.resources.filter(x=>x.path?.includes('/epochs?')).every(x=>!x.path.includes('anchor_uuid=')));
  assert.ok(h.fixture.resources.filter(x=>x.path?.includes('/epochs?')).every(x=>x.revision===0));
 }finally{await h.close();}
});

test('pending cross-page anchor keeps exact list read scope, gates writes and latest A/B/A intent wins',async()=>{
 const h=await createInspectorHarness();let resolved=null;
 try{
  h.fixture.resource=(path)=>path?.includes('/epochs?')?resource(path,path.includes('anchor_uuid=')?resolved:page,path.includes('anchor_uuid=')&&!resolved):null;
  await h.render(props);const originalSource=h.viewer.treePane.listProps.source;
  const outside=letter=>({epoch_uuid:`outside-${letter}`,cell_uuid:'cell-A'});
  for(const letter of ['A','B','A']){
   h.fixture.epoch=outside(letter);await h.act(()=>h.viewer.treePane.listProps.onFocus(`outside-${letter}`,outside(letter)));
   assert.deepEqual(h.viewer.treePane.listProps.source,originalSource);
   assert.equal(h.viewer.treePane.listProps.navigationDisabled,false);
   assert.equal(h.viewer.treePane.listProps.disabled,true);
   assert.equal(h.viewer.treePane.treeProps.actionsDisabled,true);
  }
  const paths=h.fixture.resources.filter(x=>x.path?.includes('anchor_uuid='));
  assert.ok(paths.at(-1).path.includes('outside-A'));
  // The resource path fence rejects a response from a superseded anchor.
  h.fixture.resource=path=>path?.includes('anchor_uuid=')?resource('/protocols/protocol-A/epochs?anchor_uuid=outside-B',{...page,epochs:[outside('B')]}):path?.includes('/epochs?')?resource(path,page):null;
  await h.render(props);assert.equal(h.viewer.navigation.loading,true);
  resolved={...page,offset:60,epochs:[outside('A')]};
  h.fixture.resource=path=>path?.includes('/epochs?')?resource(path,resolved):null;
  await h.render(props);assert.equal(h.viewer.navigation.loading,false);assert.equal(h.viewer.epoch.epoch_uuid,'outside-A');
 }finally{await h.close();}
});

test('filter/annotation/binding/source context changes invalidate retained navigation and old callbacks',async()=>{
 for(const change of ['filter','annotation','binding','context']){
  const h=await createInspectorHarness();try{
   h.fixture.resource=path=>path?.includes('/epochs?')?resource(path,path.includes('anchor_uuid=')?null:page,path.includes('anchor_uuid=')):null;
   await h.render(props);await h.act(()=>h.viewer.treePane.listProps.onFocus('outside-A',{epoch_uuid:'outside-A',cell_uuid:'cell-A'}));
   const old=h.viewer.treePane.listProps.onFocus;
   h.fixture.resource=path=>path?.includes('/epochs?')?resource(path,null,true):null;
   await h.render({...props,...(change==='filter'?{filters:{tag:'changed'}}:change==='annotation'?{revision:1}:change==='binding'?{protocol:{...props.protocol,expected_binding_version:3}}:{readContext:{root:'/protocols/protocol-A/workbench/candidates/candidate-A',candidate_scope_revision:'scope-A'}})});
   assert.equal(h.viewer.treePane.listProps.navigationDisabled,true,change);
   await h.act(()=>old('old-B',{epoch_uuid:'old-B',cell_uuid:'cell-A'}));
   assert.equal(h.fixture.resources.some(x=>x.path?.includes('anchor_uuid=old-B')),false,change);
  }finally{await h.close();}
 }
});

test('anchor failure disables retained list navigation; scoped detail waits for current page membership',async()=>{
 const h=await createInspectorHarness();let failure=false;
 try{
  h.fixture.page=page;await h.render({...props,filters:{metadata_predicate:'{"all":[]}'}});
  h.fixture.epoch={epoch_uuid:'outside-A',cell_uuid:'cell-A'};
  h.fixture.resource=path=>path?.includes('anchor_uuid=')?resource(path,null,!failure,failure?'changed membership':null):path?.includes('/epochs?')?resource(path,page):null;
  await h.act(()=>h.viewer.treePane.listProps.onFocus('outside-A',h.fixture.epoch));
  assert.equal(h.viewer.epoch,null);assert.equal(h.viewer.treePane.listProps.navigationDisabled,false);
  failure=true;await h.render({...props,filters:{metadata_predicate:'{"all":[]}'}});
  assert.equal(h.viewer.epoch,null);assert.equal(h.viewer.treePane.listProps.navigationDisabled,false); // fresh offset receipt is current again
 }finally{await h.close();}
});

test('cell list permits plain read navigation while inclusion and modified bulk selection stay fenced',async()=>{
 const h=await createInspectionHarness();let focused=[],targets=[];
 const p={cells,source:sourceA,revision:0,targets:[],disabled:true,navigationDisabled:false,onFocus:uuid=>focused.push(uuid),setTargets:value=>targets.push(value)};
 try{
  await h.render(p);await h.selectEpoch(1,{});assert.deepEqual(focused,['cell-A-1']);
  await h.selectEpoch(2,{ctrlKey:true});await h.selectEpoch(3,{shiftKey:true});assert.deepEqual(focused,['cell-A-1']);
  await h.render({...p,source:{...sourceA,queryRevision:'query-B'},navigationDisabled:true});
  await h.selectEpoch(4,{},'cell-A',pageAt());assert.deepEqual(focused,['cell-A-1']);
 }finally{await h.close();}
});

import {createWorkflowHarness} from './test-support/workflowHarness.js';
async function openCell(h){
 const date=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date');
 await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
 const cell=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell');
 await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
 await h.waitFor(()=>h.root.findAllByProps({className:'epoch-row cell-tree-epoch '}).length>0||h.root.findAllByType('button').some(node=>node.props['aria-label']?.startsWith('Inspect ')));
}
function row(h,ordinal){return h.root.findAllByType('button').find(node=>node.props['aria-label']?.startsWith('Inspect ')&&node.props['aria-label'].endsWith(` epoch ${ordinal}`));}

test('real mounted hooks keep loaded rows mounted through rapid 9/10/12/9 selection with no page GETs',async()=>{
 const h=await createWorkflowHarness({total:500});try{
  const Inspector=await h.component('Inspector');await h.mount(Inspector,{...props,protocol:{...props.protocol,query_revision:'query-0',cells:[{cell_uuid:'cell-0',date:'2026-09-29',label:'Cell 0',epochs:500}]},initialEpochUuid:'epoch-0'});
  await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);await openCell(h);
  const node=row(h,9),before=h.fixture.requests.length;
  for(const ordinal of [9,10,12,9]){
   const button=row(h,ordinal);assert.ok(button);assert.equal(button.props.disabled,false);
   await h.act(()=>button.props.onClick({}));assert.equal(row(h,9),node);
  }
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');
  assert.equal(h.fixture.requests.slice(before).filter(item=>item.path.includes('/epochs?')).length,0);
  assert.equal(h.viewer.navigation.loading,false);
 }finally{await h.close();}
});

test('real hooks abort/reject late cross-page anchors and preserve clickable list for latest 61/62/63',async()=>{
 const h=await createWorkflowHarness({total:500}),pending=[];
 try{
  const Inspector=await h.component('Inspector');await h.mount(Inspector,{...props,protocol:{...props.protocol,query_revision:'query-0'},initialEpochUuid:'epoch-0'});
  await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);await openCell(h);
  const next=h.root.findAllByType('button').find(node=>node.props['aria-label']?.startsWith('Next epochs for'));
  await h.act(()=>next.props.onClick());await h.waitFor(()=>!!row(h,61));
  h.fixture.respond=(url,options,result)=>url.searchParams.has('anchor_uuid')?new Promise(resolve=>pending.push({resolve:()=>resolve(result()),signal:options.signal,uuid:url.searchParams.get('anchor_uuid')})):result();
  for(const ordinal of [61,62,63]){
   const button=row(h,ordinal);assert.ok(button);assert.equal(button.props.disabled,false);
   await h.act(()=>button.props.onClick({}));await h.waitFor(()=>pending.length===ordinal-60);
   assert.equal(h.viewer.treePane.listProps.disabled,true);
   assert.equal(h.viewer.treePane.listProps.navigationDisabled,false);
  }
  assert.deepEqual(pending.map(p=>p.uuid),['epoch-60','epoch-61','epoch-62']);
  assert.equal(pending[0].signal.aborted,true);assert.equal(pending[1].signal.aborted,true);
  await h.act(()=>pending[2].resolve());await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-62'&&!h.viewer.navigation.loading);
  await h.act(()=>{pending[1].resolve();pending[0].resolve();});await h.settle(100);
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-62');assert.equal(h.viewer.navigation.position,62);
 }finally{for(const p of pending)p.resolve();await h.close();}
});

test('retained plain-click callback cannot navigate when only navigation permission changes',async()=>{
 const h=await createInspectionHarness();let focused=[];
 const p={cells,source:sourceA,revision:0,targets:[],disabled:true,navigationDisabled:false,onFocus:uuid=>focused.push(uuid),setTargets:()=>{}};
 try{
  await h.render(p);const old=h.branch.onSelect;await h.render({...p,navigationDisabled:true});
  const page=pageAt(),epoch=page.epochs[1];
  await h.act(()=>old({}, {cellUuid:'cell-A',index:1,uuid:epoch.epoch_uuid},epoch,page));
  assert.deepEqual(focused,[]);
 }finally{await h.close();}
});

test('annotation authority refresh with equal membership disables old navigation until fresh receipt arrives',async()=>{
 const h=await createWorkflowHarness({total:40});
 try{
  await h.mount();await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);await openCell(h);
  await h.waitFor(()=>h.root.findAllByType('input').some(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props.disabled));
  const old=h.viewer.treePane.listProps.onFocus;
  const input=h.root.findAllByType('input').find(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props['aria-label'].startsWith('Tag to add'));
  await h.act(()=>input.props.onChange({target:{value:'new tag'}}));
  await h.act(()=>input.parent.props.onSubmit({preventDefault(){}}));
  assert.equal(h.fixture.generation,1);assert.equal(h.viewer.treePane.listProps.navigationDisabled,true);
  const before=h.fixture.requests.length;await h.act(()=>old('epoch-9',{epoch_uuid:'epoch-9',cell_uuid:'cell-0'}));
  assert.equal(h.fixture.requests.slice(before).some(item=>item.path.includes('anchor_uuid=epoch-9')),false);
  await h.waitFor(()=>!h.viewer.treePane.listProps.navigationDisabled);
  assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-1');
  await h.act(()=>row(h,10).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-9');
 }finally{await h.close();}
});

test('reselecting the active Inspect tab returns from design without remounting or rereading rows',async()=>{
 const h=await createWorkflowHarness({total:500});try{
  await h.mount(h.Protocol,{id:'protocol-A',revision:0,structureRevision:0,initialInspection:{epoch_uuid:'epoch-0'},onChange(){}});
  await h.waitFor(()=>h.root.findAllByType('workflow-viewer').length>0&&!h.viewer.treePane.listProps.disabled);
  await openCell(h);await h.act(()=>row(h,9).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');
  const node=row(h,9),mounts=h.fixture.mounts;
  const start=h.fixture.requests.length;
  const tab=h.root.findAllByType('button').find(n=>n.props.role==='tab'&&n.props['aria-label']==='Inspect');
  for(let i=0;i<3;i++)await h.act(()=>tab.props.onClick());
  assert.equal(h.viewer.designMode,false);assert.equal(h.viewer.treePane.treeMode,false);
  assert.equal(h.fixture.requests.slice(start).filter(r=>r.path.includes('/epochs?')||r.path==='/metadata/fields').length,0);
  await h.act(()=>h.viewer.toolbar.onDesign());assert.equal(h.viewer.designMode,true);
  await h.act(()=>tab.props.onClick());assert.equal(h.viewer.designMode,false);
  assert.equal(h.fixture.mounts,mounts);assert.equal(h.fixture.unmounts,0);
  assert.equal(row(h,9),node);assert.equal(h.viewer.epoch.epoch_uuid,'epoch-8');
  assert.equal(h.fixture.requests.slice(start).filter(r=>r.path.includes('/epochs?')).length,0);
 }finally{await h.close();}
});
