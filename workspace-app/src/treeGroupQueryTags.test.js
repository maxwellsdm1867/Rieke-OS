import test from 'node:test';
import assert from 'node:assert/strict';
import {groupQueryScope,previewTreeGroup,confirmGroupReceipt,releaseGroupPreview} from './treeGroupQueryTags.js';
import {persistUndo} from './useMutationUndo.js';
import {createUndoHistory} from './mutationUndo.js';
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
