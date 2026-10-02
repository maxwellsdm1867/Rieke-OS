import test from 'node:test';
import assert from 'node:assert/strict';
import {unmountProject,saveUnmountView,readUnmountView,clearUnmountView} from './projectUnmount.js';
import {trackWrite,registerDraftSaver,assertDesktopWritable} from './desktopLifecycle.js';
const project={path:'/disposable/study',uuid:'fixture',current:true};
test('pending accepts/exports refuse; nothing is cancelled or detached',async()=>{
 let finish,calls=0;const write=trackWrite(new Promise(resolve=>finish=resolve));
 await assert.rejects(unmountProject({project,request:async()=>calls++}),/pending changes/);
 assert.equal(calls,0);finish();await write;
});
test('active unmount saves drafts, fences late mutation callbacks and releases on refusal',async()=>{
 const events=[];const stop=registerDraftSaver(()=>events.push('flush'));
 try{await assert.rejects(unmountProject({project,saveView:()=>events.push('snapshot'),request:async(path)=>{
  events.push(path);assert.throws(()=>assertDesktopWritable('/protocol/accept'),/unmounting/);
  assert.doesNotThrow(()=>assertDesktopWritable('/projects/unmount'));
  throw Object.assign(new Error('busy on server'),{status:409});
 }}),/busy on server/);
 assert.deepEqual(events,['flush','snapshot','/projects/unmount']);assert.doesNotThrow(()=>assertDesktopWritable('/edit'));
 }finally{stop();}
});
test('failed unsaved draft prevents all server close/detach requests',async()=>{
 let calls=0;const stop=registerDraftSaver(()=>{throw new Error('disk full');});
 try{await assert.rejects(unmountProject({project,request:async()=>calls++}),/view could not be saved/);assert.equal(calls,0);assert.doesNotThrow(()=>assertDesktopWritable('/edit'));}finally{stop();}
});
test('inactive and unavailable exact path unmount does not flush the active view',async()=>{
 const stop=registerDraftSaver(()=>{throw new Error('unrelated draft');});
 try{const result=await unmountProject({project:{...project,current:false,available:false},request:async(path,options)=>{
  assert.equal(path,'/projects/unmount');assert.deepEqual(options.body,{path:project.path,project_uuid:project.uuid});return {state:'unmounted'};
 }});assert.equal(result.state,'unmounted');}finally{stop();}
});
test('unsaved view roundtrip retains draft and route without replaying any writes',()=>{
 const map=new Map(),storage={setItem:(k,v)=>map.set(k,v),getItem:k=>map.get(k),removeItem:k=>map.delete(k)};
 const view={route:{page:'explore',key:'saved-route'},sessions:[['saved-route',{draft:{field:'temperature',value:'31'},name:'Unsaved selection'}]]};
 saveUnmountView(project,view,storage);assert.deepEqual(readUnmountView(project,storage),view);clearUnmountView(project,storage);assert.equal(readUnmountView(project,storage),null);
 assert.throws(()=>saveUnmountView(project,view,{setItem(){throw new Error('disk full');}}),/disk full/);
});
test('definite refusal discards only the attempted snapshot; later work remains current',async()=>{
 let snapshot='newer';
 await assert.rejects(unmountProject({project,saveView:()=>{snapshot='attempt';return()=>{snapshot=null;};},request:async()=>{throw Object.assign(new Error('import active'),{status:409});}}),/import active/);
 assert.equal(snapshot,null);
});
test('unsaved scientific input guard refuses before snapshots or requests',async()=>{
 const {registerUnmountGuard}=await import('./desktopLifecycle.js');let called=false;
 const stop=registerUnmountGuard(()=>'Save or clear the unfinished tag before unmounting.');
 try{await assert.rejects(unmountProject({project,request:async()=>{called=true;}}),/unfinished tag/);assert.equal(called,false);}finally{stop();}
});
test('unverified close keeps mutations paused and permits only an explicit safe retry',async()=>{
 let discarded=false;
 await assert.rejects(unmountProject({project,saveView:()=>()=>{discarded=true;},request:async()=>{throw Object.assign(new Error('close unverified'),{status:409,data:{close_unconfirmed:true}});}}),/close unverified/);
 assert.equal(discarded,false);assert.throws(()=>assertDesktopWritable('/annotations'),/unmounting/);
 let savedAgain=false;
 await assert.rejects(unmountProject({project,retryClosed:true,saveView:()=>{savedAgain=true;},request:async()=>{throw new Error('retry connection refused');}}),/connection refused/);
 assert.equal(savedAgain,false);assert.throws(()=>assertDesktopWritable('/annotations'),/unmounting/);
 const {beginProjectUnmount}=await import('./desktopLifecycle.js');beginProjectUnmount(true)();
});
