import test from 'node:test';
import assert from 'node:assert/strict';
import React,{StrictMode} from 'react';
import Renderer,{act} from 'react-test-renderer';
import useSourceMerge from './useSourceMerge.js';
const options={candidate_revision_uuid:'c',source_sha256:'s'};
for(const scenario of ['retired-preview','moved-after-submit','unmounted-after-submit'])test(`direct source owner: ${scenario}`,async()=>{
 let api,view,release,started,submits=0;const submitted=new Promise(resolve=>started=resolve),calls=[];
 const request=async(path,params={})=>{
  if(path.endsWith('/context'))return {candidate_revision_uuid:'c',protocol:{definition:{protocol_uuid:'p'}},source_additive_accept:true,actor:'a',candidate_scope_revision:'scope',draft:{draft_version:0}};
  if(path.endsWith('/preview')){if(scenario==='retired-preview'){started();await new Promise(r=>release=r);}return {mode:'source',source_sha256:'s',candidate_scope_revision:'scope',expected_draft_version:0,preview_sha256:'seal',expected_binding_version:1,expected_query_revision:'q',selected_epoch_count:1691,accepted_epoch_count:1691,already_present_epoch_count:0,retained_epoch_count:2,next_epoch_count:1693,accepted_cell_count:1};}
  submits++;started();await new Promise(r=>release=r);return {...params.body,protocol_uuid:'p',candidate_revision_uuid:'c',candidate_scope_revision:'scope',actor:'a',binding:{revision_uuid:'main',version:2},event_uuid:'event'};
 };
 const persist=async()=>{};const onAccepted=(...args)=>calls.push(args);
 function Probe({ownerKey}){api=useSourceMerge({projectId:'project',request,persist,ownerKey,onAccepted});return null;}
 const render=async ownerKey=>act(()=>{const node=React.createElement(StrictMode,null,React.createElement(Probe,{ownerKey}));if(view)view.update(node);else view=Renderer.create(node);});
 try{
  await render('A');let pending;await act(()=>{pending=api.start('p',options);pending.catch(()=>{});});await submitted;
  if(scenario==='unmounted-after-submit'){await act(()=>view.unmount());view=null;}
  else{await render('B');if(scenario==='retired-preview')await render('A');}
  if(scenario==='retired-preview'){await act(async()=>{release();await assert.rejects(pending,/workspace changed/);});assert.equal(submits,0);assert.deepEqual(calls,[]);}
  else{await act(async()=>{release();await pending;});assert.equal(submits,1);assert.deepEqual(calls.map(call=>call.slice(0,2)),scenario==='moved-after-submit'?[['p',{navigate:false}]]:[]);
   for(const [,,receipt] of calls)assert.deepEqual([receipt.mode,receipt.source_sha256,receipt.candidate_revision_uuid,receipt.event_uuid],['source','s','c','event'],'completion carries its verified receipt');}
 }finally{release?.();if(view)await act(()=>view.unmount());}
});

for(const scenario of ['retired-before-submit','moved-after-submit','unmounted-after-submit'])test(`Finish review owner: ${scenario}`,async()=>{
 let api,view,release,started,finishes=0,receipt;const held=new Promise(resolve=>started=resolve),reviewed=[],accepted=[];
 const context={actor:'a',candidate_revision_uuid:'union',protocol:{definition:{protocol_uuid:'p'}},candidate_scope_revision:'scope',draft:{draft_version:1}};
 const request=async(path,options={})=>{
  if(path.endsWith('/prepare'))return {contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prep',candidate_revision_uuid:'union',candidate_scope_revision:'scope',queue_revision:'q',root:'/protocols/p/workbench/candidates/union',context};
  if(path==='/annotation-profiles')return {selected_profile_uuid:'a'};
  assert.ok(path.endsWith('/finish'));finishes++;started();await new Promise(resolve=>release=resolve);
  receipt={kind:'workbench_review_completion',operation_uuid:options.body.operation_uuid,protocol_uuid:'p',candidate_revision_uuid:'union',actor:'a',expected_draft_version:2,left_out_epoch_count:2};
  return {...context,draft:{draft_version:2},review_completion:receipt};
 };
 const persist=async()=>{if(scenario==='retired-before-submit'){started();await new Promise(resolve=>release=resolve);}};
 function Probe({ownerKey}){api=useSourceMerge({projectId:'project',request,persist,ownerKey,onAccepted:(...args)=>accepted.push(args),onReviewed:(...args)=>reviewed.push(args)});return null;}
 const render=async ownerKey=>act(()=>{const node=React.createElement(StrictMode,null,React.createElement(Probe,{ownerKey}));if(view)view.update(node);else view=Renderer.create(node);});
 try{
  await render('A');let pending;await act(()=>{pending=api.finish('p',{queue_revision:'q'});pending.catch(()=>{});});await held;
  if(scenario==='unmounted-after-submit'){await act(()=>view.unmount());view=null;}else{await render('B');if(scenario==='retired-before-submit')await render('A');}
  await act(async()=>{release();if(scenario==='retired-before-submit')await assert.rejects(pending,/workspace changed/);else assert.equal(await pending,true);});
  assert.equal(finishes,scenario==='retired-before-submit'?0:1);assert.deepEqual(accepted,[]);assert.deepEqual(reviewed,scenario==='moved-after-submit'?[['p',receipt]]:[]);
 }finally{release?.();if(view)await act(()=>view.unmount());}
});
