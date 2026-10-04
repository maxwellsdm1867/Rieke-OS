import test from 'node:test';
import assert from 'node:assert/strict';
import {groupQueryScope,previewTreeGroup,confirmGroupReceipt,releaseGroupPreview} from './treeGroupQueryTags.js';
import {persistUndo} from './useMutationUndo.js';
import {createUndoHistory,mutationUndo} from './mutationUndo.js';
import {groupAnnotationRecovery as recovery} from './groupAnnotationRecovery.js';
const scope={protocolId:'protocol',filters:{metadata_predicate:'{"all":[]}'},splits:'parameters/value'},revision='a'.repeat(64),path=['b'.repeat(64)];
function receipt(body,count=1857){return {format:'rieke-group-annotation-receipt',version:1,action:'add',operation_uuid:body.operation_uuid,target_kind:'epoch',target_count:count,changed:count-1,unchanged:1,profile_uuid:body.profile_uuid,tag:body.tag,undo:{kind:'annotation_group',operation_uuid:body.operation_uuid,count:count-1}};}
test('query preview contains complete scope/path and no page offsets or epoch identities',async()=>{
 const calls=[];const request=async(route,options)=>{calls.push({route,...options});return {selection_uuid:'server-selection',target_kind:'epoch',count:1857,profile_uuid:'author',tree_revision:revision};};
 const target=await previewTreeGroup({scope,path,revision,count:1857,profileUuid:'author',request});
 assert.deepEqual(calls[0].body,{scope:{protocol_uuid:'protocol',filters:scope.filters,splits:scope.splits,path,revision},profile_uuid:'author'});
 assert.equal(target.count,1857);assert.equal(target.ids,undefined);assert.equal(target.epoch.annotations.epoch_tags.length,0);
 await releaseGroupPreview(target,request);assert.deepEqual(calls[1].body,{selection_uuid:'server-selection'});
 assert.throws(()=>groupQueryScope({...scope,readContext:{root:'/workbench'}},path,revision),/not supported/);
});
test('unconfirmed group save retries same operation and refuses a different tag',async()=>{
 const calls=[];let failed=false;
 const request=async(route,options)=>{
  if(route.endsWith('preview'))return {selection_uuid:'selection',target_kind:'epoch',count:1857,profile_uuid:'author',tree_revision:revision};
  calls.push(options.body);if(!failed){failed=true;throw Object.assign(Error('Recovery unconfirmed'),{saved:true});}
  return receipt(options.body);
 };
 const target=await previewTreeGroup({scope,path,revision,count:1857,profileUuid:'author',request});
 await assert.rejects(target.groupMutation.save({tag:'tag',profileUuid:'author'}),/Recovery/);
 await assert.rejects(target.groupMutation.save({tag:'different',profileUuid:'author'}),/Retry/);
 const saved=await target.groupMutation.save({tag:'tag',profileUuid:'author'});
 assert.deepEqual(calls[0],calls[1]);assert.equal(saved.changed,1856);assert.equal('target_uuids' in calls[0],false);
});
test('compact server inverse reference exceeds 1000 safely and retries the same inverse operation',async()=>{
 const history=createUndoHistory();history.project('owned project');history.record({kind:'annotation_group',operation_uuid:'forward',profile_uuid:'author',count:1856});
 assert.equal(history.view().count,1);assert.ok(history.view().bytes<2048);
 const calls=[];let first=true;
 const request=async(route,options)=>{calls.push({route,body:options.body});if(first){first=false;throw Object.assign(Error('Recovery unconfirmed'),{saved:true});}return {format:'rieke-group-annotation-receipt',version:1,action:'undo',operation_uuid:options.body.operation_uuid,target_kind:'epoch',target_count:1856,changed:1856,unchanged:0,profile_uuid:'author',forward_operation_uuid:'forward'};};
 assert.equal(await history.undo(action=>persistUndo(action,request)),false);assert.equal(history.view().count,1);
 assert.equal(await history.undo(action=>persistUndo(action,request)),true);assert.equal(history.view().count,0);
 assert.deepEqual(calls[0],calls[1]);assert.deepEqual(Object.keys(calls[0].body),['operation_uuid']);
});
test('incomplete, partial or wrong-profile receipt never confirms the group',()=>{
 const body={operation_uuid:'operation',profile_uuid:'author',tag:'tag'},good=receipt(body);
 const args={operationUuid:'operation',profileUuid:'author',count:1857,tag:'tag'};
 assert.equal(confirmGroupReceipt(good,args),good);
 for(const changes of [{target_count:1000},{changed:1857},{profile_uuid:'foreign'},{persistence:{database:'unknown'}},{undo:{kind:'annotation_group',operation_uuid:'operation',count:1000}}])assert.throws(()=>confirmGroupReceipt({...good,...changes},args),/not confirmed/);
});

test('recovery slots reserve on save, never evict, and preserve original project/profile',async()=>{
 const previous=recovery.currentProject();recovery.project('original-project');
 let requests=0;const bodies=[],targets=[];
 const request=async(route,{body})=>{
  if(route.endsWith('group-preview'))return preview(body);
  requests++;bodies.push(body);throw refusal();
 };
 try{
  for(let index=0;index<5;index++)targets.push(await open(request));
  assert.equal(recovery.view().length,0);assert.equal(requests,0);
  for(const target of targets.slice(0,4))await assert.rejects(target.groupMutation.save(save),/Definite refusal/);
  const rows=recovery.view();assert.equal(rows.length,4);
  await assert.rejects(targets[4].groupMutation.save(save),/four/);assert.equal(requests,4);
  assert.deepEqual(recovery.view(),rows);
  recovery.project('different-project');await assert.rejects(targets[4].groupMutation.save(save),/original project/);assert.equal(requests,4);
  recovery.project('original-project');recovery.dismiss(rows[0].operation_uuid);
  await assert.rejects(targets[4].groupMutation.save({...save,tag:'new after failed admission'}),/Definite refusal/);
  assert.equal(requests,5);assert.equal(bodies[4].tag,'new after failed admission');
  assert.ok(bodies.every(body=>body.profile_uuid==='author'));
 }finally{for(const row of recovery.view())recovery.dismiss(row.operation_uuid);recovery.project(previous);}
});
test('an earlier overlapping group undo refuses rather than retargeting author revisions',async()=>{
 const history=createUndoHistory();history.project('owned project');
 for(const operation of ['first','second'])history.record({kind:'annotation_group',operation_uuid:operation,profile_uuid:'author',count:1857});
 assert.equal(await history.undo(async()=>({kind:'annotations',revisions:{}})),true);
 assert.equal(await history.undo(async()=>{throw Error('Original author revision changed');}),false);
 assert.equal(history.view().count,1);assert.match(history.view().message,/overlapping group edits retain their original author revisions/);
});


test('a preview cannot dispatch under a different project after it was captured',async()=>{
 const {groupAnnotationRecovery:recovery}=await import('./groupAnnotationRecovery.js');const previous=recovery.currentProject();recovery.project('initial');let writes=0;
 const request=async route=>{if(route.endsWith('preview'))return {selection_uuid:'selection',target_kind:'epoch',count:1857,profile_uuid:'author',tree_revision:revision};writes++;};
 const target=await previewTreeGroup({scope,path,revision,count:1857,profileUuid:'author',request});recovery.project('later');
 await assert.rejects(target.groupMutation.save({tag:'tag',profileUuid:'author'}),/original project/);assert.equal(writes,0);assert.equal(target.groupMutation.canPublish(),false);recovery.project(previous);
});


test('a dismissed refused operation cannot dispatch from a retained editor handle',async()=>{
 let dispatched=0;
 const target=await open(async(route,{body})=>{
  if(route.endsWith('group-preview'))return preview(body);
  dispatched++;throw refusal();
 });
 await assert.rejects(target.groupMutation.save(save),/Definite refusal/);assert.equal(dispatched,1);
 const row=recovery.view().at(-1);
 await assert.rejects(target.groupMutation.save(save),/terminal/);recovery.dismiss(row.operation_uuid);
 await assert.rejects(target.groupMutation.save(save),/terminal/);assert.equal(dispatched,1);assert.equal(recovery.view().length,0);
});

const save={tag:'tag',profileUuid:'author'};
const preview=body=>({selection_uuid:'selection',target_kind:'epoch',count:1857,profile_uuid:body.profile_uuid,tree_revision:revision});
const open=request=>previewTreeGroup({scope,path,revision,count:1857,profileUuid:'author',request});
const refusal=()=>Object.assign(Error('Definite refusal'),{status:409});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};

test('closing an unsaved preview releases once without reserving recovery',async()=>{
 const calls=[];const target=await open(async(route,{body})=>{calls.push(route);if(route.endsWith('group-preview'))return preview(body);throw Error('release unavailable');});
 assert.equal(Object.isFrozen(target.groupMutation),true);
 await target.groupMutation.release();await target.groupMutation.release();
 assert.equal(calls.filter(route=>route.endsWith('group-preview-release')).length,1);
 assert.equal(recovery.view().length,0);
});

test('pending editor save and panel retry share dispatch and one undo, with terminal release once',async()=>{
 const previous=recovery.currentProject(),previousUndo=mutationUndo.view().project;
 recovery.project('joined-save');mutationUndo.project('joined-save');
 const write=deferred(),started=deferred(),calls=[];
 const target=await open(async(route,{body})=>{
  calls.push({route,body});if(route.endsWith('group-preview'))return preview(body);
  if(route.endsWith('group-preview-release'))return {};
  started.resolve();await write.promise;return receipt(body);
 });
 try{
  const saving=target.groupMutation.save(save);await started.promise;
  const joining=recovery.retry(recovery.view()[0].operation_uuid);
  await target.groupMutation.release();await target.groupMutation.release();
  assert.equal(calls.filter(call=>call.route.endsWith('group-preview-release')).length,0);
  assert.equal(calls.filter(call=>call.route==='/annotations/group').length,1);
  write.resolve();const [first,second]=await Promise.all([saving,joining]);assert.equal(first,second);
  assert.equal(mutationUndo.view().count,1);assert.equal(recovery.view().length,0);
  assert.equal(await target.groupMutation.save(save),first);await target.groupMutation.release();
  assert.equal(calls.filter(call=>call.route==='/annotations/group').length,1);
  assert.equal(calls.filter(call=>call.route.endsWith('group-preview-release')).length,1);
  assert.equal(mutationUndo.view().count,1);
 }finally{write.resolve();recovery.project(previous);mutationUndo.project(previousUndo);}
});

test('byte admission refuses before write without attaching the oversized first tag',async()=>{
 const bodies=[];const target=await open(async(route,{body})=>{if(route.endsWith('group-preview'))return preview(body);bodies.push(body);return receipt(body);});
 await assert.rejects(target.groupMutation.save({...save,tag:'x'.repeat(4096)}),/memory admission/);
 assert.equal(bodies.length,0);assert.equal(recovery.view().length,0);
 await target.groupMutation.save(save);assert.equal(bodies.length,1);assert.equal(bodies[0].tag,'tag');
});

test('uncertain saves remain pinned and retain exact requests across saved errors and malformed receipts',async()=>{
 for(const failure of [Object.assign(Error('saved 409'),{status:409,saved:true}),Object.assign(Error('recovery unconfirmed'),{status:507,saved:true}),Error('connection lost'),{malformed:true}]){
  let first=true;const bodies=[],releases=[];
  const target=await open(async(route,{body})=>{
   if(route.endsWith('group-preview'))return preview(body);
   if(route.endsWith('group-preview-release')){releases.push(body);return {};}
   bodies.push({...body});if(first){first=false;if(failure.malformed)return {};throw failure;}return receipt(body);
  });
  await assert.rejects(target.groupMutation.save(save));await target.groupMutation.release();
  const row=recovery.view()[0];assert.equal(row.status,'unconfirmed');assert.equal(releases.length,0);
  assert.throws(()=>recovery.dismiss(row.operation_uuid),/Confirm/);
  await assert.rejects(target.groupMutation.save({...save,profileUuid:'foreign'}),/author profile/);
  await assert.rejects(target.groupMutation.save({...save,tag:'different'}),/Retry/);
  const previous=recovery.currentProject();recovery.project('foreign-project');
  await assert.rejects(recovery.retry(row.operation_uuid),/original project/);assert.equal(bodies.length,1);
  recovery.project(previous);await recovery.retry(row.operation_uuid);
  assert.deepEqual(bodies[1],bodies[0]);assert.equal(releases.length,1);assert.equal(recovery.view().length,0);
 }
});

test('project ownership is captured before a delayed preview response',async()=>{
 const previous=recovery.currentProject();recovery.project('preview-original');
 const response=deferred();let writes=0;
 try{
  const opening=open(async(route,{body})=>{if(route.endsWith('group-preview')){await response.promise;return preview(body);}writes++;return receipt(body);});
  recovery.project('preview-later');response.resolve();const target=await opening;
  assert.equal(target.groupMutation.canPublish(),false);
  await assert.rejects(target.groupMutation.save(save),/original project/);assert.equal(writes,0);
  recovery.project('preview-original');await target.groupMutation.save(save);assert.equal(writes,1);
 }finally{response.resolve();recovery.project(previous);}
});

test('a ready reservation stays pinned when undo is busy and retries the original operation',async()=>{
 const previous=recovery.currentProject(),previousUndo=mutationUndo.view().project;
 recovery.project('busy-undo');mutationUndo.project('busy-undo');
 mutationUndo.record({kind:'annotation_group',operation_uuid:'prior',profile_uuid:'author',count:1});
 const inverse=deferred();const undoing=mutationUndo.undo(async()=>{await inverse.promise;return {revisions:{}};});
 const writes=[],releases=[];
 const target=await open(async(route,{body})=>{
  if(route.endsWith('group-preview'))return preview(body);
  if(route.endsWith('group-preview-release')){releases.push(body);return {};}
  writes.push(body);return receipt(body);
 });
 try{
  await assert.rejects(target.groupMutation.save(save),/Undo is still saving/);
  const row=recovery.view()[0];assert.equal(row.status,'ready');assert.equal(writes.length,0);
  await target.groupMutation.release();assert.equal(releases.length,0);
  inverse.resolve();await undoing;await recovery.retry(row.operation_uuid);
  assert.equal(writes[0].operation_uuid,row.operation_uuid);assert.equal(writes[0].tag,'tag');
  assert.equal(releases.length,1);assert.equal(mutationUndo.view().count,1);
 }finally{inverse.resolve();await undoing;recovery.project(previous);mutationUndo.project(previousUndo);}
});

test('late save completion cannot publish or record undo in a different project',async()=>{
 const previous=recovery.currentProject(),previousUndo=mutationUndo.view().project;
 recovery.project('save-original');mutationUndo.project('save-original');
 const response=deferred(),started=deferred(),notifications=[];
 const unsubscribe=recovery.onChange(event=>notifications.push(event));
 const target=await open(async(route,{body})=>{
  if(route.endsWith('group-preview'))return preview(body);
  started.resolve();await response.promise;return receipt(body);
 });
 try{
  const saving=target.groupMutation.save(save);await started.promise;
  recovery.project('save-later');mutationUndo.project('save-later');response.resolve();
  await saving;assert.equal(target.groupMutation.canPublish(),false);
  assert.equal(mutationUndo.view().count,0);assert.equal(mutationUndo.view().pending,0);
  assert.equal(recovery.view().length,0);assert.deepEqual(notifications,[]);
 }finally{response.resolve();unsubscribe();recovery.project(previous);mutationUndo.project(previousUndo);}
});

test('four unconfirmed operations cannot be evicted by a fifth save',async()=>{
 const bodies=[],targets=[];let reject=false;
 const request=async(route,{body})=>{
  if(route.endsWith('group-preview'))return preview(body);
  bodies.push({...body});throw reject?refusal():Error('lost response');
 };
 try{
  for(let index=0;index<5;index++)targets.push(await open(request));
  for(const target of targets.slice(0,4))await assert.rejects(target.groupMutation.save(save),/lost response/);
  const original=recovery.view();assert.equal(original.length,4);
  await assert.rejects(targets[4].groupMutation.save(save),/four/);
  assert.equal(bodies.length,4);assert.deepEqual(recovery.view(),original);
  reject=true;
  for(const row of original){await assert.rejects(recovery.retry(row.operation_uuid),/Definite refusal/);recovery.dismiss(row.operation_uuid);}
 }finally{
  reject=true;
  for(const row of recovery.view()){
   if(row.status!=='rejected')await assert.rejects(recovery.retry(row.operation_uuid),/Definite refusal/);
   recovery.dismiss(row.operation_uuid);
  }
 }
});

test('definite refusal releases a closed preview once but occupies its slot until dismissed',async()=>{
 for(const status of [400,409]){
  const response=deferred(),started=deferred(),releases=[];
  const target=await open(async(route,{body})=>{
   if(route.endsWith('group-preview'))return preview(body);
   if(route.endsWith('group-preview-release')){releases.push(body);return {};}
   started.resolve();await response.promise;throw Object.assign(Error('Definite refusal'),{status});
  });
  const saving=target.groupMutation.save(save);const rejected=assert.rejects(saving,/Definite refusal/);
  await started.promise;await target.groupMutation.release();assert.equal(releases.length,0);
  response.resolve();await rejected;await target.groupMutation.release();
  assert.equal(releases.length,1);const row=recovery.view()[0];assert.equal(row.status,'rejected');
  recovery.dismiss(row.operation_uuid);assert.equal(recovery.view().length,0);
 }
});
