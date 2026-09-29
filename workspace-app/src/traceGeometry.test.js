import test from 'node:test';
import assert from 'node:assert/strict';
import {clampWindow,dragWindow,finiteExtent,finiteSegments,formatTick,MAX_TRACE_SAMPLES,sampleAtPixel,ticks,timeRange,zoomWindow} from './components/traceGeometry.js';

test('trace window clamps to source bounds and never exceeds full-rate request cap',()=>{
 assert.deepEqual(clampWindow(-50,50000,100000),{start:0,count:MAX_TRACE_SAMPLES});
 assert.deepEqual(clampWindow(99999,20000,100000),{start:80000,count:20000});
 assert.deepEqual(clampWindow(900,20000,1000),{start:0,count:1000});
 assert.deepEqual(clampWindow(0,10,0),{start:0,count:0});
 assert.deepEqual(clampWindow(0,10,1),{start:0,count:1});
});
test('sample time ends at the last actual sample, not the exclusive window end',()=>{
 assert.deepEqual(timeRange(20000,20000,10000),{first:2,last:3.9999,span:1.9999});
 assert.deepEqual(timeRange(5,1,10000),{first:.0005,last:.0005,span:0});
 assert.equal(timeRange(0,10,0),null);
 assert.equal(timeRange(0,0,10000),null);
});
test('nearest sample cursor preserves actual index at both plot boundaries',()=>{
 assert.equal(sampleAtPixel(-50,500,20000),0);
 assert.equal(sampleAtPixel(500,500,20000),19999);
 assert.equal(sampleAtPixel(900,500,20000),19999);
 assert.equal(sampleAtPixel(250,500,1),0);
 assert.equal(sampleAtPixel(200,0,20000),null);
});
test('dragging to zoom uses inclusive samples and does not depend on drag direction',()=>{
 const viewport={start:100,count:101};
 assert.deepEqual(dragWindow(viewport,1000,10,30,100),{start:110,count:21});
 assert.deepEqual(dragWindow(viewport,1000,30,10,100),{start:110,count:21});
 assert.deepEqual(dragWindow(viewport,1000,-50,150,100),viewport);
});
test('drag pan moves the viewport opposite to pointer motion and clamps at edges',()=>{
 const viewport={start:100,count:101};
 assert.deepEqual(dragWindow(viewport,1000,10,30,100,'pan'),{start:80,count:101});
 assert.deepEqual(dragWindow({start:0,count:101},1000,10,30,100,'pan'),{start:0,count:101});
});
test('zoom respects its anchor and full-rate sample cap',()=>{
 assert.deepEqual(zoomWindow({start:100,count:100},1000,.5,100),{start:100,count:50});
 assert.deepEqual(zoomWindow({start:100,count:100},1000,.5,199),{start:150,count:50});
 const zoomed=zoomWindow({start:80000,count:20000},100000,2);
 assert.deepEqual(zoomed,{start:80000,count:20000});
 assert.deepEqual(zoomWindow({start:0,count:1},1,.5),{start:0,count:1});
});
test('missing values create disconnected segments and never become zero',()=>{
 assert.deepEqual(finiteSegments([null,5,null,0,2,NaN,Infinity,-3]),[[{index:1,value:5}],[{index:3,value:0},{index:4,value:2}],[{index:7,value:-3}]]);
 const extent=finiteExtent([null,5,NaN,Infinity]);
 assert.equal(extent.finiteCount,1);assert.equal(extent.missingCount,3);assert.ok(extent.min<5&&extent.max>5);
 assert.equal(finiteExtent([null,NaN,Infinity]),null);
});
test('tick formatting preserves scientific exponents and useful tiny amplitude ranges',()=>{
 assert.equal(formatTick(1e9,1e8),'1.00e+9');
 assert.equal(formatTick(1e-10,1e-11),'1.00e-10');
 const values=ticks(-.000005,.000005,5);
 assert.ok(values.includes(0));assert.ok(values.every(value=>value>=-.000005&&value<=.000005));
 assert.deepEqual(ticks(2,2),[2]);
});
