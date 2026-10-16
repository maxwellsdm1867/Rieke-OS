import test from 'node:test';
import assert from 'node:assert/strict';
import {armAction,observationFinished} from '../workflow/browser.mjs';
import {geometryReadiness,geometrySnapshot} from './observer.mjs';

// Explicit frame scheduler: callbacks queued by one frame cannot run until the
// next. Driver retrieval advances the clock without invoking readiness.
function model(t){
 const keys=['window','document','performance','requestAnimationFrame','cancelAnimationFrame','setTimeout','clearTimeout'];
 const old=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 let now=100,serial=0;const frames=new Map(),timers=new Map();
 const w={active:null,requests:[],draws:[],completed:{}};
 const state={status:false,width:751,stream:{status:'ready',stream_uuid:'stream'}};
 globalThis.window={__workflow:w,__workflowReadiness:geometryReadiness,__workflowReadStream:()=>state.stream};
 globalThis.document={querySelector:s=>s==='.tv-status'?(state.status?{}:null):s==='.tv-base'?{getBoundingClientRect:()=>({width:state.width})}:null};
 Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now}});
 globalThis.requestAnimationFrame=f=>{frames.set(++serial,f);return serial;};
 globalThis.cancelAnimationFrame=id=>frames.delete(id);
 globalThis.setTimeout=(f,ms)=>{timers.set(++serial,{f,at:now+ms});return serial;};
 globalThis.clearTimeout=id=>timers.delete(id);
 t.after(()=>{for(const k of keys){if(old[k])Object.defineProperty(globalThis,k,old[k]);else delete globalThis[k];}});
 const ready=()=>{w.requests=[{action_id:'owned',url:'/api/trace-views/token/epochs/epoch/display?stream_uuid=stream',method:'GET',status:200,start:101,headers:107,end:108,binary:new ArrayBuffer(100)}];w.draws=[{action_id:'owned',stream_uuid:'stream',at:110}];};
 const el={isConnected:true,disabled:false,click(){assert.equal(frames.size,1);assert.ok(w.active.observer_armed_at<=w.active.intent);ready();}};
 return {w,state,frames,timers,ready,el,async arm(){await armAction(el,{action_id:'owned',phase:'ordinary',spec:{trace:{stream_uuid:'stream'}},timeoutMs:1000});},frame(){now+=16;const batch=[...frames.values()];frames.clear();for(const f of batch)f(now);},advance(ms){now+=ms;for(const[id,v]of [...timers])if(v.at<=now){timers.delete(id);v.f();}}};
}
for(const delay of [0,80,160])test(`geometry closes on two actual RAFs with ${delay} ms delayed driver retrieval`,async t=>{
 const c=model(t);await c.arm();assert.equal(c.w.active.diagnosticFrames,undefined);assert.equal(c.w.completed.owned,undefined);
 c.frame();assert.equal(c.w.active.diagnosticFrames,1);assert.equal(c.w.completed.owned,undefined);
 c.frame();assert.equal(c.w.active,null);assert.equal(c.w.completed.owned.observer_raf_count,2);
 assert.equal(c.w.completed.owned.captured_requests[0].binary.byteLength,100,'wire oracle retains binary outside observation');
 c.advance(delay);assert.equal(observationFinished('owned'),true);const s=geometrySnapshot('owned');
 assert.equal(s.total_ms,32);assert.equal(s.trace.first_visible_ms,10);assert.equal(s.trace.first_raf_ms,16);assert.equal(s.trace.complete_ms,32);
 assert.equal(s.observer.driver_retrieval_lag_ms,delay);assert.equal(c.frames.size,0);assert.equal(c.timers.size,0);
 c.w.requests.push({action_id:'owned',url:'late'});assert.equal(geometrySnapshot('owned').requests.length,1);
});
for(const defect of ['wrong action','duplicate response','status','body pending','short binary','missing binary','wrong stream','pending control','pre-body draw','wrong draw action','wrong draw stream','status overlay','zero width'])test(`geometry readiness preserves refusal: ${defect}`,async t=>{
 const c=model(t);await c.arm();c.frame();assert.equal(c.w.active.diagnosticFrames,1);
 const r=c.w.requests[0],d=c.w.draws[0];
 if(defect==='wrong action')r.action_id='old';
 if(defect==='duplicate response')c.w.requests.push({...r});
 if(defect==='status')r.status=500;
 if(defect==='body pending')delete r.end;
 if(defect==='short binary')r.binary=new ArrayBuffer(99);
 if(defect==='missing binary')delete r.binary;
 if(defect==='wrong stream')c.state.stream.stream_uuid='other';
 if(defect==='pending control')c.state.stream.status='pending';
 if(defect==='pre-body draw')d.at=107;
 if(defect==='wrong draw action')d.action_id='old';
 if(defect==='wrong draw stream')d.stream_uuid='other';
 if(defect==='status overlay')c.state.status=true;
 if(defect==='zero width')c.state.width=0;
 c.frame();assert.equal(c.w.completed.owned,undefined);assert.equal(c.w.active.diagnosticFrames,0);assert.equal(c.w.active.diagnosticFirstRaf,null);
 c.ready();Object.assign(c.state,{status:false,width:751,stream:{status:'ready',stream_uuid:'stream'}});
 c.frame();assert.equal(c.w.completed.owned,undefined);c.frame();assert.equal(geometrySnapshot('owned').total_ms,64);assert.equal(geometrySnapshot('owned').trace.first_raf_ms,48);
});
test('geometry timeout remains page-owned and cancels RAFs',async t=>{
 const c=model(t);await c.arm();c.w.requests=[];c.advance(1001);
 assert.throws(()=>observationFinished('owned'),/readiness timed out/);assert.equal(c.w.completed.owned,undefined);assert.equal(c.frames.size,0);assert.equal(c.timers.size,0);
});
test('geometry oracle exception propagates and cancels polling',async t=>{
 const c=model(t);await c.arm();window.__workflowReadStream=()=>{throw Error('stream oracle failed');};c.frame();
 assert.throws(()=>observationFinished('owned'),/stream oracle failed/);assert.equal(c.w.completed.owned,undefined);assert.equal(c.frames.size,0);assert.equal(c.timers.size,0);
});
test('geometry changed ownership cannot close a replacement action',async t=>{
 const c=model(t);await c.arm();const replacement={action_id:'replacement'};c.w.active=replacement;c.frame();
 assert.throws(()=>observationFinished('owned'),/ownership changed/);assert.equal(c.w.active,replacement);assert.equal(c.w.completed.owned,undefined);assert.equal(c.frames.size,0);assert.equal(c.timers.size,0);
});
