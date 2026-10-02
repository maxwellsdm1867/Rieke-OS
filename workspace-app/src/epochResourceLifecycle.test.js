import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

const metadata=uuid=>({epoch_uuid:uuid,streams:[{kind:'responses',uuid:`stream-${uuid}`,sample_count:3}]});
const trace=uuid=>({epoch_uuid:uuid,stream_uuid:`stream-${uuid}`,start:0,count:3,sample_rate:10000,values:[-1,null,2]});
async function harness(t){
 const previousFetch=globalThis.fetch,requests=[],renders=[];
 let respond=path=>{const uuid=new URL(path,'http://fixture').pathname.split('/')[2];return path.includes('/trace?')?trace(uuid):metadata(uuid);};
 globalThis.fetch=async(url,options)=>{const path=url.slice(4);requests.push({path,signal:options.signal});return new Response(JSON.stringify(await respond(path)),{status:200});};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {useEpochResource}=await server.ssrLoadModule('/src/api.js');
 const {epochResourceCache:cache,initialEpochTracePath}=await server.ssrLoadModule('/src/resourceCache.js');
 t.mock.timers.enable({apis:['setTimeout']});
 let renderer,current;
 function Probe({path,revision=0}){current=useEpochResource(path,revision);renders.push({...current});return null;}
 const h={cache,requests,renders,get current(){return current;},set respond(value){respond=value;},
  warm(uuid,revision=0,path=`/epochs/${uuid}`){const epoch=metadata(uuid);cache.put(path,revision,epoch);cache.put(initialEpochTracePath(epoch),revision,trace(uuid));return epoch;},
  async render(path,revision=0){await act(async()=>{const element=React.createElement(Probe,{path,revision});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});},
  async tick(ms){await act(async()=>{t.mock.timers.tick(ms);for(let index=0;index<10;index++)await Promise.resolve();});},
  async reload(){await act(async()=>current.reload());},
  async close(){await act(async()=>renderer?.unmount());t.mock.timers.reset();await server.close();globalThis.fetch=previousFetch;}};
 return h;
}
test('complete warm A/B/A transitions publish in their first render without timers or I/O',async t=>{
 const h=await harness(t);try{
  const a=h.warm('a',7,'/epochs/a?protocol_uuid=p'),b=h.warm('b',7,'/epochs/b?protocol_uuid=p');
  for(const epoch of [a,b,a]){
   const start=h.renders.length;await h.render(`/epochs/${epoch.epoch_uuid}?protocol_uuid=p`,7);
   assert.equal(h.renders[start].data,epoch);assert.equal(h.renders[start].loading,false);assert.equal(h.current.data,epoch);
  }
  await h.tick(80);assert.equal(h.requests.length,0);
 }finally{await h.close();}
});
test('metadata-only misses retain 80 ms latest-intent coalescing and await the matching trace',async t=>{
 const h=await harness(t);let finish;
 try{
  h.cache.put('/epochs/a',0,metadata('a'));h.cache.put('/epochs/b',0,metadata('b'));
  h.respond=path=>path.includes('/trace?')?new Promise(resolve=>finish=resolve):metadata('b');
  await h.render('/epochs/a');await h.render('/epochs/b');await h.tick(79);
  assert.equal(h.requests.length,0);assert.equal(h.current.data,null);assert.equal(h.current.loading,true);
  await h.tick(1);assert.deepEqual(h.requests.map(item=>item.path),['/epochs/b/trace?stream_uuid=stream-b&start=0&count=3']);
  assert.equal(h.current.data,null);await act(async()=>finish(trace('b')));
  assert.equal(h.current.data.epoch_uuid,'b');assert.equal(h.current.loading,false);
 }finally{await h.close();}
});
test('query/revision changes and reload hide previous warm data until exact fresh reads complete',async t=>{
 const h=await harness(t);try{
  h.warm('a',7,'/epochs/a?protocol_uuid=p');await h.render('/epochs/a?protocol_uuid=p',7);
  await h.render('/epochs/a?protocol_uuid=q',7);assert.equal(h.current.data,null);assert.equal(h.requests.length,0);
  await h.render('/epochs/a?protocol_uuid=p',8);assert.equal(h.current.data,null);await h.tick(80);
  assert.deepEqual(h.requests.map(item=>item.path),['/epochs/a?protocol_uuid=p','/epochs/a/trace?stream_uuid=stream-a&start=0&count=3']);
  assert.equal(h.current.data.epoch_uuid,'a');h.requests.length=0;
  await h.reload();assert.equal(h.current.data,null);assert.equal(h.cache.peek('/epochs/a?protocol_uuid=p',8),undefined);
  assert.equal(h.cache.peek('/epochs/a/trace?stream_uuid=stream-a&start=0&count=3',8),undefined);
  await h.tick(79);assert.equal(h.requests.length,0);await h.tick(1);assert.equal(h.requests.length,2);
 }finally{await h.close();}
});
test('candidate reads never consume global warmth; superseded late trace completion stays fenced',async t=>{
 const h=await harness(t);let finish;
 try{
  h.warm('a');const candidate='/protocols/p/workbench/candidates/r/epochs/a?candidate_scope_revision=token';
  h.respond=()=>metadata('a');await h.render(candidate);assert.equal(h.current.data,null);await h.tick(80);
  assert.deepEqual(h.requests.map(item=>item.path),[candidate]);assert.equal(h.cache.peek(candidate,0),undefined);
  h.cache.put('/epochs/b',0,metadata('b'));h.respond=()=>new Promise(resolve=>finish=resolve);
  await h.render('/epochs/b');await h.tick(80);const obsolete=h.requests.at(-1);
  assert.match(obsolete.path,/\/epochs\/b\/trace/);await h.render('/epochs/a');assert.equal(h.current.data.epoch_uuid,'a');assert.equal(obsolete.signal.aborted,true);
  await act(async()=>finish(trace('b')));assert.equal(h.current.data.epoch_uuid,'a');
  assert.equal(h.cache.peek('/epochs/b/trace?stream_uuid=stream-b&start=0&count=3',0),undefined);
 }finally{await h.close();}
});
