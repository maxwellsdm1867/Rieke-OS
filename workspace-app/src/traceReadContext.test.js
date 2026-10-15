import test from 'node:test';
import assert from 'node:assert/strict';
import {traceRequestPath,traceCacheRevision} from './traces/traceReadContext.js';
const root='/protocols/protocol-a/workbench/candidates/revision-a';
const context={root,candidate_scope_revision:'exact scope + / & = ? # token'};
const stream={uuid:'response-a'},window={start:123,count:800};
test('normal trace URL and cache revision remain unchanged',()=>{
 assert.equal(traceRequestPath('epoch-a',stream,window),'/epochs/epoch-a/trace?stream_uuid=response-a&start=123&count=800');
 assert.equal(traceCacheRevision(7),7);
 assert.equal(traceRequestPath('epoch-a',null,window),null);
});
test('candidate trace forwards the exact root and opaque token alongside full-rate window coordinates',()=>{
 const url=new URL(traceRequestPath('epoch-a',stream,window,context),'http://fixture');
 assert.equal(url.pathname,root+'/epochs/epoch-a/trace');
 assert.equal(url.searchParams.get('candidate_scope_revision'),context.candidate_scope_revision);
 assert.equal(url.searchParams.get('stream_uuid'),stream.uuid);assert.equal(url.searchParams.get('start'),'123');assert.equal(url.searchParams.get('count'),'800');
});
test('same epoch/window is isolated across global authority, candidate roots, tokens and data revisions',()=>{
 const otherRoot={...context,root:root.replace('revision-a','revision-b')};
 const otherToken={...context,candidate_scope_revision:'other exact token'};
 const paths=[null,context,otherRoot,otherToken].map(scope=>traceRequestPath('epoch-a',stream,window,scope));
 assert.equal(new Set(paths).size,4);
 const identities=[traceCacheRevision(7),traceCacheRevision(7,context),traceCacheRevision(7,otherRoot),traceCacheRevision(7,otherToken),traceCacheRevision(8,context)];
 assert.equal(new Set(identities).size,5);
});
test('incomplete or noncandidate authority fails closed rather than using a global trace',()=>{
 for(const invalid of [{},{root},{root,candidate_scope_revision:''},{root,candidate_scope_revision:1},{root:'/epochs/epoch-a',candidate_scope_revision:'token'}])assert.throws(()=>traceRequestPath('epoch-a',stream,window,invalid),/Frozen candidate context is unavailable/);
});

const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const display={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
const descriptor={uuid:uid(7),sample_count:3,sample_rate:10000,units:'pA'};
const {traceResponseMatches,selectPreparedTraceContext}=await import('./traces/traceReadContext.js');
const {readWholeTrace}=await import('./traces/readWholeTrace.js');
test('prepared display routes strictly and ignores annotation revision only',()=>{
 assert.equal(traceRequestPath(uid(6),descriptor,{start:0,count:3},display),`/trace-views/${uid(1)}/epochs/${uid(6)}/trace?stream_uuid=${uid(7)}&start=0&count=3`);
 assert.equal(traceCacheRevision(1,display),traceCacheRevision(999,display));
 for(const key of ['token','project_uuid','publication_revision','protocol_uuid','candidate_revision_uuid','membership_sha256'])assert.notEqual(traceCacheRevision(1,display),traceCacheRevision(1,{...display,[key]:key==='membership_sha256'?'b'.repeat(64):uid(100)}));
 for(const bad of [{...display,token:'bad'},{...display,selection_token:uid(8)},{...display,candidate_scope_revision:'scope'},{...display,view_kind:'other'},{...display,membership_sha256:'A'.repeat(64)}])assert.throws(()=>traceRequestPath(uid(6),descriptor,{start:0,count:3},bad),/Prepared trace display/);
});
test('prepared echo must be exact and cannot claim current candidate authority',()=>{
 assert(traceResponseMatches({read_context:{...display}},display));
 for(const body of [{},{read_context:{...display,token:uid(9)}},{read_context:display,candidate_scope_revision:'scope'},{read_context:{...display,extra:true}}])assert.equal(traceResponseMatches(body,display),false);
 assert.equal(traceResponseMatches({read_context:display},null),false);
});
test('selected display waits for its own page and fences pending tokens and publications',()=>{
 const args={context:display,projectUuid:display.project_uuid,protocolUuid:display.protocol_uuid,candidateUuid:display.candidate_revision_uuid};
 assert.equal(selectPreparedTraceContext(args),display);assert.equal(selectPreparedTraceContext({...args,selected:true}),null);
 assert.equal(selectPreparedTraceContext({...args,page:{trace_read_context:{...display,token:uid(9)}}}),null);
 const selected={...display,token:uid(10),view_kind:'workbench_selected',membership_sha256:'c'.repeat(64)};
 assert.equal(selectPreparedTraceContext({...args,selected:true,page:{trace_read_context:selected}}),selected);
 assert.throws(()=>selectPreparedTraceContext({...args,selected:true,page:{trace_read_context:display}}),/Prepared trace display/);
 assert.throws(()=>selectPreparedTraceContext({...args,page:{trace_read_context:{...display,project_uuid:uid(10)}}}),/Prepared trace display/);
 assert.equal(selectPreparedTraceContext({...args,selected:true,page:{trace_read_context:{...selected,publication_revision:uid(10)}}}),null);
 assert.equal(selectPreparedTraceContext({page:{},selected:true}),undefined);
});
test('prepared whole reads reject wrong source, rate, units and capability without fallback',async()=>{
 const header={epoch_uuid:uid(6),stream_uuid:descriptor.uuid,start:0,count:3,total_samples:3,sample_rate:10000,units:'pA',source_sha256:'b'.repeat(64),decimated:false,read_context:display,values:[1,2,3]};
 for(const change of [{},{source_sha256:'c'.repeat(64)},{sample_rate:20},{units:'mV'},{read_context:{...display,token:uid(9)}},{candidate_scope_revision:'scope'}]){
  const calls=[];const promise=readWholeTrace({request:async path=>{calls.push(path);return {...header,...change};},epochUuid:uid(6),stream:descriptor,readContext:display,sourceSha256:header.source_sha256});
  if(Object.keys(change).length)await assert.rejects(promise,/does not match/);else assert.deepEqual((await promise).values,[1,2,3]);
  assert.equal(calls.length,1);assert(calls[0].startsWith('/trace-views/'));
 }
});
test('prepared batch validates the envelope and every window capability independently',async()=>{
 const stream={...descriptor,sample_count:200000},source='b'.repeat(64),header={epoch_uuid:uid(6),stream_uuid:descriptor.uuid,total_samples:stream.sample_count,sample_rate:stream.sample_rate,units:stream.units,source_sha256:source,decimated:false,read_context:display};
 for(const bad of ['none','envelope','window']){
  const windows=[0,100000].map(start=>({...header,start,count:100000,values:new Float64Array(100000)}));
  const response={...header,start:0,count:200000,windows};if(bad==='envelope')response.read_context={...display,token:uid(9)};if(bad==='window')windows[1].read_context={...display,membership_sha256:'c'.repeat(64)};
  const promise=readWholeTrace({request:async()=>response,epochUuid:uid(6),stream,readContext:display,sourceSha256:source,maxChunkSamples:100000});
  if(bad==='none')assert.equal((await promise).values.length,200000);else await assert.rejects(promise,/does not match/);
 }
});
