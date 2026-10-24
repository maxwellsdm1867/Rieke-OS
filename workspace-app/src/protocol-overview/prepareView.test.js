import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareView} from './prepareView.js';

test('concurrent consumers share one request; one departure cannot cancel the other',async()=>{
 const owner={},a=new AbortController(),b=new AbortController();let calls=0,release,transportSignal;
 const request=(_path,{signal})=>{calls++;transportSignal=signal;return new Promise(resolve=>release=resolve);};
 const first=prepareView(owner,'/overview/prepare',{request,signal:a.signal});
 const second=prepareView(owner,'/overview/prepare',{request,signal:b.signal});
 await Promise.resolve();assert.equal(calls,1);
 a.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(transportSignal.aborted,false);
 release({status:'ready'});assert.deepEqual(await second,{status:'ready'});
 await prepareView(owner,'/overview/prepare',{request:async()=>{calls++;return {};}});
 assert.equal(calls,2,'completion is not retained as authority for a later request');
});

test('last departure aborts; project owners and resources never share authority',async()=>{
 const a=new AbortController(),b=new AbortController(),signals=[];
 const request=(_path,{signal})=>{signals.push(signal);return new Promise(()=>{});};
 const first=prepareView('project-a','/overview/prepare',{request,signal:a.signal});
 const second=prepareView('project-b','/overview/prepare',{request,signal:b.signal});
 await Promise.resolve();assert.equal(signals.length,2);
 a.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(signals[0].aborted,true);assert.equal(signals[1].aborted,false);
 b.abort();await assert.rejects(second,{name:'AbortError'});assert.equal(signals[1].aborted,true);
});

test('StrictMode reconnect can rejoin without a duplicate POST; errors release the owner',async()=>{
 const owner={},a=new AbortController(),b=new AbortController();let calls=0,release,signal;
 const request=(_path,options)=>{calls++;signal=options.signal;return new Promise(resolve=>release=resolve);};
 const first=prepareView(owner,'/overview/prepare',{request,signal:a.signal});
 await Promise.resolve();a.abort();
 const second=prepareView(owner,'/overview/prepare',{request,signal:b.signal});
 await assert.rejects(first,{name:'AbortError'});assert.equal(calls,1);assert.equal(signal.aborted,false);
 release({});await second;
 await assert.rejects(prepareView(owner,'/overview/prepare',{request:async()=>{throw Error('offline');}}),/offline/);
 assert.deepEqual(await prepareView(owner,'/overview/prepare',{request:async()=>({status:'ready'})}),{status:'ready'});
});
