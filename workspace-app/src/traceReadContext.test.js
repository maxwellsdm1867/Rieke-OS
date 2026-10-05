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
