import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {useExactTraceCursor} from './useExactTraceCursor.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const context={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
const stream={uuid:uid(7),sample_count:100001,sample_rate:10000,units:'pA'},source='b'.repeat(64);
async function harness(){
 let renderer,current;const requests=[],owner={identity:'owner'};
 const request=(path,{signal})=>new Promise((resolve,reject)=>{const q=new URLSearchParams(path.split('?')[1]),start=Number(q.get('start')),count=Number(q.get('count'));requests.push({path,signal,start,count,reject,finish:()=>resolve({epoch_uuid:uid(6),stream_uuid:stream.uuid,source_sha256:source,start,count,total_samples:stream.sample_count,sample_rate:stream.sample_rate,units:stream.units,decimated:false,read_context:context,values:Array.from({length:count},(_,i)=>(start+i)/7)})});});
 function Probe(props){current=useExactTraceCursor({enabled:true,identity:'captured-a',owner,request,epochUuid:uid(6),sourceSha256:source,stream,readContext:context,...props});return null;}
 return {requests,get current(){return current;},async render(props={}){await act(async()=>{if(renderer)renderer.update(React.createElement(Probe,props));else renderer=TestRenderer.create(React.createElement(Probe,props));});},async close(){await act(async()=>renderer?.unmount());}};
}
test('cursor has no background reads, coalesces hover to one tile and reuses only exact admitted samples',async()=>{
 const h=await harness();try{
  await h.render();assert.equal(h.requests.length,0);assert.equal(h.current.sample(42000).state,'pending');
  await act(async()=>{for(let i=0;i<100;i++)h.current.read(40000+i);await new Promise(resolve=>setTimeout(resolve,65));});
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].start,40000);assert.equal(h.requests[0].count,20000);
  await act(async()=>h.requests[0].finish());assert.equal(h.current.sample(40099).value,40099/7);
  await act(async()=>h.current.read(45000,{immediate:true}));assert.equal(h.requests.length,1);assert.equal(h.current.sample(45000).value,45000/7);
  await act(async()=>h.current.read(100000,{immediate:true}));assert.equal(h.requests[1].count,1);assert.equal(h.current.sample(45000).state,'pending','only one raw tile is retained');
  await act(async()=>h.requests[1].finish());assert.equal(h.current.sample(100000).value,100000/7);
 }finally{await h.close();}
});
test('returning to ready A cancels delayed B without another movement or stale replacement',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.current.read(1,{immediate:true}));await act(async()=>h.requests[0].finish());
  await act(async()=>{h.current.read(25000);h.current.read(2);await new Promise(resolve=>setTimeout(resolve,65));});
  assert.equal(h.requests.length,1);assert.equal(h.current.sample(2).value,2/7);
 }finally{await h.close();}
});
test('replacement and owner change abort in-flight cursor reads and late responses cannot publish',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.current.read(1,{immediate:true}));await act(async()=>h.current.read(25000,{immediate:true}));assert(h.requests[0].signal.aborted);
  await act(async()=>h.requests[0].finish());assert.equal(h.current.sample(1).state,'pending');
  await h.render({identity:'captured-b'});assert(h.requests[1].signal.aborted);await act(async()=>h.requests[1].finish());assert.equal(h.current.sample(25000).state,'pending');
  await act(async()=>h.current.read(25000,{immediate:true}));await h.render({identity:'captured-b',owner:{identity:'new-session'}});assert(h.requests[2].signal.aborted);
  await act(async()=>h.requests[2].finish());assert.equal(h.current.sample(25000).state,'pending');
 }finally{await h.close();}
});
test('a settled unwanted tile cannot strand a later return to its same tile',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.current.read(1,{immediate:true}));await act(async()=>h.current.read(25000));
  await act(async()=>h.requests[0].finish());assert.equal(h.current.sample(1).state,'pending');
  await act(async()=>h.current.read(1,{immediate:true}));assert.equal(h.requests.length,2);await act(async()=>h.requests[1].finish());assert.equal(h.current.sample(1).value,1/7);
 }finally{await h.close();}
});
test('cursor failure is not a missing/guessed sample and explicit retry remains bounded',async()=>{
 const h=await harness();try{
  await h.render();await act(async()=>h.current.read(123,{immediate:true}));await act(async()=>h.requests[0].reject(Error('source changed')));
  assert.deepEqual(h.current.sample(123),{state:'error',error:'source changed'});
  await act(async()=>h.current.read(123,{immediate:true}));assert.equal(h.current.sample(123).state,'pending');assert.equal(h.requests.length,2);
  await act(async()=>h.requests[1].finish());assert.equal(h.current.sample(123).value,123/7);
  await h.render({enabled:false});assert.equal(h.current.sample(123).state,'pending');await act(async()=>h.current.read(123,{immediate:true}));assert.equal(h.requests.length,2);
 }finally{await h.close();}
});
