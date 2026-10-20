import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {useCellWindows} from './useCellWindows.js';
const first={cells:[{cell_uuid:'a'}],cells_total:2,cells_next:1};
const last={cells:[{cell_uuid:'b'}],cells_total:2,cells_next:null};
async function harness(t){
 let value,renderer;
 function View({scope,load,enabled=true}){value=useCellWindows(scope,load,{enabled});return null;}
 t.after(async()=>{await act(()=>renderer?.unmount());});
 return {get value(){return value;},async render(props){await act(()=>{if(renderer)renderer.update(React.createElement(View,props));else renderer=TestRenderer.create(React.createElement(View,props));});},async accept(data){await act(()=>value.accept(data));}};
}
test('cell windows fence A/B/A late replies and duplicate same-tick requests',async t=>{
 const h=await harness(t),pending=[];
 const load=(after,options)=>new Promise(resolve=>pending.push({after,options,resolve}));
 await h.render({scope:'A',load});await h.accept(first);
 let a,b;await act(()=>{a=h.value.more();b=h.value.more();});
 assert.equal(pending.length,1,'one request even before React commits loading');
 await h.render({scope:'B',load});await h.render({scope:'A',load});await h.accept(first);
 await act(()=>pending[0].resolve(last));await a;await b;
 assert.deepEqual(h.value.cells,first.cells,'the old A request cannot enter a new A lifetime');
 assert.equal(pending[0].options.signal.aborted,true);
});
test('cell windows stop on changed totals and non-advancing cursors; retry remains available',async t=>{
 const h=await harness(t);let response={...last,cells_total:3};
 await h.render({scope:'A',load:async()=>response});await h.accept(first);
 await act(()=>h.value.more());assert.match(h.value.window.error,/changed|invalid/i);assert.deepEqual(h.value.cells,first.cells);
 response={...last,cells_next:1};await act(()=>h.value.more());assert.match(h.value.window.error,/changed|invalid/i);
 response=last;await act(()=>h.value.more());assert.deepEqual(h.value.cells,[...first.cells,...last.cells]);assert.equal(h.value.window.loaded,2);
});
test('disabled cell windows neither load nor accept a late pending reply',async t=>{
 const h=await harness(t);let resolve,calls=0;
 const load=()=>{calls++;return new Promise(r=>{resolve=r;});};
 await h.render({scope:'A',load});await h.accept(first);let promise;await act(()=>{promise=h.value.more();});
 await h.render({scope:'A',load,enabled:false});await act(()=>resolve(last));await promise;
 await act(()=>h.value.more());assert.equal(calls,1);assert.deepEqual(h.value.cells,first.cells);
});
