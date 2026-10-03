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
 const queued=new Map();let next=0,ready=false,completed=[];
 const pane={scrollTop:0,scrollHeight:100,clientHeight:100};
 const requestFrame=callback=>{queued.set(++next,callback);return next;},cancelFrame=id=>queued.delete(id);
 const frame=()=>{const work=[...queued.values()];queued.clear();work.forEach(fn=>fn());};
 let cancel=restoreInspectionScroll({pane,top:180,ready:()=>ready,requestFrame,cancelFrame,onRestored:top=>completed.push(top)});
 frame();frame();assert.equal(pane.scrollTop,0);assert.deepEqual(completed,[]);
 ready=true;pane.scrollHeight=660;frame();assert.equal(pane.scrollTop,0);
 frame();assert.equal(pane.scrollTop,180);assert.deepEqual(completed,[180]);cancel();
 ready=false;cancel=restoreInspectionScroll({pane,top:500,ready:()=>ready,requestFrame,cancelFrame});
 frame();cancel();ready=true;frame();frame();assert.equal(pane.scrollTop,180);
 restoreInspectionScroll({pane,top:900,ready:()=>true,requestFrame,cancelFrame});frame();frame();assert.equal(pane.scrollTop,560);
});
