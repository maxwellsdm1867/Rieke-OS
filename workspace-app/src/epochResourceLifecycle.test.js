import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

const metadata=uuid=>({epoch_uuid:uuid,streams:[{kind:'responses',uuid:`stream-${uuid}`,sample_count:3}]});
const trace=uuid=>({epoch_uuid:uuid,stream_uuid:`stream-${uuid}`,start:0,count:3,sample_rate:10000,values:[-1,null,2]});

test('draft pause cancels old-scope delayed reads and resumes only with the new receipt',async t=>{
 const previousFetch=globalThis.fetch,requests=[];
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {useResource}=await server.ssrLoadModule('/src/api.js');
 let renderer,current,finish;globalThis.fetch=async(path,options)=>{requests.push({path,signal:options.signal});if(path.includes('in-flight'))await new Promise(resolve=>{finish=resolve;});return new Response(JSON.stringify({epoch_uuid:'a'}),{status:200});};
 t.mock.timers.enable({apis:['setTimeout']});
 function Probe({token,paused=false}){current=useResource(`/protocols/p/workbench/candidates/c/epochs/a?candidate_scope_revision=${token}`,token,80,{paused});return null;}
 const render=async props=>act(async()=>{const element=React.createElement(Probe,props);if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});
 const tick=async ms=>act(async()=>{t.mock.timers.tick(ms);for(let i=0;i<10;i++)await Promise.resolve();});
 try{
  await render({token:'old'});await tick(40);await render({token:'old',paused:true});await tick(100);assert.equal(requests.length,0,'old timer must never start during the draft write');
  await render({token:'new',paused:true});await tick(100);assert.equal(requests.length,0);
  await render({token:'new'});await tick(80);assert.equal(requests.length,1);assert.match(requests[0].path,/revision=new$/);assert.equal(current.loading,false);
  await render({token:'new',paused:true});assert.equal(current.data.epoch_uuid,'a');assert.equal(current.loading,true,'committed content is retained but inert');
  await render({token:'in-flight'});await tick(80);const obsolete=requests.at(-1);await render({token:'in-flight',paused:true});assert.equal(obsolete.signal.aborted,true);
  await act(async()=>finish());assert.equal(current.data,null,'aborted completion cannot publish');
  await render({token:'newest'});await tick(80);assert.match(requests.at(-1).path,/revision=newest$/);assert.equal(current.loading,false);
 }finally{await act(async()=>renderer?.unmount());t.mock.timers.reset();globalThis.fetch=previousFetch;await server.close();}
});
async function harness(t,{delayMs,prefetch=false}={}){
 const previousFetch=globalThis.fetch,requests=[],renders=[];
 let respond=path=>{const uuid=new URL(path,'http://fixture').pathname.split('/')[2];return path.includes('/trace?')?trace(uuid):metadata(uuid);};
 globalThis.fetch=async(url,options)=>{const path=url.slice(4);requests.push({path,signal:options.signal});return new Response(JSON.stringify(await respond(path)),{status:200});};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {useEpochResource,useEpochPrefetch}=await server.ssrLoadModule('/src/api.js');
 const {epochResourceCache:cache,initialEpochTracePath}=await server.ssrLoadModule('/src/resourceCache.js');
 t.mock.timers.enable({apis:['setTimeout']});
 let renderer,current;
 function Probe({path,revision=0}){current=useEpochResource(path,revision,delayMs);useEpochPrefetch(prefetch&&!path?['/epochs/a']:[],revision,0,{traces:true});renders.push({...current});return null;}
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
test('an explicitly requested delay still coalesces metadata-only misses and awaits the matching trace',async t=>{
 const h=await harness(t,{delayMs:80});let finish;
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
 const h=await harness(t,{delayMs:80});try{
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
 const h=await harness(t,{delayMs:80});let finish;
 try{
  h.warm('a');const candidate='/protocols/p/workbench/candidates/r/epochs/a?candidate_scope_revision=token';
  h.respond=()=>metadata('a');await h.render(candidate);assert.equal(h.current.data,null);await h.tick(80);
  assert.deepEqual(h.requests.map(item=>item.path),[candidate]);assert.equal(h.cache.peek(candidate,0),undefined);
  h.cache.put('/epochs/b',0,metadata('b'));h.respond=()=>new Promise(resolve=>finish=resolve);
  await h.render('/epochs/b');await h.tick(80);const obsolete=h.requests.at(-1);
  assert.match(obsolete.path,/\/epochs\/b\/trace/);await h.render('/epochs/a');assert.equal(h.current.data.epoch_uuid,'a');await h.tick(0);assert.equal(obsolete.signal.aborted,true);
  await act(async()=>finish(trace('b')));assert.equal(h.current.data.epoch_uuid,'a');
  assert.equal(h.cache.peek('/epochs/b/trace?stream_uuid=stream-b&start=0&count=3',0),undefined);
 }finally{await h.close();}
});

test('uncached epoch navigation starts metadata and then trace without advancing a timer',async t=>{
 const h=await harness(t),pending=new Map();
 try{
  h.respond=path=>new Promise(resolve=>pending.set(path,resolve));
  await h.render('/epochs/a');
  assert.deepEqual(h.requests.map(item=>item.path),['/epochs/a']);
  assert.equal(h.current.data,null);
  await act(async()=>pending.get('/epochs/a')(metadata('a')));
  const tracePath='/epochs/a/trace?stream_uuid=stream-a&start=0&count=3';
  assert.deepEqual(h.requests.map(item=>item.path),['/epochs/a',tracePath]);
  assert.equal(h.current.data,null,'metadata cannot publish as a complete trace snapshot');
  await act(async()=>pending.get(tracePath)(trace('a')));
  assert.equal(h.current.data.epoch_uuid,'a');assert.equal(h.current.loading,false);
 }finally{await h.close();}
});

test('immediate rapid navigation aborts obsolete reads and rejects late trace publication',async t=>{
 const h=await harness(t),pending=new Map();
 try{
  for(const uuid of ['a','b','c'])h.cache.put(`/epochs/${uuid}`,0,metadata(uuid));
  h.respond=path=>new Promise(resolve=>pending.set(path,resolve));
  for(const uuid of ['a','b','c'])await h.render(`/epochs/${uuid}`);
  assert.equal(h.requests.length,3,'each new intent begins without advancing timers');
  await h.tick(0); // End the bounded prefetch-to-foreground handoff turn.
  assert.deepEqual(h.requests.map(item=>item.signal.aborted),[true,true,false]);
  await act(async()=>pending.get(h.requests[2].path)(trace('c')));
  assert.equal(h.current.data.epoch_uuid,'c');
  await act(async()=>{pending.get(h.requests[1].path)(trace('b'));pending.get(h.requests[0].path)(trace('a'));});
  assert.equal(h.current.data.epoch_uuid,'c');
  for(const obsolete of h.requests.slice(0,2))assert.equal(h.cache.peek(obsolete.path,0),undefined);
 }finally{await h.close();}
});

test('actual hook transition adopts the prefetched trace without a duplicate request',async t=>{
 const h=await harness(t,{prefetch:true});let finish;
 try{
  h.respond=path=>path.includes('/trace?')?new Promise(resolve=>finish=resolve):metadata('a');
  await h.render(null);await h.tick(0);
  assert.equal(h.requests.length,2);const traceRequest=h.requests[1];
  await h.render('/epochs/a');await h.tick(0);
  assert.equal(h.requests.length,2,'prefetch and foreground must share the pending trace');
  assert.equal(traceRequest.signal.aborted,false);
  await act(async()=>finish(trace('a')));
  assert.equal(h.current.data.epoch_uuid,'a');assert.equal(h.current.loading,false);
 }finally{await h.close();}
});
