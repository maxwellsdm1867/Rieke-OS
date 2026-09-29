import test from 'node:test';
import assert from 'node:assert/strict';
import {scheduleLoadingNotice} from './loadingNotice.js';
function clock(){let now=0,id=0;const timers=new Map();return {setTimer(fn,delay){timers.set(++id,{at:now+delay,fn});return id;},clearTimer(id){timers.delete(id);},tick(ms){now+=ms;for(const [id,timer] of timers)if(timer.at<=now){timers.delete(id);timer.fn();}}};}
test('fast navigation completes without flashing a loading notice',()=>{
 const time=clock(),shown=[];const cancel=scheduleLoadingNotice(true,value=>shown.push(value),time);
 time.tick(100);cancel();scheduleLoadingNotice(false,value=>shown.push(value),time);time.tick(500);
 assert.deepEqual(shown,[false]);
});
test('one notice survives a short metadata-to-sample handoff',()=>{
 const time=clock(),shown=[];let cancel=scheduleLoadingNotice(true,value=>shown.push(value),time);time.tick(220);
 cancel();cancel=scheduleLoadingNotice(false,value=>shown.push(value),time);time.tick(50);
 cancel();cancel=scheduleLoadingNotice(true,value=>shown.push(value),time);time.tick(220);
 assert.deepEqual(shown,[true,true]);cancel();scheduleLoadingNotice(false,value=>shown.push(value),time);time.tick(120);
 assert.equal(shown.at(-1),false);
});
test('unmounted loading surfaces cannot publish a late status',()=>{
 const time=clock();const cancel=scheduleLoadingNotice(true,()=>assert.fail('late notice'),time);cancel();time.tick(500);
});
