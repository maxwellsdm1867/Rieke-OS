import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';
import {deferred} from './test-support/pagedTreeHarness.js';

const props={protocol:{definition:{protocol_uuid:'protocol-A',initial_revision_uuid:'pinned-A'},query_revision:'query-A',expected_binding_version:2,cells:[]},filters:{},revision:0,initialEpochUuid:'epoch-A'};
const receipt=ids=>({protocol_uuid:'protocol-A',binding:{version:3},removed_epoch_uuids:ids});
function elements(element,predicate){
 if(!element||typeof element!=='object')return [];
 const children=element.props?.children;
 return [...(predicate(element)?[element]:[]),...(Array.isArray(children)?children:[children]).flatMap(child=>elements(child,predicate))];
}
const focusedRemove=h=>elements(h.viewer.detailExtras,item=>item.type==='button'&&item.props.children==='Remove this epoch from pinned protocol');
const text=element=>typeof element==='string'?element:element&&typeof element==='object'?[element.props?.children].flat().map(text).join(''):'';
const errorText=h=>elements(h.viewer.before,item=>item.props?.role==='alert').map(text).join('');

test('pinned Main alone exposes selected and focused membership removal',async()=>{
 for(const mode of ['pinned','automatic','incoming']){
  const h=await createInspectorHarness();
  try{
   await h.render({...props,...(mode==='automatic'?{protocol:{...props.protocol,definition:{protocol_uuid:'protocol-A'}}}:mode==='incoming'?{readContext:{root:'/protocols/protocol-A/workbench/candidates/candidate-A',candidate_scope_revision:'query-A'}}:{})});
   assert.equal(typeof h.viewer.selectionActions.onRemove,mode==='pinned'?'function':'undefined',mode);
   assert.equal(focusedRemove(h).length,mode==='pinned'?1:0,mode);
   await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B','epoch-C']));
   assert.equal(focusedRemove(h).length,0,'a selected set must not also expose a focused singleton command');
  }finally{await h.close();}
 }
});

test('list and split-tree removal send only the exact selected UUIDs with current binding and scope',async()=>{
 for(const mode of ['list','tree']){
  const h=await createInspectorHarness(),calls=[],changes=[];
  h.fixture.api=async(path,options)=>{calls.push({path,...options});return receipt(options.body.epoch_uuids);};
  try{
   await h.render({...props,filters:{cell_type:'ON'},onChange:event=>changes.push(event)});
   const selected=['epoch-D','epoch-B'];
   await h.act(()=>mode==='list'?h.viewer.treePane.listProps.setTargets(selected):h.viewer.treePane.treeProps.setSelectedEpochs(selected));
   assert.equal(h.viewer.selectionActions.disabled,false);
   await h.act(()=>h.viewer.selectionActions.onRemove());
   assert.equal(calls.length,1,mode);
   assert.equal(calls[0].path,'/protocols/protocol-A/membership/remove');
   assert.equal(calls[0].method,'POST');
   assert.equal(calls[0].signal,undefined,'accepted writes must survive navigation');
   assert.deepEqual(calls[0].body,{epoch_uuids:selected,query_revision:'query-A',expected_binding_version:2,selection_scope:{filters:{cell_type:'ON'},cell_uuid:null}});
   assert.deepEqual(h.viewer.targets,[]);
   assert.deepEqual(changes,[{kind:'membership',protocolId:'protocol-A'}]);
  }finally{await h.close();}
 }
});

test('focused removal is an immediate singleton command and clears the removed focus on confirmed completion',async()=>{
 const h=await createInspectorHarness(),calls=[];
 h.fixture.api=async(path,options)=>{calls.push({path,...options});return receipt(options.body.epoch_uuids);};
 try{
  await h.render(props);
  const [button]=focusedRemove(h);assert.equal(button.props.disabled,false);
  await h.act(()=>button.props.onClick());
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0].body,{epoch_uuids:['epoch-A'],query_revision:'query-A',expected_binding_version:2,selection_scope:{filters:{},cell_uuid:null}});
  assert.equal(h.viewer.epoch,null);
  assert.deepEqual(h.viewer.targets,[]);
 }finally{await h.close();}
});

test('retained remove callbacks cannot submit after selection or dataset authority changes',async()=>{
 for(const change of ['selection','filter','query','binding','revision']){
  const h=await createInspectorHarness(),calls=[];
  h.fixture.api=(...args)=>{calls.push(args);return Promise.resolve(receipt(['epoch-B']));};
  try{
   await h.render(props);await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
   const oldRemove=h.viewer.selectionActions.onRemove;
   if(change==='selection')await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-C']));
   else await h.render({...props,...(change==='filter'?{filters:{cell_type:'other'}}:change==='revision'?{revision:1}:{protocol:{...props.protocol,...(change==='query'?{query_revision:'query-B'}:{expected_binding_version:3})}})});
   await h.act(()=>oldRemove());
   assert.equal(calls.length,0,change);
   assert.match(errorText(h),/Selection or dataset changed/,change);
  }finally{await h.close();}
 }
});

test('a confirmed removal invalidates its origin without clearing a newer selection or replaying the write',async()=>{
 const h=await createInspectorHarness(),pending=deferred(),calls=[],changes=[];
 h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
 try{
  const initial={...props,onChange:event=>changes.push(event)};
  await h.render(initial);await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B','epoch-C']));
  let work;await h.act(()=>{work=h.viewer.selectionActions.onRemove();});
  await h.render({...initial,revision:1});
  await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-D']));
  await h.act(async()=>{pending.resolve(receipt(['epoch-C','epoch-B']));await work;});
  assert.equal(calls.length,1);assert.equal(calls[0].signal,undefined);
  assert.deepEqual(h.viewer.targets,['epoch-D']);
  assert.deepEqual(changes,[{kind:'membership',protocolId:'protocol-A'}]);
 }finally{await h.close();}
});

test('unconfirmed removal renews membership without clearing the selection or retrying',async()=>{
 for(const failure of ['transport','wrong-protocol','wrong-binding','wrong-targets']){
  const h=await createInspectorHarness(),calls=[],changes=[];
  h.fixture.api=async(path,options)=>{
   calls.push({path,...options});
   if(failure==='transport')throw Error('Connection lost after submission');
   return {...receipt(['epoch-B','epoch-C']),...(failure==='wrong-protocol'?{protocol_uuid:'other'}:failure==='wrong-binding'?{binding:{version:4}}:{removed_epoch_uuids:['epoch-B','epoch-D']})};
  };
  try{
   await h.render({...props,onChange:event=>changes.push(event)});
   await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B','epoch-C']));
   await h.act(()=>h.viewer.selectionActions.onRemove());
   assert.equal(calls.length,1,failure);
   assert.deepEqual(h.viewer.targets,['epoch-B','epoch-C'],failure);
   assert.deepEqual(changes,[{kind:'membership',protocolId:'protocol-A'}],failure);
   assert.match(errorText(h),failure==='transport'?/Connection lost/:/receipt was incomplete/,failure);
  }finally{await h.close();}
 }
});

test('accepted removal completion after a protocol switch invalidates only the origin and keeps the new selection',async()=>{
 for(const outcome of ['confirmed','unconfirmed']){
  const h=await createInspectorHarness(),pending=deferred(),calls=[],originChanges=[],destinationChanges=[];
  h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
  try{
   await h.render({...props,onChange:event=>originChanges.push(event)});
   await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B','epoch-C']));
   let work;await h.act(()=>{work=h.viewer.selectionActions.onRemove();});
   await h.render({...props,protocol:{...props.protocol,definition:{protocol_uuid:'protocol-B',initial_revision_uuid:'pinned-B'},query_revision:'query-B',expected_binding_version:5},onChange:event=>destinationChanges.push(event)});
   await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-D']));
   await h.act(async()=>{if(outcome==='confirmed')pending.resolve(receipt(['epoch-B','epoch-C']));else pending.reject(Error('Completion unavailable'));await work;});
   assert.equal(calls.length,1,outcome);
   assert.deepEqual(h.viewer.targets,['epoch-D'],outcome);
   assert.deepEqual(originChanges,[{kind:'membership',protocolId:'protocol-A'}],outcome);
   assert.deepEqual(destinationChanges,[],outcome);
  }finally{await h.close();}
 }
});
