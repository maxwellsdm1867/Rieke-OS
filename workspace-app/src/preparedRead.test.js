import test from 'node:test';
import assert from 'node:assert/strict';
import {requestApi,PreparationRequiredError} from './api.js';
import {createOverviewCache} from './protocol-overview/overviewCache.js';
import {prepareTree} from './tree-browser/prepareTree.js';
const pending={status:'preparing',preparation:{status:'pending',resource:'tree',reason:'not prepared'}};
test('202 cannot publish as resource or cache receipt',async()=>{
 const previous=globalThis.fetch;let observed=0;
 globalThis.fetch=async()=>new Response(JSON.stringify(pending),{status:202,headers:{'Content-Type':'application/json'}});
 try{
  await assert.rejects(requestApi('/tree-pages',{onResponse:()=>observed++}),PreparationRequiredError);
  const cache=createOverviewCache(),descriptor={path:'/overview',scope:'project',revision:1};
  await assert.rejects(cache.read(descriptor,{request:requestApi}),PreparationRequiredError);
  assert.equal(cache.peek(descriptor).data,null);assert.equal(cache.peek(descriptor).preparation.status,'pending');assert.equal(observed,0);
 }finally{globalThis.fetch=previous;}
});
test('explicit preparation carries only original semantic scope',async()=>{
 const calls=[];await prepareTree({protocolId:'p',filters:{tag:'x'},splits:'cell',revision:3}, {request:async(...args)=>calls.push(args)});
 assert.deepEqual(calls, [['/tree-pages/prepare',{method:'POST',body:{protocol_uuid:'p',filters:{tag:'x'},splits:'cell'},signal:undefined}]]);
});
test('cancelled or superseded preparation cannot renew a tree',async()=>{
 for(const cancel of [true,false]){
  const controller=new AbortController();let calls=0;
  await assert.rejects(prepareTree({predicate:{all:[]}},{signal:controller.signal,isCurrent:()=>cancel,request:async()=>{calls++;if(cancel)controller.abort();}}),{name:'AbortError'});
  assert.equal(calls,1);
 }
});
test('pending preparation never retries automatically',async()=>{
 let calls=0;await assert.rejects(prepareTree({},{request:async()=>{calls++;throw new PreparationRequiredError(pending);}}),PreparationRequiredError);assert.equal(calls,1);
});
