import test from 'node:test';
import assert from 'node:assert/strict';
import {startResourceRequest,visibleResourceState} from './resourceRequest.js';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
test('repeated navigation coalesces requests before server I/O begins',async()=>{
 const requested=[],shown=[];let cancel;
 for(let index=0;index<30;index++){
  cancel?.();
  cancel=startResourceRequest({path:`epoch-${index}`,delayMs:5,request:async path=>{requested.push(path);return path;},onData:data=>shown.push(data),onError:assert.fail});
 }
 await sleep(20);
 assert.deepEqual(requested,['epoch-29']);assert.deepEqual(shown,['epoch-29']);cancel();
});
test('out-of-order completion cannot paint a superseded epoch or failure',async()=>{
 const shown=[];let resolveOld,rejectOld;
 const stop=startResourceRequest({path:'old',request:()=>new Promise(resolve=>resolveOld=resolve),onData:data=>shown.push(data),onError:assert.fail});
 await sleep(0);stop();
 startResourceRequest({path:'new',request:async()=> 'new',onData:data=>shown.push(data),onError:assert.fail});
 resolveOld('old');await sleep(0);
 assert.deepEqual(shown,['new']);
 const stopError=startResourceRequest({path:'old-error',request:()=>new Promise((resolve,reject)=>rejectOld=reject),onData:assert.fail,onError:assert.fail});
 await sleep(0);stopError();rejectOld(new Error('Late failure'));await sleep(0);
});
test('current request errors still reach retry UI',async()=>{
 let message;
 startResourceRequest({path:'broken',request:async()=>{throw new Error('Unavailable');},onData:assert.fail,onError:error=>message=error.message});
 await sleep(0);assert.equal(message,'Unavailable');
});
test('warmed trace is returned in the same render while changed path, revision or reload hides stale responses',()=>{
  const state={path:'/epochs/a/trace',revision:4,nonce:0,data:{epoch_uuid:'a'},loading:false,error:null};
  const args={state,path:state.path,revision:4,nonce:0};
  assert.equal(visibleResourceState(args),state);
  for(const change of [{path:'/epochs/b/trace'},{revision:5},{nonce:1}]){
    const next=visibleResourceState({...args,...change});assert.equal(next.data,null);assert.equal(next.loading,true);
  }
  const hit={epoch_uuid:'b'},next=visibleResourceState({...args,path:'/epochs/b/trace',hit});
  assert.equal(next.data,hit);assert.equal(next.loading,false);assert.equal(next.path,'/epochs/b/trace');
});
