import test from 'node:test';
import assert from 'node:assert/strict';
import {installFrameDiagnostic,wrapReadinessDiagnostic} from './frame-diagnostic.mjs';
function fixture(t){
 const keys=['window','document','performance','PerformanceObserver'],old=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 let now=10,id=0;const queued=new Map(),listeners={},observers=[];
 globalThis.window={__workflow:{active:{action_id:'ordinary-0-million',diagnosticFrames:0},requests:[],draws:[]},requestAnimationFrame:f=>{queued.set(++id,f);return id;},__workflowReadStream:()=>({status:'ready',stream_uuid:'stream'})};
 globalThis.document={visibilityState:'visible',hidden:false,hasFocus:()=>true,addEventListener:(name,f)=>{listeners[name]=f;},querySelector:name=>name==='.tv-base'?{getBoundingClientRect:()=>({width:751})}:null};
 Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now++}});
 globalThis.PerformanceObserver=class{constructor(callback){observers.push(callback);}observe(options){assert.equal(options.type,'longtask');}};
 t.after(()=>{for(const key of keys){if(old[key])Object.defineProperty(globalThis,key,old[key]);else delete globalThis[key];}});
 return {queued,observers,listeners,frame(timestamp=16){const batch=[...queued.values()];queued.clear();for(const callback of batch)callback(timestamp);}};
}
test('passive RAF logger adds no scheduled callback and preserves timestamp/exception/return',t=>{
 const f=fixture(t);installFrameDiagnostic();assert.equal(f.queued.size,0);
 const id=window.requestAnimationFrame(timestamp=>{assert.equal(timestamp,32);return 'original';});assert.equal(id,1);assert.equal(f.queued.size,1);
 const cb=f.queued.get(id);assert.equal(cb(32),'original');assert.equal(f.queued.size,1,'wrapper schedules no new frame');
 assert.equal(window.__traceFrameDiagnostic.frames.length,1);
 window.requestAnimationFrame(()=>{throw Error('original failure');});assert.throws(()=>f.queued.get(2)(48),/original failure/);assert.equal(window.__traceFrameDiagnostic.frames.length,2);
});
test('callback, visibility and longtask histories stay capped',t=>{
 const f=fixture(t);installFrameDiagnostic();
 for(let i=0;i<520;i++){window.requestAnimationFrame(()=>{});f.frame();}
 for(let i=0;i<70;i++)f.listeners.visibilitychange();
 f.observers[0]({getEntries:()=>Array.from({length:140},()=>({startTime:1,duration:51,name:'self'}))});
 const d=window.__traceFrameDiagnostic;assert.equal(d.frames.length,512);assert.equal(d.visibility.length,64);assert.equal(d.longtasks.length,128);assert.ok(d.dropped>0);
});
test('readiness is called exactly once, keeps its result/state, and records predicates afterwards',t=>{
 fixture(t);installFrameDiagnostic();const a=window.__workflow.active;let calls=0;
 window.__workflowReadiness=()=>{calls++;a.diagnosticFrames=2;window.__workflow.active=null;return true;};
 window.__workflow.requests=[{action_id:a.action_id,url:'/display?x',status:200,end:20,binary:new ArrayBuffer(100)}];window.__workflow.draws=[{action_id:a.action_id,at:21,stream_uuid:'stream'}];
 wrapReadinessDiagnostic();assert.equal(window.__workflowReadiness({trace:{stream_uuid:'stream'}}),true);assert.equal(calls,1);assert.equal(window.__workflow.active,null);
 const row=window.__traceFrameDiagnostic.readiness[0];assert.equal(row.correct_frames,2);assert.equal(row.matching_draw_at,21);assert.equal(row.status_overlay,false);assert.equal(row.canvas_width,751);
});
test('readiness exceptions remain failures and no repeated call is made',t=>{
 fixture(t);installFrameDiagnostic();let calls=0;window.__workflowReadiness=()=>{calls++;throw Error('oracle failure');};wrapReadinessDiagnostic();
 assert.throws(()=>window.__workflowReadiness({trace:{stream_uuid:'stream'}}),/oracle failure/);assert.equal(calls,1);assert.equal(window.__traceFrameDiagnostic.readiness.length,0);
});
test('nontrace readiness and unrelated RAF preserve result without action evidence',t=>{
 const f=fixture(t);installFrameDiagnostic();window.__workflow.active.action_id='setup-0';window.requestAnimationFrame(()=>42);f.frame();assert.equal(window.__traceFrameDiagnostic.frames.length,0);
 window.__workflowReadiness=()=>false;wrapReadinessDiagnostic();assert.equal(window.__workflowReadiness({}),false);assert.equal(window.__traceFrameDiagnostic.readiness.length,0);
});
