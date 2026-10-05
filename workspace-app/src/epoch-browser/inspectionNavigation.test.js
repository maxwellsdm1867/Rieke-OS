import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectionNavigation,inspectionPageOffset,restoreInspectionScroll} from './inspectionNavigation.js';

test('presentation hints are scoped, bounded and clamp pagination to current cell membership',()=>{
 const saved={scope:'A',dates:['today'],cells:['cell'],offsets:{cell:120},scrollTop:180};
 assert.deepEqual(inspectionNavigation(saved,'A'),saved);
 assert.deepEqual(inspectionNavigation(saved,'B'),{scope:'B',dates:[],cells:[],offsets:{},scrollTop:0});
 assert.equal(inspectionPageOffset(120,61),60);
 assert.equal(inspectionPageOffset(120,0),0);
 const bounded=inspectionNavigation({...saved,cells:Array.from({length:1000},(_,n)=>`cell-${n}`)},'A');
 assert.equal(bounded.cells.length,128);assert.equal(Object.keys(bounded.offsets).length,128);
});

test('achieved scroll waits for fresh membership and two settled frames; newer intent cancels it',()=>{
 const queued=new Map();let next=0,ready=false,completed=[],notify;
 const observe=callback=>{notify=callback;return()=>{notify=null;};};
 const pane={scrollTop:0,scrollHeight:100,clientHeight:100};
 const requestFrame=callback=>{queued.set(++next,callback);return next;},cancelFrame=id=>queued.delete(id);
 const frame=()=>{const work=[...queued.values()];queued.clear();work.forEach(fn=>fn());};
 let cancel=restoreInspectionScroll({pane,top:180,ready:()=>ready,observe,requestFrame,cancelFrame,onRestored:top=>completed.push(top)});
 frame();frame();assert.equal(pane.scrollTop,0);assert.deepEqual(completed,[]);
 assert.equal(queued.size,0,'failed or pending membership must not perpetually poll RAF');
 ready=true;pane.scrollHeight=660;notify();frame();assert.equal(pane.scrollTop,0);
 frame();assert.equal(pane.scrollTop,180);assert.deepEqual(completed,[180]);assert.equal(notify,null);cancel();
 ready=false;cancel=restoreInspectionScroll({pane,top:500,ready:()=>ready,observe,requestFrame,cancelFrame});
 frame();cancel();ready=true;frame();frame();assert.equal(pane.scrollTop,180);
 restoreInspectionScroll({pane,top:900,ready:()=>true,observe,requestFrame,cancelFrame});frame();frame();assert.equal(pane.scrollTop,560);
});

test('DOM readiness observer sleeps through errors, wakes on retry, and releases on effect replay/unmount',async()=>{
 const {JSDOM}=await import('jsdom');
 const dom=new JSDOM('<div id="pane" data-inspection-membership-ready="false"><div data-inspection-page-ready="false"></div></div>');
 const previous=globalThis.MutationObserver;globalThis.MutationObserver=dom.window.MutationObserver;
 const pane=dom.window.document.querySelector('#pane'),child=pane.firstElementChild;
 Object.defineProperties(pane,{scrollHeight:{value:660},clientHeight:{value:100}});
 const frames=new Map();let serial=0,done=0;
 const requestFrame=callback=>{frames.set(++serial,callback);return serial;},cancelFrame=id=>frames.delete(id);
 const frame=()=>{const batch=[...frames.values()];frames.clear();batch.forEach(fn=>fn());};
 const options={pane,top:180,requestFrame,cancelFrame,ready:()=>pane.dataset.inspectionMembershipReady==='true'&&!pane.querySelector('[data-inspection-page-ready="false"]'),onRestored:()=>done++};
 let cancel;
 try{
  cancel=restoreInspectionScroll(options);cancel(); // StrictMode-style effect cleanup/replay.
  cancel=restoreInspectionScroll(options);frame();assert.equal(frames.size,0);
  pane.dataset.inspectionMembershipReady='true';await Promise.resolve();frame();assert.equal(frames.size,0);assert.equal(done,0);
  child.textContent='Request failed';await Promise.resolve();frame();assert.equal(frames.size,0);
  child.dataset.inspectionPageReady='true';await Promise.resolve();frame();assert.equal(done,0);frame();assert.equal(done,1);assert.equal(pane.scrollTop,180);
  child.textContent='Later unrelated update';await Promise.resolve();assert.equal(frames.size,0,'completed observer is disconnected');
  cancel=restoreInspectionScroll(options);cancel();child.textContent='Unmounted';await Promise.resolve();assert.equal(frames.size,0);
 }finally{cancel?.();globalThis.MutationObserver=previous;dom.window.close();}
});
