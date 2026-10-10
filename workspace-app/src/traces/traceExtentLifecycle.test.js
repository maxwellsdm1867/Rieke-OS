import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?text(node.children):'';
test('whole default, explicit Sample, remembered window, independent views and complete range',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const calls=[];let renderer;
 const port={identity:'extent-test',request:async path=>{
  const q=new URLSearchParams(path.split('?')[1]),start=+q.get('start'),count=+q.get('count'),id=path.split('/')[2],total=id==='short'?100:67500;
  calls.push({id,start,count});return {epoch_uuid:id,stream_uuid:'s',start,count,total_samples:total,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array(count).fill(1)};
 }};
 const epoch=id=>({epoch_uuid:id,streams:[{kind:'responses',uuid:'s',sample_count:id==='short'?100:67500,sample_rate:10000,units:'pA'}]});
 const render=async id=>act(async()=>{
  const element=React.createElement(WorkspaceRequestProvider,{port},React.createElement(React.Fragment,null,React.createElement(Trace,{key:'main',epoch:epoch(id)}),React.createElement(Trace,{key:'independent',epoch:epoch('other')})));
  if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);
 });
 const view=()=>renderer.root.findAllByProps({'aria-label':'Recorded response viewer'})[0];
 const button=label=>view().findAllByType('button').find(b=>text(b.props.children)===label);
 try{
  await render('a');assert.equal(button('Whole epoch').props['aria-pressed'],true);
  assert.match(text(renderer.toJSON()),/0–6.7499 s/);assert.match(text(renderer.toJSON()),/67,500 \/ 67,500 samples/);
  assert.deepEqual(calls.filter(c=>c.id==='a').map(c=>c.count),[20000,20000,20000,7500]);
  await act(async()=>button('Sample').props.onClick());
  assert.equal(button('Sample').props['aria-pressed'],true);assert.match(text(renderer.toJSON()),/20,000 \/ 67,500 samples/);
  const form=view().findByType('form'),inputs=form.findAllByType('input');
  await act(async()=>{inputs[0].props.onChange({target:{value:'30000'}});inputs[1].props.onChange({target:{value:'1000'}});});
  await act(async()=>form.props.onSubmit({preventDefault(){}}));
  await render('b');assert.deepEqual(calls.filter(c=>c.id==='b').at(-1),{id:'b',start:30000,count:1000});
  await render('short');assert.deepEqual(calls.filter(c=>c.id==='short').at(-1),{id:'short',start:0,count:100});
  await render('c');assert.deepEqual(calls.filter(c=>c.id==='c').at(-1),{id:'c',start:30000,count:1000});
  const independent=renderer.root.findAllByProps({'aria-label':'Recorded response viewer'})[1];
  assert.equal(independent.findAllByType('button').find(b=>text(b.props.children)==='Whole epoch').props['aria-pressed'],true);
  await act(async()=>button('Whole epoch').props.onClick());assert.equal(button('Whole epoch').props['aria-pressed'],true);
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});
test('whole trace revision changes abort held chunks and refuse late A/B/A results',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const held=[];let renderer;
 const port={identity:'held-owner',request:(path,{signal})=>new Promise(resolve=>held.push({path,signal,resolve}))};
 const epoch={epoch_uuid:'a',streams:[{kind:'responses',uuid:'s',sample_count:25000,sample_rate:10000,units:'pA'}]};
 const render=async revision=>act(async()=>{
  const element=React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch,revision}));
  if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);
 });
 const complete=async(index,value)=>act(async()=>{
  const h=held[index],q=new URLSearchParams(h.path.split('?')[1]),start=+q.get('start'),count=+q.get('count');
  h.resolve({epoch_uuid:'a',stream_uuid:'s',start,count,total_samples:25000,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array(count).fill(value)});
 });
 try{
  await render('A');await render('B');await render('A');
  assert.equal(held.length,3);assert(held[0].signal.aborted);assert(held[1].signal.aborted);assert(!held[2].signal.aborted);
  await complete(0,90);await complete(1,80);assert.equal(held.length,3,'retired reads cannot schedule the next chunk');
  assert.doesNotMatch(text(renderer.toJSON()),/0–2.4999 s/);
  await complete(2,1);assert.equal(held.length,4);assert.doesNotMatch(text(renderer.toJSON()),/0–2.4999 s/);
  await complete(3,2);assert.match(text(renderer.toJSON()),/0–2.4999 s/);
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});

test('inline response choices retain exact UUIDs even with duplicate device names',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const calls=[];let renderer;
 const port={identity:'stream-choice',request:async path=>{const q=new URLSearchParams(path.split('?')[1]);calls.push(q.get('stream_uuid'));return {epoch_uuid:'e',stream_uuid:q.get('stream_uuid'),start:0,count:3,sample_rate:10000,units:'pA',values:[1,2,3]};}};
 const epoch={epoch_uuid:'e',streams:['s1','s2'].map(uuid=>({kind:'responses',uuid,device:'Amp1',sample_count:3,sample_rate:10000,units:'pA'}))};
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(WorkspaceRequestProvider,{port},React.createElement(Trace,{epoch})));});
  assert.equal(renderer.root.findAllByType('select').length,0);assert.equal(renderer.root.findAllByType('details').length,0);
  assert.equal(renderer.root.findByProps({'aria-label':'Start sample'}).props.disabled,true);
  const second=renderer.root.findByProps({'aria-label':'Response 2: Amp1 · pA'});
  await act(async()=>second.props.onClick());assert.deepEqual(calls,['s1','s2']);assert.equal(second.props['aria-pressed'],true);
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});
