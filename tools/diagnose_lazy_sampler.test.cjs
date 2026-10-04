const {test}=require('node:test'),assert=require('node:assert/strict');
const {startSampler}=require('./diagnose_lazy_sampler.cjs');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
test('stop drains in-flight work and no old timer enters the next variant',async()=>{
 let release,oldCalls=0,done=false;const gate=new Promise(r=>release=r);
 const stop=startSampler(async()=>{oldCalls++;await gate},1);await wait(2);
 const pending=stop().then(()=>{done=true});await wait(2);assert.equal(done,false);release();await pending;
 let nextCalls=0;const next=startSampler(async()=>{nextCalls++},2);await wait(12);await next();
 assert.equal(oldCalls,1);assert.ok(nextCalls>=1);const seen=nextCalls;await wait(5);assert.equal(nextCalls,seen);
});
