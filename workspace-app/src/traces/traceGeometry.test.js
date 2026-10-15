import test from 'node:test';
import assert from 'node:assert/strict';
import {clampWindow,dragWindow,finiteExtent,finiteSegments,formatTick,MAX_TRACE_SAMPLES,sampleAtPixel,ticks,timeRange,traceDisplaySegments,zoomWindow} from './ui/traceGeometry.js';

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


test('million-sample display retains endpoint and both same-column spikes within a physical-pixel bound',()=>{
 const values=new Float64Array(1000000),positive=123456,negative=123457;values[positive]=100;values[negative]=-100;
 const before=Buffer.from(values.buffer).toString('base64');
 const segments=traceDisplaySegments(values,500),indices=segments.flat();
 assert.equal(segments.length,1);assert.equal(indices[0],0);assert.equal(indices.at(-1),999999);
 assert(indices.includes(positive));assert(indices.includes(negative));assert(indices.length<=4*500);
 for(let i=1;i<indices.length;i++)assert(indices[i]>indices[i-1],'indices are unique and in recorded order');
 assert.equal(Buffer.from(values.buffer).toString('base64'),before,'display selection never alters full-rate values');
 assert.equal(values[sampleAtPixel(positive/999999*500,500,1000000)],100,'cursor still addresses the original sample');
});
test('pixel display never connects across gaps and preserves isolated samples within one column',()=>{
 const values=new Array(1000).fill(2);values[0]=null;values[100]=NaN;values[101]=4;values[102]=Infinity;values[500]=null;values[501]=-10;values[502]=null;values[999]=null;
 const segments=traceDisplaySegments(values,1);
 assert.deepEqual(segments.map(s=>[s[0],s.at(-1)]),[[1,99],[101,101],[103,499],[501,501],[503,998]]);
 for(const segment of segments)for(let i=segment[0];i<=segment.at(-1);i++)assert.equal(typeof values[i]==='number'&&Number.isFinite(values[i]),true);
 assert(segments.every(s=>s.length<=4));
});
test('display width and device scale set the point budget; zoomed windows naturally draw every sample',()=>{
 const values=new Float64Array(10000);
 const a=traceDisplaySegments(values,100)[0],b=traceDisplaySegments(values,200)[0],c=traceDisplaySegments(values,300.5)[0];
 assert(b.length>a.length);assert(c.length>b.length);assert(a.length<=400);assert(b.length<=800);assert(c.length<=1204);
 const zoomed=values.subarray(3000,3200);
 assert.deepEqual(traceDisplaySegments(zoomed,100),[Array.from({length:200},(_,i)=>i)]);
 assert.deepEqual(traceDisplaySegments([1,null,2,3],0),[[0],[2,3]],'unavailable display geometry never drops samples');
 assert.deepEqual(traceDisplaySegments([null,NaN],100),[]);assert.deepEqual(traceDisplaySegments([7],1),[[0]]);
});
