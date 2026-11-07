import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useState} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const recording=name=>({name,size:32});
async function harness(t,{integrated=true,initialMonitor}={}){
 const key=`__importHookRecovery${Math.random().toString(36).slice(2)}`,reads=[],uploads=[],completions=[];
 globalThis[key]={request(path,options){assert.equal(path,'/jobs');const operation=deferred();reads.push({...operation,signal:options.signal});return operation.promise;},upload(file){const operation=deferred();uploads.push({...operation,file});return operation.promise;}};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',plugins:[{name:'owned-import-adapters',enforce:'pre',resolveId(id){if(id==='../api.js')return '\0import-test-api';if(id==='./uploadRecording.js')return '\0import-test-upload';},load(id){if(id==='\0import-test-api')return `export const api=(...args)=>globalThis[${JSON.stringify(key)}].request(...args);`;if(id==='\0import-test-upload')return `export const uploadRecording=(...args)=>globalThis[${JSON.stringify(key)}].upload(...args);`;}}]});
 const {default:useMonitor}=await server.ssrLoadModule('/src/recording-import/useImportMonitor.js');
 const {default:useQueue}=await server.ssrLoadModule('/src/recording-import/useImportQueue.js');
 let state,renderer,revision=0,monitor=initialMonitor;
 function Harness(){const [transfer,setTransfer]=useState(null);const live=useMonitor(revision,job=>completions.push(job),!!transfer,integrated);const queue=useQueue(integrated?live:monitor,setTransfer,()=>{});state={monitor:live,queue,transfer};return null;}
 t.mock.timers.enable({apis:['setTimeout']});
 const render=()=>act(async()=>{if(renderer)renderer.update(React.createElement(Harness));else renderer=TestRenderer.create(React.createElement(Harness));});
 t.after(async()=>{await act(()=>renderer?.unmount());t.mock.timers.reset();await server.close();delete globalThis[key];});await render();
 return {reads,uploads,completions,get state(){return state;},tick:ms=>act(async()=>{t.mock.timers.tick(ms);}),enqueue:files=>act(async()=>{state.queue.enqueue(files);}),resolve:(operation,value)=>act(async()=>{operation.resolve(value);}),reject:(operation,error)=>act(async()=>{operation.reject(error);}),replace:async()=>{revision++;await render();},updateMonitor:async value=>{monitor=value;await render();}};
}

test('queued files recover from a monitor transport that ignores abort without retrying an upload',async t=>{
 const h=await harness(t),history={jobs:[{job_uuid:'old',status:'complete'}]};await h.resolve(h.reads[0],history);
 assert.equal(h.completions.length,0,'old history is not a new completion');
 await h.enqueue([recording('next.h5')]);assert.equal(h.reads.length,2,'enqueue initiates a fresh status read');assert.equal(h.uploads.length,0,'old history cannot admit a new upload');assert.equal(h.state.queue.remaining,1);assert.match(h.state.queue.status,/Checking current jobs/);
 await h.tick(8000);assert.equal(h.reads[1].signal.aborted,true);assert.equal(h.state.monitor.loading,false,'timeout settles state although transport remains pending');assert.equal(h.state.monitor.data,history);assert.match(h.state.monitor.error,/8 seconds/);assert.match(h.state.queue.status,/unable to check/);assert.equal(h.uploads.length,0);
 await h.tick(10000);assert.equal(h.reads.length,3,'automatic GET retry continues after timeout');
 const fresh={jobs:[{job_uuid:'old',status:'complete'}]};await h.resolve(h.reads[2],fresh);assert.equal(h.completions.length,1,'recovered monitor refreshes the project once');assert.equal(h.uploads.length,1);assert.equal(h.uploads[0].file.name,'next.h5');
 await h.resolve(h.reads[1],{jobs:[{job_uuid:'stale',status:'validating'}]});assert.equal(h.state.monitor.data,fresh,'late timed-out response cannot overwrite recovery');
 await h.reject(h.uploads[0],new Error('Acceptance is unconfirmed'));assert.match(h.state.queue.error,/Acceptance is unconfirmed/);
 await h.resolve(h.reads.at(-1),{jobs:[]});await h.tick(2500);assert.equal(h.uploads.length,1,'uncertain POST is never automatically retried');
});

test('replacement retires monitor reads without stale errors or timeout interference',async t=>{
 const h=await harness(t);await h.tick(4000);await h.replace();assert.equal(h.reads[0].signal.aborted,true);assert.equal(h.reads.length,2);
 await h.tick(4000);assert.equal(h.state.monitor.loading,true,'retired timeout cannot end the replacement request');await h.reject(h.reads[0],new Error('obsolete network failure'));assert.equal(h.state.monitor.error,null);
 const fresh={jobs:[]};await h.resolve(h.reads[1],fresh);assert.equal(h.state.monitor.loading,false);assert.equal(h.state.monitor.data,fresh);await h.tick(4000);assert.equal(h.state.monitor.error,null);
});

test('queue admits only fresh jobs, serializes accepted imports, and stops the remaining batch on failure',async t=>{
 let reloads=0,monitor={data:{jobs:[]},loading:false,error:null,reload:()=>reloads++};const h=await harness(t,{integrated:false,initialMonitor:monitor});
 await h.enqueue([recording('one.h5'),recording('two.h5'),recording('three.h5')]);assert.equal(reloads,1);assert.equal(h.uploads.length,0);
 await h.updateMonitor({...monitor});assert.equal(h.uploads.length,0,'old data rerender is not a fresh read');monitor={...monitor,data:{jobs:[]}};await h.updateMonitor(monitor);assert.equal(h.uploads.length,1);assert.equal(h.state.queue.remaining,2);
 await h.resolve(h.uploads[0],{job_uuid:'one'});assert.equal(h.uploads.length,1,'acceptance alone cannot advance the queue');monitor={...monitor,data:{jobs:[{job_uuid:'one',status:'validating'}]}};await h.updateMonitor(monitor);assert.equal(h.uploads.length,1);
 monitor={...monitor,data:{jobs:[{job_uuid:'one',status:'complete'}]}};await h.updateMonitor(monitor);assert.equal(h.uploads.length,2);assert.equal(h.uploads[1].file.name,'two.h5');await h.resolve(h.uploads[1],{job_uuid:'two'});
 monitor={...monitor,data:{jobs:[{job_uuid:'two',status:'failed'},{job_uuid:'one',status:'complete'}]}};await h.updateMonitor(monitor);assert.equal(h.uploads.length,2);assert.equal(h.state.queue.remaining,0);assert.equal(h.state.queue.busy,false);assert.match(h.state.queue.error,/Import stopped/);
});


test('queue refuses missing or failed job observations until a confirmed fresh read arrives',async t=>{
 let monitor={data:null,loading:false,error:null,reload(){}};const h=await harness(t,{integrated:false,initialMonitor:monitor});
 await h.enqueue([recording('one.h5')]);assert.equal(h.uploads.length,0);
 monitor={...monitor,data:{jobs:[]},error:'offline'};await h.updateMonitor(monitor);assert.equal(h.uploads.length,0);assert.match(h.state.queue.status,/unable to check/);
 monitor={...monitor,loading:true,error:null};await h.updateMonitor(monitor);assert.equal(h.uploads.length,0);
 monitor={...monitor,loading:false,data:{jobs:[]}};await h.updateMonitor(monitor);assert.equal(h.uploads.length,1);
});
