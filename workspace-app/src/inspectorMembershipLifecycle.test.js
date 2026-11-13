import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';
import {deferred} from './test-support/pagedTreeHarness.js';

const props={protocol:{definition:{protocol_uuid:'protocol-A',name:'Pinned native protocol',initial_revision_uuid:'pinned-A'},query_revision:'query-A',expected_binding_version:2,cells:[]},filters:{},revision:0,initialEpochUuid:'epoch-A'};
const receipt=ids=>({protocol_uuid:'protocol-A',binding:{version:3},removed_epoch_uuids:ids});
function elements(element,predicate){
 if(!element||typeof element!=='object')return [];
 const children=element.props?.children;
 return [...(predicate(element)?[element]:[]),...(Array.isArray(children)?children:[children]).flatMap(child=>elements(child,predicate))];
}
const focusedRemove=h=>elements(h.viewer.detailExtras,item=>item.type==='button'&&item.props.children==='Remove this epoch from pinned protocol');
const text=element=>typeof element==='string'?element:element&&typeof element==='object'?[element.props?.children].flat().map(text).join(''):'';
const removalDialog=h=>elements(h.viewer.before,item=>typeof item.props?.onConfirm==='function'&&'protocolName' in item.props)[0];
const errorText=h=>elements(h.viewer.before,item=>item.props?.role==='alert').map(text).join('');

test('pinned Main alone exposes selected and focused membership removal',async()=>{
 for(const mode of ['pinned','automatic','incoming']){
  const h=await createInspectorHarness();
  try{
   await h.render({...props,...(mode==='automatic'?{protocol:{...props.protocol,definition:{protocol_uuid:'protocol-A'}}}:mode==='incoming'?{readContext:{root:'/protocols/protocol-A/workbench/candidates/candidate-A',candidate_scope_revision:'query-A'}}:{})});
   assert.equal(typeof h.viewer.selectionActions.onRemove,mode==='pinned'?'function':'undefined',mode);
   assert.equal(typeof h.viewer.selectionActions.onSelectAll,mode==='pinned'?'function':'undefined',mode);
   assert.equal(typeof h.viewer.selectionActions.onSelectCell,mode==='pinned'?'function':'undefined',mode);
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
   assert.equal(calls.length,0,'opening confirmation does not write');
   assert.equal(removalDialog(h).props.protocolName,'Pinned native protocol');
   await h.act(()=>removalDialog(h).props.onConfirm());
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

test('focused removal confirms a singleton command and clears the removed focus on confirmed completion',async()=>{
 const h=await createInspectorHarness(),calls=[];
 h.fixture.api=async(path,options)=>{calls.push({path,...options});return receipt(options.body.epoch_uuids);};
 try{
  await h.render(props);
  const [button]=focusedRemove(h);assert.equal(button.props.disabled,false);
  await h.act(()=>button.props.onClick());
  assert.equal(calls.length,0);assert.equal(removalDialog(h).props.count,1);
  await h.act(()=>removalDialog(h).props.onConfirm());
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
  await h.act(()=>h.viewer.selectionActions.onRemove());
  let work;await h.act(()=>{work=removalDialog(h).props.onConfirm();});
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
   assert.equal(calls.length,0,'opening confirmation does not write');
   assert.equal(removalDialog(h).props.protocolName,'Pinned native protocol');
   await h.act(()=>removalDialog(h).props.onConfirm());
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
   await h.act(()=>h.viewer.selectionActions.onRemove());
  let work;await h.act(()=>{work=removalDialog(h).props.onConfirm();});
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

test('Cancel retires removal consent without writing, and an old confirm callback cannot revive it',async()=>{
 const h=await createInspectorHarness(),calls=[];
 h.fixture.api=(...args)=>{calls.push(args);return Promise.resolve(receipt(['epoch-B']));};
 try{
  await h.render(props);await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
  await h.act(()=>h.viewer.selectionActions.onRemove());
  const dialog=removalDialog(h);assert.equal(dialog.props.count,1);
  await h.act(()=>dialog.props.onClose());
  assert.equal(removalDialog(h),undefined);
  await h.act(()=>dialog.props.onConfirm());
  assert.equal(calls.length,0);assert.deepEqual(h.viewer.targets,['epoch-B']);
 }finally{await h.close();}
});

test('pending removal confirmation refuses changed selection, scope, binding or query even after return',async()=>{
 for(const change of ['selection','filter','query','binding','revision','project','paused','round-trip']){
  const h=await createInspectorHarness(),calls=[];
  h.fixture.api=(...args)=>{calls.push(args);return Promise.resolve(receipt(['epoch-B']));};
  try{
   await h.render(props);await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
   await h.act(()=>h.viewer.selectionActions.onRemove());const confirm=removalDialog(h).props.onConfirm;
   if(change==='selection'||change==='round-trip'){
    await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-C']));
    if(change==='round-trip')await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
   }else await h.render({...props,...(change==='filter'?{filters:{cell_type:'other'}}:change==='revision'?{revision:1}:change==='project'?{projectId:'other-project'}:change==='paused'?{readPaused:true}:{protocol:{...props.protocol,...(change==='query'?{query_revision:'query-B'}:{expected_binding_version:3})}})});
   assert.equal(removalDialog(h).props.stale,true,change);
   await h.act(()=>confirm());
   assert.equal(calls.length,0,change);assert.match(errorText(h),/Selection or dataset changed/,change);
  }finally{await h.close();}
 }
});

test('pinned Select all and focused-cell selection replace targets only after complete bounded membership reads',async()=>{
 for(const cellOnly of [false,true]){
  const h=await createInspectorHarness(),calls=[],last=deferred();
  const ids=Array.from({length:61},(_,i)=>`selected-${i}`);
  h.fixture.api=(path,options)=>{
   calls.push({path,...options});const offset=Number(new URL(path,'http://fixture').searchParams.get('offset'));
   const page={offset,total:61,selection_revision:'selection-A',query_revision:'query-A',expected_binding_version:2,epochs:ids.slice(offset,offset+60).map(epoch_uuid=>({epoch_uuid,cell_uuid:'cell-A'}))};
   return offset===0?Promise.resolve(page):last.promise.then(()=>page);
  };
  try{
   await h.render({...props,filters:{cell_type:'ON'}});await h.act(()=>h.viewer.treePane.listProps.setTargets(['original']));
   assert.equal(h.viewer.selectionActions.cellSelectDisabled,false);
   let work;await h.act(()=>{work=cellOnly?h.viewer.selectionActions.onSelectCell():h.viewer.selectionActions.onSelectAll();});
   assert.equal(calls.length,2);assert.deepEqual(h.viewer.targets,['original']);
   for(const call of calls){const url=new URL(call.path,'http://fixture');assert.equal(url.searchParams.get('cell_type'),'ON');assert.equal(url.searchParams.get('cell_uuid'),cellOnly?'cell-A':null);assert.equal(url.searchParams.get('limit'),'60');assert.ok(call.signal);assert.notEqual(call.method,'POST');}
   await h.act(async()=>{last.resolve();await work;});
   assert.deepEqual(h.viewer.targets,ids);assert.equal(h.viewer.selectionActions.disabled,false);
  }finally{await h.close();}
 }
});

test('Select all refuses partial membership after selection or scope changes while reading',async()=>{
 for(const change of ['selection','query','project']){
  const h=await createInspectorHarness(),pending=deferred(),calls=[];
  h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
  try{
   await h.render(props);await h.act(()=>h.viewer.treePane.listProps.setTargets(['original']));
   let work;await h.act(()=>{work=h.viewer.selectionActions.onSelectAll();});
   if(change==='selection')await h.act(()=>h.viewer.treePane.listProps.setTargets(['new-selection']));
   else {await h.render({...props,...(change==='query'?{protocol:{...props.protocol,query_revision:'query-B'}}:{projectId:'other-project'})});await h.act(()=>h.viewer.treePane.listProps.setTargets(['new-selection']));}
   await h.act(async()=>{pending.resolve({offset:0,total:1,selection_revision:'selection-A',query_revision:'query-A',expected_binding_version:2,epochs:[{epoch_uuid:'stale-member',cell_uuid:'cell-A'}]});await work;});
   assert.equal(calls.length,1);assert.deepEqual(h.viewer.targets,['new-selection']);
   assert.equal(calls[0].signal.aborted,true);
  }finally{await h.close();}
 }
});

test('busy retained selection reads cancel on departure and cannot publish after route or nested-panel return',async()=>{
 for(const nested of [false,true]){
  const h=await createInspectorHarness(),pending=deferred(),calls=[];
  h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
  try{
   await h.render(props,{retainedActive:true});await h.act(()=>h.viewer.treePane.listProps.setTargets(['original']));
   let work;await h.act(()=>{work=h.viewer.selectionActions.onSelectAll();});
   assert.equal(h.viewer.selectionActions.disabled,true,'selection read keeps the retained owner busy');
   await h.render(props,{retainedActive:nested,nestedActive:!nested,retainedBusy:true});
   assert.equal(calls[0].signal.aborted,true,'hidden busy owners must cancel manual membership reads');
   await h.render(props,{retainedActive:true,retainedBusy:true});
   await h.act(async()=>{pending.resolve({offset:0,total:1,selection_revision:'selection-A',query_revision:'query-A',expected_binding_version:2,epochs:[{epoch_uuid:'late-result',cell_uuid:'cell-A'}]});await work;});
   assert.deepEqual(h.viewer.targets,['original']);assert.equal(calls.length,1);
  }finally{await h.close();}
 }
});

test('retained confirmation consent retires on departure while other work keeps effects connected',async()=>{
 for(const nested of [false,true]){
  const h=await createInspectorHarness(),calls=[];
  h.fixture.api=(...args)=>{calls.push(args);return Promise.resolve(receipt(['epoch-B']));};
  try{
   await h.render(props,{retainedActive:true,retainedBusy:true});await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
   await h.act(()=>h.viewer.selectionActions.onRemove());const confirm=removalDialog(h).props.onConfirm;
   await h.render(props,{retainedActive:nested,nestedActive:!nested,retainedBusy:true});
   await h.render(props,{retainedActive:true,retainedBusy:true});
   assert.equal(removalDialog(h),undefined);
   await h.act(()=>confirm());assert.equal(calls.length,0);assert.deepEqual(h.viewer.targets,['epoch-B']);
  }finally{await h.close();}
 }
});

test('accepted removal POST survives retained departure and invalidates its original protocol',async()=>{
 const h=await createInspectorHarness(),pending=deferred(),calls=[],changes=[];
 h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
 const initial={...props,onChange:event=>changes.push(event)};
 try{
  await h.render(initial,{retainedActive:true});await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
  await h.act(()=>h.viewer.selectionActions.onRemove());let work;await h.act(()=>{work=removalDialog(h).props.onConfirm();});
  await h.render(initial,{retainedActive:false,retainedBusy:true});
  assert.equal(calls[0].signal,undefined,'accepted writes are not aborted with selection reads');
  await h.act(async()=>{pending.resolve(receipt(['epoch-B']));await work;});
  assert.equal(calls.length,1);assert.deepEqual(changes,[{kind:'membership',protocolId:'protocol-A'}]);
  await h.render(initial,{retainedActive:true});
  assert.deepEqual(h.viewer.targets,['epoch-B'],'late completion invalidates data without replaying selection cleanup into a returned view');
 }finally{await h.close();}
});

test('accepted removal cannot regain UI cleanup authority after nested-panel hide and return',async()=>{
 const h=await createInspectorHarness(),pending=deferred(),calls=[],changes=[];
 h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
 const initial={...props,onChange:event=>changes.push(event)};
 try{
  await h.render(initial,{retainedActive:true});await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
  await h.act(()=>h.viewer.selectionActions.onRemove());let work;await h.act(()=>{work=removalDialog(h).props.onConfirm();});
  await h.render(initial,{retainedActive:true,nestedActive:false,retainedBusy:true});
  await h.render(initial,{retainedActive:true,nestedActive:true,retainedBusy:true});
  await h.act(async()=>{pending.resolve(receipt(['epoch-B']));await work;});
  assert.equal(calls.length,1);assert.equal(calls[0].signal,undefined);
  assert.deepEqual(changes,[{kind:'membership',protocolId:'protocol-A'}]);
  assert.deepEqual(h.viewer.targets,['epoch-B']);
 }finally{await h.close();}
});
