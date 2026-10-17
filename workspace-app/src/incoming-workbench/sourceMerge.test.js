import test from 'node:test';
import assert from 'node:assert/strict';
import {createSourceMerge} from './sourceMerge.js';
function harness({lost=false,persistFail=false}={}){
 let owner={},saved=null,actor='actor',posts=[],accepts=0,commits=0,receipt;
 const request=async(path,options={})=>{
  if(path==='/annotation-profiles')return {selected_profile_uuid:actor,profiles:[{profile_uuid:'actor',display_name:'Original author'}]};
  if(path.includes('/receipts/')){if(!receipt)throw Error('No receipt yet');return receipt;}
  if(!options.method)return {candidate_revision_uuid:'candidate',protocol:{definition:{protocol_uuid:'protocol'}},source_additive_accept:true,actor:'actor',candidate_scope_revision:'scope',draft:{draft_version:7,decisions_truncated:true,decisions_total:300,decisions:[]}};
  posts.push({path,body:structuredClone(options.body)});
  if(path.endsWith('/preview'))return {mode:'source',source_sha256:'source',candidate_scope_revision:'scope',expected_draft_version:7,preview_sha256:'sealed',expected_binding_version:2,expected_query_revision:'query',selected_epoch_count:1691,accepted_epoch_count:1691,already_present_epoch_count:0,retained_epoch_count:540,next_epoch_count:2231,accepted_cell_count:3};
  accepts++;
  assert.deepEqual(saved.body,options.body,'replay body was persisted before submission');
  if(!receipt){commits++;receipt={...options.body,candidate_scope_revision:'scope',protocol_uuid:'protocol',candidate_revision_uuid:'candidate',actor:'actor',binding:{revision_uuid:'main',version:3},event_uuid:'event'};}
  if(lost){lost=false;throw Error('lost reply');}return receipt;
 };
 const controller=createSourceMerge({projectId:'project',request,owner:()=>owner,persist:async()=>{if(persistFail)throw Error('save failed');saved=structuredClone(controller.snapshot());}});
 return {controller,request,posts,get saved(){return saved},get commits(){return commits},get accepts(){return accepts},changeOwner(){owner={}},setActor(value){actor=value},accept:(protocol='protocol')=>controller.start(protocol,{candidate_revision_uuid:'candidate',source_sha256:'source'})};
}
test('held source uses server preview and accept above 1000, without selecting or patching a draft',async()=>{const h=harness();const result=await h.accept();assert.equal(result.protocolId,'protocol');assert.deepEqual(h.posts.map(p=>p.path.split('/').at(-1)),['preview','accept']);assert.equal(h.posts[0].body.mode,'source');assert.equal(h.controller.snapshot(),null);assert.equal(h.commits,1);});
test('lost acceptance response retains exact operation and recovers receipt without a second merge',async()=>{const h=harness({lost:true});await assert.rejects(h.accept(),/may have completed/);const saved=structuredClone(h.controller.snapshot());assert.equal(saved.actor,'actor');assert.equal(h.commits,1);await assert.rejects(h.accept(),/recover/);h.setActor('other');await assert.rejects(h.controller.recover(),/Original author/);assert.equal(h.accepts,1);h.setActor('actor');await h.controller.recover();assert.deepEqual(h.posts.filter(p=>p.path.endsWith('/accept')).map(p=>p.body),[saved.body]);assert.equal(h.commits,1);});
test('restored recovery is inert until explicitly requested',async()=>{const h=harness({lost:true});await assert.rejects(h.accept());const saved=h.controller.snapshot(),next=createSourceMerge({projectId:'project',request:h.request});next.restore(saved);next.restore(saved);assert.equal(h.accepts,1);await next.recover();assert.equal(h.accepts,1);assert.equal(h.commits,1);});
test('failed persistence prevents acceptance',async()=>{const h=harness({persistFail:true});await assert.rejects(h.accept(),/save failed/);assert.equal(h.accepts,0);assert.equal(h.controller.snapshot(),null);});
test('owner change before acceptance retires held consent',async()=>{const h=harness();const request=async(path,options)=>{const value=await h.request(path,options);if(path.endsWith('/preview'))h.changeOwner();return value;};let owner='initial';const controller=createSourceMerge({projectId:'project',request:async(path,options)=>{const v=await request(path,options);if(path.endsWith('/preview'))owner='retired';return v;},owner:()=>owner});await assert.rejects(controller.start('protocol',{candidate_revision_uuid:'candidate',source_sha256:'source'}),/workspace changed/);assert.equal(h.accepts,0);});

test('navigation during persistence cannot turn a restored prepared operation into new consent',async()=>{
 const h=harness();let owner={},saved;
 const controller=createSourceMerge({projectId:'project',request:h.request,owner:()=>owner,persist:async()=>{saved=structuredClone(controller.snapshot());owner={};}});
 await assert.rejects(controller.start('protocol',{candidate_revision_uuid:'candidate',source_sha256:'source'}),/workspace changed/);
 assert.equal(h.accepts,0);
 const restored=createSourceMerge({projectId:'project',request:h.request});restored.restore(saved);
 await assert.rejects(restored.recover());assert.equal(h.accepts,0);assert.deepEqual(restored.snapshot(),saved);
});

test('a separately consented retry uses the original operation without a second commit',async()=>{
 const h=harness({lost:true});await assert.rejects(h.accept());const original=structuredClone(h.controller.snapshot());
 await h.controller.recover({retry:true});assert.equal(h.accepts,2);assert.equal(h.commits,1);
 assert.deepEqual(h.posts.filter(p=>p.path.endsWith('/accept')).map(p=>p.body),[original.body,original.body]);
});
test('receipt lookup accepts the backend default author when no selected author is set',async()=>{
 const h=harness({lost:true});await assert.rejects(h.accept());
 const restored=createSourceMerge({projectId:'project',request:(path,options)=>path==='/annotation-profiles'?Promise.resolve({default_profile_uuid:'actor'}):h.request(path,options)});
 restored.restore(h.controller.snapshot());await restored.recover();assert.equal(h.accepts,1);
});

function mergeAllHarness({persist}={}){
 const posts=[];
 const request=async(path,options={})=>{
  posts.push({path,method:options.method||'GET',body:structuredClone(options.body)});
  if(path==='/protocols/protocol/workbench/merge-all')return {mode:'all',operation_uuid:options.body.operation_uuid,protocol_uuid:'protocol',candidate_revision_uuid:'union',actor:'actor',accepted_epoch_count:755,binding:{revision_uuid:'main',version:3},event_uuid:'event'};
  if(path.startsWith('/protocols/protocol/workbench/receipts/'))return {mode:'all',operation_uuid:decodeURIComponent(path.split('/').at(-1)),protocol_uuid:'protocol',binding:{revision_uuid:'main',version:3},event_uuid:'event'};
  throw Error(`unexpected ${path}`);
 };
 const controller=createSourceMerge({projectId:'project',request,persist});
 return {controller,posts};
}
test('merge all is one request fenced by the queue revision the scientist saw',async()=>{
 let saved=null;const h=mergeAllHarness({persist:async()=>{saved=structuredClone(h.controller.snapshot());return {viewSaved:true,notice:''};}});
 const result=await h.controller.startAll('protocol',{queue_revision:'q1'});
 assert.deepEqual(h.posts.map(p=>[p.method,p.path]),[['POST','/protocols/protocol/workbench/merge-all']]);
 const body=h.posts[0].body;
 assert.deepEqual({...body,operation_uuid:'op'},{expected_queue_revision:'q1',operation_uuid:'op'});
 assert.equal(saved.body.operation_uuid,body.operation_uuid,'the replayable operation was saved before submission');
 assert.equal(saved.body.expected_queue_revision,'q1');
 assert.equal(result.receipt.mode,'all');assert.equal(result.receipt.event_uuid,'event');assert.equal(h.controller.snapshot(),null);
});
test('merge all: a view that could not be saved does not block submission and leaves a quiet notice',async()=>{
 const h=mergeAllHarness({persist:async()=>({viewSaved:false,notice:'The latest view could not be saved; the merge was still submitted.'})});
 await h.controller.startAll('protocol',{queue_revision:'q1'});
 assert.equal(h.posts.filter(p=>p.path.endsWith('/merge-all')).length,1);
 assert.equal(h.controller.state.phase,'idle');assert.match(h.controller.state.notice,/could not be saved/);
});
test('merge all: an unconfirmed accepted write still refuses submission',async()=>{
 const h=mergeAllHarness({persist:async()=>{throw Error('Some accepted changes were not confirmed.');}});
 await assert.rejects(h.controller.startAll('protocol',{queue_revision:'q1'}),/not confirmed/);
 assert.equal(h.posts.filter(p=>p.path.endsWith('/merge-all')).length,0);assert.equal(h.controller.snapshot(),null);
});
test('a saved merge-all operation restores and recovers its receipt by operation',async()=>{
 const h=mergeAllHarness({persist:async()=>({viewSaved:true})});
 const op={projectId:'project',protocolId:'protocol',mergeAll:true,body:{mode:'merge_all',expected_queue_revision:'q1',operation_uuid:'op-1'}};
 h.controller.restore(op);assert.equal(h.controller.state.phase,'unconfirmed');
 const result=await h.controller.recover();
 assert.deepEqual(h.posts.map(p=>[p.method,p.path]),[['GET','/protocols/protocol/workbench/receipts/op-1']]);
 assert.equal(result.receipt.operation_uuid,'op-1');assert.equal(h.controller.snapshot(),null);
 assert.throws(()=>mergeAllHarness().controller.restore({...op,body:{...op.body,expected_queue_revision:''}}),/invalid/);
});
test('merge all restores and validates its saved recovery identity',async()=>{
 const h=mergeAllHarness({persist:async()=>({viewSaved:true})});
 const op={projectId:'project',protocolId:'protocol',candidateId:'union',actor:'actor',body:{mode:'all',operation_uuid:'op',preview_sha256:'p',expected_candidate_scope_revision:'s',expected_query_revision:'q',expected_draft_version:1,expected_binding_version:1}};
 h.controller.restore(op);assert.equal(h.controller.state.phase,'unconfirmed');
 const other=mergeAllHarness().controller;assert.throws(()=>other.restore({...op,body:{...op.body,source_sha256:'x'}}),/invalid/);
});
