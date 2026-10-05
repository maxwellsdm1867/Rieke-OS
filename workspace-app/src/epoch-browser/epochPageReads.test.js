import test from 'node:test';
import assert from 'node:assert/strict';
import {createEpochPageReads} from './epochPageReads.js';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const path='/protocols/p/epochs?cell_uuid=c&offset=0&limit=60';

test('expansion and selection share one pending page with independent cancellation',async()=>{
  const calls=[];let finish;
  const reads=createEpochPageReads((path,options)=>{calls.push({path,...options});return new Promise(resolve=>finish=resolve);});
  const a=new AbortController(),b=new AbortController();
  const first=reads.load(path,{signal:a.signal}),second=reads.load(path,{signal:b.signal});
  const cancelled=assert.rejects(first,{name:'AbortError'});a.abort();await cancelled;
  assert.equal(calls.length,1);assert.equal(calls[0].signal.aborted,false);
  const page={epochs:[],query_revision:'current'};finish(page);assert.equal(await second,page);
  const third=reads.load(path);assert.equal(calls.length,2,'a completed page is not reused as fresh membership');
  finish(page);await third;
});

test('last cancellation retires a page and late settlement cannot delete its replacement',async()=>{
  const calls=[];
  const reads=createEpochPageReads((path,options)=>new Promise(resolve=>calls.push({path,...options,resolve})));
  const controller=new AbortController(),old=reads.load(path,{signal:controller.signal});
  const cancelled=assert.rejects(old,{name:'AbortError'});controller.abort();await cancelled;
  assert.equal(calls[0].signal.aborted,true);
  const fresh=reads.load(path);calls[0].resolve({revision:'old'});await Promise.resolve();
  const joined=reads.load(path);assert.equal(calls.length,2);
  calls[1].resolve({revision:'new'});assert.deepEqual(await fresh,await joined);
});

test('page bodies, scope pools and explicit reload remain independent; writes refuse',async()=>{
  const calls=[];
  const request=(path,options)=>new Promise(resolve=>calls.push({path,...options,resolve}));
  const a=createEpochPageReads(request),b=createEpochPageReads(request);
  const pending=[a.load(path),b.load(path),a.reload(path),
    a.load('/explore/epochs',{method:'POST',body:{revision:'a',predicate:{value:1}}}),
    a.load('/explore/epochs',{method:'POST',body:{revision:'b',predicate:{value:1}}})];
  assert.equal(calls.length,5);for(const call of calls)call.resolve({epochs:[]});await Promise.all(pending);
  await assert.rejects(a.load('/annotations',{method:'POST',body:{tags_add:['x']}}),/Only epoch page reads/);
  assert.equal(calls.length,5);
});

test('an actual page retry is fresh but subsequent page navigation shares with selection again',async()=>{
  const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
  const {useEpochBrowserPage}=await server.ssrLoadModule('/src/epoch-browser/useEpochBrowserPage.js');
  const calls=[],reads=createEpochPageReads((path,options)=>new Promise(resolve=>calls.push({path,...options,resolve})));
  const source={kind:'protocol',protocolId:'p'};let current,renderer;
  function Probe({offset}){current=useEpochBrowserPage(source,{offset},0,reads);return null;}
  const render=async offset=>act(async()=>{const element=React.createElement(Probe,{offset});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});
  try{
    await render(0);await act(async()=>calls[0].resolve({offset:0,epochs:[]}));
    await act(async()=>current.reload());assert.equal(calls.length,2);
    await render(60);assert.equal(calls[1].signal.aborted,true);
    const selection=reads.load('/protocols/p/epochs?limit=60&offset=60');assert.equal(calls.length,3);
    await act(async()=>{calls[2].resolve({offset:60,epochs:[]});calls[1].resolve({offset:0,epochs:[]});await selection;});
    assert.equal(current.data.offset,60);assert.equal(current.loading,false);
  }finally{await act(async()=>renderer?.unmount());await server.close();}
});
