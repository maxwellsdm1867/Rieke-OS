import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveTreeGroup,verifyTreeGroup} from './treeGroupTargets.js';
import {bulkAnnotationChange} from './annotationTags.js';

const revision='a'.repeat(64),path=['b'.repeat(64)],scope={protocolId:'protocol',filters:{metadata_predicate:{all:[]}},splits:'date,cell'};
function leaf({path:currentPath=path,offset=0,rows,total=rows.length,count=total,rev=revision}){
  return {revision:rev,path:currentPath,offset,limit:60,kind:'epochs',total,selection:{count},has_more:offset+60<total,epochs:rows.slice(offset,offset+60)};
}
const rows=count=>Array.from({length:count},(_,i)=>({epoch_uuid:`epoch-${i}`,cell_uuid:'cell'}));
function requestFor(data,seen=[]){return async(_,options)=>{const body=options.body;seen.push(body);return body.path.length?leaf({path:body.path,offset:body.offset,rows:data}):{revision};};}
test('collects every cross-page target with the same protocol, predicate and structural path',async()=>{
  const seen=[],data=rows(137);
  const target=await resolveTreeGroup({scope,path,revision,count:137,request:requestFor(data,seen)});
  assert.equal(target.count,137);assert.deepEqual(target.ids,data.map(row=>row.epoch_uuid));assert.ok(Object.isFrozen(target.ids));
  assert.deepEqual(seen.map(body=>body.offset),[0,60,120,0]);
  for(const body of seen){assert.equal(body.revision,revision);assert.equal(body.protocol_uuid,'protocol');assert.deepEqual(body.filters,scope.filters);}
});
test('visits every branch page and leaf, preserving opaque joint/missing keys',async()=>{
  const branches=Array.from({length:61},(_,i)=>({path:[...path,String(i).padStart(64,'0')]}));
  const request=async(_,options)=>{
    const b=options.body;if(!b.path.length)return {revision};
    if(b.path.length===1)return {revision,path,offset:b.offset,limit:60,kind:'branches',total:61,selection:{count:61},has_more:b.offset+60<61,branches:branches.slice(b.offset,b.offset+60)};
    return leaf({path:b.path,rows:[{epoch_uuid:b.path[1],cell_uuid:'cell'}]});
  };
  const target=await resolveTreeGroup({scope,path,revision,count:61,request});assert.equal(target.ids.length,61);
});
test('refuses 1001 before any request and accepts exactly 1000',async()=>{
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:1001,request:()=>{assert.fail('must not request oversized group');}}),/at most 1,000/);
  const target=await resolveTreeGroup({scope,path,revision,count:1000,request:requestFor(rows(1000))});assert.equal(target.ids.length,1000);
});
test('count mismatch, missing rows and duplicate identities fail without publishing targets',async()=>{
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:3,request:requestFor(rows(2))}),/count changed/);
  const duplicate=rows(2);duplicate[1]=duplicate[0];
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:2,request:requestFor(duplicate)}),/invalid or excessive/);
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:2,request:async()=>({...leaf({rows:rows(2)}),epochs:rows(1)})}),/complete group/);
});
test('stale continuation and stale final root revision refuse',async()=>{
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:1,request:async()=>leaf({rows:rows(1),rev:'c'.repeat(64)})}),/Tree changed/);
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:1,request:async(_,o)=>o.body.path.length?leaf({rows:rows(1)}):{revision:'c'.repeat(64)}}),/Tree changed/);
});
test('cancellation stops before any next page and does not publish partial IDs',async()=>{
  const controller=new AbortController();let calls=0;
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:61,signal:controller.signal,request:async()=>{calls++;controller.abort();return leaf({rows:rows(61)});}}),{name:'AbortError'});
  assert.equal(calls,1);
});
test('actual cell choice resolves one verified identity even when matching group exceeds limit',async()=>{
  const target=await resolveTreeGroup({scope,path,revision,count:5000,cellUuid:'cell',request:async(_,o)=>o.body.path.length?leaf({rows:rows(60),total:5000}):{revision}});
  assert.equal(target.kind,'cell');assert.equal(target.count,1);assert.equal(target.epoch.cell_uuid,'cell');
  await assert.rejects(resolveTreeGroup({scope,path,revision,count:1,cellUuid:'other',request:requestFor(rows(1))}),/cell identity/);
});
test('unsupported candidate context refuses before global tree request',async()=>{
  const request=()=>assert.fail('candidate must not fall back to global route');
  await assert.rejects(resolveTreeGroup({scope:{...scope,readContext:{root:'/candidate'}},path,revision,count:1,request}),/Incoming Workbench/);
});
test('tag-induced membership changes cannot retarget frozen IDs; pre-submit check refuses stale scope',async()=>{
  const target=await resolveTreeGroup({scope,path,revision,count:2,request:requestFor(rows(2))});
  await assert.rejects(verifyTreeGroup(scope,revision,async()=>({revision:'d'.repeat(64)})),/Tree changed/);
  assert.deepEqual(target.ids,['epoch-0','epoch-1']);
});
test('native bulk body covers every initial target and only the selected actor revision',async()=>{
  const target=await resolveTreeGroup({scope,path,revision,count:2,request:requestFor(rows(2))});
  const read={targets:Object.fromEntries(target.ids.map(id=>[id,{target_kind:'epoch',target_uuid:id,revisions:{alice:3,bob:19}}]))};
  const body=bulkAnnotationChange({targetUuids:target.ids,profileUuid:'alice',tag:'reviewed',read});
  assert.equal(body.profile_uuid,'alice');assert.deepEqual(body.expected_revisions,{'epoch-0':3,'epoch-1':3});assert.deepEqual(body.target_uuids,target.ids);
  delete read.targets['epoch-1'];assert.throws(()=>bulkAnnotationChange({targetUuids:target.ids,profileUuid:'alice',tag:'reviewed',read}),/could not be verified/);
});
