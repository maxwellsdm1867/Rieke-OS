import test from 'node:test';
import assert from 'node:assert/strict';
import {createTreeBranchReadCache as createCache} from './treeBranchReadCache.js';
import {onlineManager,focusManager,timeoutManager} from '@tanstack/react-query';
// Query GC timers must not keep the Node test runner alive. Browser timers are unchanged.
timeoutManager.setTimeoutProvider({setTimeout:(callback,delay)=>setTimeout(callback,delay).unref(),clearTimeout,setInterval:(callback,delay)=>setInterval(callback,delay).unref(),clearInterval});
const owned=new Set();
const createTreeBranchReadCache=options=>{const cache=createCache(options);owned.add(cache);return cache;};
test.afterEach(async()=>{await new Promise(resolve=>setImmediate(resolve));for(const cache of owned)cache.retire();owned.clear();onlineManager.setOnline(true);focusManager.setFocused(undefined);});
const hex=n=>String(n).repeat(64),protocol='00000000-0000-4000-8000-000000000001';
const scope={projectUuid:'project-A',projectPath:'/owned/A',actorId:'actor-A',activation:'renderer-A',revision:1};
const body={protocol_uuid:protocol,filters:{},splits:'date,cell',path:[],offset:0,limit:60,revision:hex(1)};
const identity={version:1,project_uuid:scope.projectUuid,project_path:scope.projectPath,protocol_uuid:protocol,tree_revision:hex(1),generation:{metadata:hex(2),typed:hex(3),source:hex(4),annotation:hex(5),binding:hex(6),publication:'backend-A'}};
const page={kind:'branches',revision:hex(1),path:[],offset:0,limit:60,depth:0,split_order:['date','cell'],total:1,total_epochs:4,cells:1,count:4,duration_seconds:1,selection:{count:4},levels:[{field:'date'},{field:'cell'}],ancestors:[],epochs:[],branches:[{key:hex(7),path:[hex(7)],value:'2026-10-03',count:4,cells:1}],has_more:false,read_identity:identity};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const attest=(cache,response=page,request=body)=>cache.attest(scope,request,response);

test('only a current complete backend witness permits exact nonterminal ancestor reuse',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);let requests=0;
 const load=async()=>{requests++;return page;};
 assert.equal(attest(cache,{...page,read_identity:undefined}),null);
 const lease=attest(cache);await cache.read(lease,body,{load});
 const second=attest(cache);const hit=await cache.read(second,body,{load});
 assert.equal(requests,1);assert.equal(hit.branches[0].value,'2026-10-03');assert.ok(Object.isFrozen(hit.branches[0]));
 assert.equal(cache.stats().hits,1);
});

test('annotation, backend incarnation, project path, actor and binding changes cannot share results',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);let requests=0;
 let current=page;const load=async()=>{requests++;return current;};
 await cache.read(attest(cache),body,{load});
 for(const key of ['annotation','publication','binding','source','metadata','typed']){
  current={...page,read_identity:{...identity,generation:{...identity.generation,[key]:key+'-changed'}}};
  await cache.read(attest(cache,current),body,{load});
 }
 assert.equal(requests,7);
 for(const key of ['actorId','projectPath','projectUuid','activation','revision']){
  cache.activate({...scope,[key]:'changed'});
  assert.equal(attest(cache),null);
  cache.activate(scope);
 }
 assert.equal(cache.stats().entries,0);
});

import {loadColumnTreePages} from './columnTreeReads.js';
const ownerFor=cache=>({active:()=>cache.isActive(scope),attest:(request,response)=>cache.attest(scope,request,response),read:(...args)=>cache.read(...args),current:lease=>cache.assertCurrent(lease)});
function ancestor(request,readIdentity=identity){return {...page,path:request.path,depth:request.path.length,offset:request.offset,read_identity:readIdentity,branches:[{...page.branches[0],key:hex(7+request.path.length),path:[...request.path,hex(7+request.path.length)]}]};}
const leaf={...page,kind:'epochs',path:[hex(7),hex(8)],depth:2,branches:[],epochs:[{epoch_uuid:'epoch-A'}],ancestors:[{parent_offset:0},{parent_offset:0}]};

test('return performs fresh anchor and reuses two identical branch POSTs; terminal is never cached',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);const calls=[];
 const load=async(url,options)=>{calls.push({url,body:options.body});return options.body.anchor_uuid?leaf:ancestor(options.body);};
 const args={scope:{protocolId:protocol,splits:'date,cell'},anchor:'epoch-A',readOwner:ownerFor(cache),load};
 const first=await loadColumnTreePages(args);assert.equal(first.length,3);assert.equal(calls.length,3);
 const second=await loadColumnTreePages(args);assert.equal(calls.length,4);assert.equal(calls.at(-1).body.anchor_uuid,'epoch-A');
 assert.equal(cache.stats().entries,2);assert.equal(cache.stats().hits,2);assert.deepEqual(second,first);
});

test('no backend witness means fresh ancestors; changed witness cannot be stamped onto old responses',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);let calls=0;
 let missing=true;const load=async(url,{body:request})=>{calls++;const response=request.anchor_uuid?leaf:ancestor(request);return missing?{...response,read_identity:undefined}:request.anchor_uuid?{...leaf,read_identity:{...identity,generation:{...identity.generation,annotation:'changed'}}}:response;};
 const args={scope:{protocolId:protocol,splits:'date,cell'},anchor:'epoch-A',readOwner:ownerFor(cache),load};
 await loadColumnTreePages(args);await loadColumnTreePages(args);assert.equal(calls,6);assert.equal(cache.stats().entries,0);
 missing=false;await assert.rejects(loadColumnTreePages(args),/identity changed/);assert.equal(cache.stats().entries,0);
});

test('complete body keys separate offsets, opaque paths and typed values; forbidden scopes fail closed',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);let count=0;
 const load=async(_,{body:request})=>{count++;return ancestor(request);};const lease=attest(cache);
 await cache.read(lease,body,{load});await cache.read(lease,{...body,offset:60},{load});await cache.read(lease,{...body,path:[hex(7)]},{load});assert.equal(count,3);
 for(const changes of [{anchor_uuid:'epoch-A'},{path:[hex(7),hex(8)]},{filters:{cell_type:'A'}},{predicate:{all:[]}},{candidate_scope_revision:'frozen'},{protocol_uuid:'other'},{revision:hex(9)},{splits:'cell,date'},{limit:61}])await assert.rejects(cache.read(lease,{...body,...changes},{load}),/outside/);
 assert.equal(count,3);
});

test('coalesced subscribers cancel independently and retired abort-ignoring work cannot publish',async()=>{
 const cache=createTreeBranchReadCache({inflight:1});cache.activate(scope);const hold=deferred();let calls=0;
 const load=()=>{calls++;return hold.promise;},a=new AbortController(),b=new AbortController(),lease=attest(cache);
 const one=cache.read(lease,body,{load,signal:a.signal}),two=cache.read(lease,body,{load,signal:b.signal});await Promise.resolve();
 a.abort();await assert.rejects(one,{name:'AbortError'});assert.equal(calls,1);
 cache.retire();await assert.rejects(two,{name:'AbortError'});cache.activate(scope);
 await assert.rejects(cache.read(attest(cache),body,{load}),/capacity/);assert.equal(cache.stats().inflight,1);
 hold.resolve(page);await new Promise(resolve=>setImmediate(resolve));assert.equal(cache.stats().entries,0);assert.equal(cache.stats().inflight,0);
 await cache.read(attest(cache),body,{load:async()=>page});assert.equal(cache.stats().entries,1);
});

test('entry/byte/age/lease bounds, LRU and oversized responses cannot leave old entries',async()=>{
 let clock=0;const cache=createTreeBranchReadCache({entries:1,bytes:10000,retainMs:20,leaseMs:10,now:()=>clock});cache.activate(scope);
 await cache.read(attest(cache),body,{load:async()=>page});
 await cache.read(attest(cache),{...body,offset:60},{load:async()=>({...page,offset:60})});assert.equal(cache.stats().entries,1);assert.equal(cache.stats().evictions,1);
 const old=attest(cache);clock=11;await assert.rejects(cache.read(old,body,{load:async()=>page}),{name:'StaleTreeReadError'});
 clock=21;assert.equal(cache.stats().entries,0);
 await cache.read(attest(cache),body,{load:async()=>({...page,note:'x'.repeat(11000)})});assert.equal(cache.stats().entries,0);assert.equal(cache.stats().oversized,1);assert.ok(cache.stats().bytes<=10000);
});

test('late target success/error after newer intent causes no ancestor reads or cache insertion',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);
 for(const reject of [false,true]){
  const hold=deferred();let current=true,calls=0;
  const result=loadColumnTreePages({scope:{protocolId:protocol,splits:'date,cell'},anchor:'epoch-A',readOwner:ownerFor(cache),isCurrent:()=>current,load:()=>{calls++;return hold.promise;}});
  current=false;reject?hold.reject(Error('old failure')):hold.resolve(leaf);
  await assert.rejects(result);assert.equal(calls,1);assert.equal(cache.stats().entries,0);
 }
});


test('local reads run offline; focus/reconnect do not refetch and failures retry only on explicit intent',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);cache.client.mount();
 try{
  onlineManager.setOnline(false);let calls=0;
  const load=async()=>{calls++;if(calls===1)throw Error('owned fixture failure');return page;};
  await assert.rejects(cache.read(attest(cache),body,{load}),/fixture failure/);
  assert.equal(calls,1);assert.equal(cache.client.getQueryCache().getAll().length,0);
  await cache.read(attest(cache),body,{load});assert.equal(calls,2);
  focusManager.setFocused(false);focusManager.setFocused(true);onlineManager.setOnline(true);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,2);
  cache.retire();cache.activate(scope);assert.equal(cache.stats().entries,0);
  await cache.read(attest(cache),body,{load});assert.equal(calls,3);
 }finally{cache.client.unmount();}
});

test('last observer cancellation consumes the query signal and removes inactive query storage',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);const hold=deferred(),controller=new AbortController();let transportSignal;
 const result=cache.read(attest(cache),body,{signal:controller.signal,load:(_,{signal})=>{transportSignal=signal;return hold.promise;}});
 controller.abort();await assert.rejects(result,{name:'AbortError'});assert.equal(transportSignal.aborted,true);
 assert.equal(cache.client.getQueryCache().getAll().length,0);assert.equal(cache.stats().inflight,1);
 hold.resolve(page);await new Promise(resolve=>setImmediate(resolve));assert.equal(cache.stats().inflight,0);assert.equal(cache.stats().entries,0);
});

import React,{act as domAct} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
test('mounted current lease expiry clears loading and explicit retry obtains a fresh witness',async()=>{
 let clock=0,calls=0,witnesses=0;const retryBodies=[];const hold=deferred(),cache=createTreeBranchReadCache({now:()=>clock});cache.activate(scope);
 const key='__treeLeaseFixture';globalThis[key]={owner:{...ownerFor(cache),identity:'fixture',attest:(request,response)=>{witnesses++;return cache.attest(scope,request,response);}},
  api:async(_,{body:request})=>{retryBodies.push(request);if((request.path.length||request.offset)&&!request.revision)throw Error('A tree revision is required for continuation pages');calls++;return calls===1?leaf:calls===2?hold.promise:request.anchor_uuid||request.path.length===2?leaf:ancestor(request);}};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
  name:'lease-fixture',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/components/ColumnTree.jsx')){
   if(id==='../api.js')return '\0lease-api';if(id==='../tree-ancestors/treeBranchReads.jsx')return '\0lease-owner';
   if(id==='./TreeGroupTags.jsx'||id==='./IncomingTreeSelection.jsx')return '\0lease-actions';
  }},load(id){if(id==='\0lease-api')return `export const api=(...args)=>globalThis.${key}.api(...args),number=String,duration=String;`;
   if(id==='\0lease-owner')return `export const useTreeBranchReads=()=>globalThis.${key}.owner;`;
   if(id==='\0lease-actions')return 'export const useTreeGroupTags=()=>({revision:0}),useIncomingTreeSelection=()=>({}),TreeGroupTagButton=()=>null,IncomingEpochSelect=()=>null;';}
 }]});let view;
 const oldRaf=globalThis.requestAnimationFrame,oldCancel=globalThis.cancelAnimationFrame;
 globalThis.requestAnimationFrame=()=>0;globalThis.cancelAnimationFrame=()=>{};
 try{
  const {default:ColumnTree}=await server.ssrLoadModule('/src/components/ColumnTree.jsx');
  await act(async()=>{view=TestRenderer.create(React.createElement(ColumnTree,{protocolId:protocol,splits:'date,cell',selected:'epoch-A'}));});
  assert.equal(calls,3);clock=10001;
  await act(async()=>{hold.resolve(ancestor(body));await new Promise(resolve=>setImmediate(resolve));});
  assert.equal(view.root.findByProps({'aria-label':'Tree column overview'}).props['aria-busy'],false);
  assert.match(view.root.findByProps({role:'alert'}).children[0],/expired/);
  await act(async()=>{view.root.findByProps({role:'alert'}).findByType('button').props.onClick();});
  assert.equal(witnesses,2);assert.equal(retryBodies[3].anchor_uuid,'epoch-A','retry preserves the failed anchored intent');assert.equal(retryBodies[3].revision,undefined,'retry requests fresh authority');assert.equal(view.root.findAllByProps({role:'alert'}).length,0);
  assert.equal(view.root.findByProps({'aria-label':'Tree column overview'}).props['aria-busy'],false);
  assert.equal(view.root.findByProps({'data-epoch-uuid':'epoch-A'}).props.disabled,false);
  const successfulApi=globalThis[key].api;let failedBody;
  globalThis[key].api=async(_,{body:request})=>{failedBody=request;retryBodies.push(request);throw Error('fixture 503');};
  await act(async()=>view.root.findAll(node=>node.type==='button'&&node.props.className?.includes('tp-branch')).at(-1).props.onClick());
  assert.equal(failedBody.anchor_uuid,undefined,'deliberate branch navigation is not selected-epoch navigation');
  const deliberatePath=failedBody.path;globalThis[key].api=successfulApi;const retryStart=retryBodies.length;
  await act(async()=>view.root.findByProps({role:'alert'}).findByType('button').props.onClick());
  assert.deepEqual(retryBodies[retryStart].path,[]);assert.equal(retryBodies[retryStart].revision,undefined);assert.deepEqual(retryBodies[retryStart+1].path,deliberatePath);assert.equal(retryBodies[retryStart+1].anchor_uuid,undefined);assert.equal(retryBodies[retryStart+1].revision,hex(1));
  globalThis[key].api=async(_,{body:request})=>{retryBodies.push(request);throw Error('fixture 503');};
  await act(async()=>view.update(React.createElement(ColumnTree,{protocolId:protocol,splits:'date,cell',selected:'epoch-B'})));
  const obsoleteRetry=view.root.findByProps({role:'alert'}).findByType('button').props.onClick;
  await act(async()=>view.update(React.createElement(ColumnTree,{protocolId:protocol,splits:'date,cell',filters:{cell_type:'changed'},selected:'epoch-C'})));
  const beforeObsolete=retryBodies.length;await act(async()=>obsoleteRetry());assert.equal(retryBodies.length,beforeObsolete,'old scope retry cannot replay into a new filter');
  let frozenRefreshes=0;
  await act(async()=>view.update(React.createElement(ColumnTree,{protocolId:protocol,splits:'date,cell',expectedRevision:'frozen',readContext:{root:'/frozen'},onRefreshPreview:()=>frozenRefreshes++})));
  const beforeFrozen=retryBodies.length;await act(async()=>view.root.findByProps({role:'alert'}).findByType('button').props.onClick());assert.equal(frozenRefreshes,1);assert.equal(retryBodies.length,beforeFrozen,'frozen refresh stays delegated');
  const obsoleteFrozen=view.root.findByProps({role:'alert'}).findByType('button').props.onClick;
  await act(async()=>view.update(React.createElement(ColumnTree,{protocolId:protocol,splits:'date,cell',filters:{cell_type:'live'},onRefreshPreview:()=>frozenRefreshes++})));
  const beforeOldFrozen=retryBodies.length;await act(async()=>obsoleteFrozen());assert.equal(frozenRefreshes,1);assert.equal(retryBodies.length,beforeOldFrozen,'old frozen refresh cannot target a replacement scope');
 }finally{await act(async()=>view?.unmount());await server.close();delete globalThis[key];globalThis.requestAnimationFrame=oldRaf;globalThis.cancelAnimationFrame=oldCancel;}
});

test('one retained tree keeps mounted rows while hidden, aborts reads, fences actions, and freshly validates return',async()=>{
 const cache=createTreeBranchReadCache();cache.activate(scope);let calls=0,selected=0,hold=null,lastSignal;const requests=[];const statuses=[];
 const key='__retainedTreeFixture';globalThis[key]={owner:{...ownerFor(cache),identity:'owner-A'},api:async(_,{body:request,signal})=>{lastSignal=signal;calls++;requests.push(request);if(hold)return hold.promise;return request.anchor_uuid||request.path.length===2?{...leaf,offset:request.offset,has_more:!request.offset,total:120,epochs:[{epoch_uuid:request.anchor_uuid||'epoch-A'}]}:ancestor(request);}};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
  name:'retained-fixture',enforce:'pre',resolveId(id,importer){
   if(id==='../tree-ancestors/treeBranchReads.jsx'&&/\/(ColumnTree|RetainedTreePresentation)\.jsx$/.test(importer||''))return '\0retained-owner';
   if(id==='../api.js'&&/\/(ColumnTree|PagedTree)\.jsx$/.test(importer||''))return '\0retained-api';
   if(importer?.endsWith('/components/ColumnTree.jsx')&&(id==='./TreeGroupTags.jsx'||id==='./IncomingTreeSelection.jsx'))return '\0retained-actions';
  },load(id){if(id==='\0retained-owner')return `export const useTreeBranchReads=()=>globalThis.${key}.owner;`;
   if(id==='\0retained-api')return `export const api=(...args)=>globalThis.${key}.api(...args),number=String,duration=String;`;
   if(id==='\0retained-actions')return 'export const useTreeGroupTags=()=>({revision:0}),useIncomingTreeSelection=()=>({}),TreeGroupTagButton=()=>null,IncomingEpochSelect=()=>null;';}
 }]});const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'}),priorWindow=globalThis.window,priorDocument=globalThis.document;globalThis.window=dom.window;globalThis.document=dom.window.document;const container=document.getElementById('root');const view=createRoot(container);
 const oldRaf=globalThis.requestAnimationFrame,oldCancel=globalThis.cancelAnimationFrame;const frames=new Map();let frameId=0;globalThis.requestAnimationFrame=fn=>{frames.set(++frameId,fn);return frameId;};globalThis.cancelAnimationFrame=id=>frames.delete(id);
 const flushFrames=async()=>domAct(async()=>{const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn());});
 Object.defineProperty(dom.window.HTMLElement.prototype,'clientHeight',{get:()=>50,configurable:true});
 dom.window.HTMLElement.prototype.getBoundingClientRect=function(){const pane=this.closest('.tp-column-content');const top=this.matches('.tp-epoch,.tp-branch')?7-(pane?.scrollTop||0):0;return {top,bottom:top+20,left:0,right:100,width:100,height:20};};
 try{
  const {default:Host}=await server.ssrLoadModule('/src/components/RetainedTreePresentation.jsx');
  const {default:Layout}=await server.ssrLoadModule('/src/components/EpochBrowserLayout.jsx');
  const tree={protocolId:protocol,splits:'date,cell',revision:1,selected:'epoch-A',onSelectEpoch:()=>selected++,onStatus:value=>statuses.push(value)};
  const committedLabels=[];function LabelProbe({active}){React.useLayoutEffect(()=>{if(active)committedLabels.push(container.querySelector('[data-retained-tree-status]')?.textContent||'');});return null;}
  const render=async(active,changes={})=>domAct(async()=>{view.render(React.createElement(Layout,{retainDetail:true,editing:active,sizes:{},treeOpen:false,metadataOpen:false,detail:React.createElement(React.Fragment,null,React.createElement(Host,{active,tree:{...tree,...changes}}),React.createElement(LabelProbe,{active}))}));await new Promise(resolve=>setImmediate(resolve));});
  await render(true);for(let retry=0;retry<30&&!container.querySelector('[data-epoch-uuid="epoch-A"]');retry++)await domAct(async()=>{await new Promise(resolve=>setTimeout(resolve,20));});
  const row=container.querySelector('[data-epoch-uuid="epoch-A"]'),count=calls;assert.ok(row,container.innerHTML);await flushFrames();
  await domAct(async()=>{[...container.querySelectorAll('.tp-column-content')].forEach((pane,i)=>{pane.scrollTop=[40,60,120][i];pane.dispatchEvent(new dom.window.Event('scroll',{bubbles:true}));});});
  await render(false);assert.equal(container.querySelector('[data-epoch-uuid="epoch-A"]'),row);assert.equal(calls,count);
  assert.equal(container.querySelector('.tree-view-workspace').style.display,'none','Activity hides retained DOM');
  await domAct(async()=>row.click());assert.equal(selected,0);
  hold=deferred();await render(true,{readPending:true});assert.match(committedLabels.at(-1),/Refreshing/,'first visible commit must label retained rows before passive effects');assert.equal(container.querySelector('[data-epoch-uuid="epoch-A"]'),row);assert.equal(row.disabled,true);assert.equal(calls,count+1);
  assert.match(container.textContent,/previous view/);await domAct(async()=>row.click());assert.equal(selected,0);
  const pendingSignal=lastSignal;await render(false);assert.equal(pendingSignal.aborted,true);const statusCount=statuses.length;
  await domAct(async()=>{hold.resolve(leaf);hold=null;await new Promise(resolve=>setImmediate(resolve));});assert.equal(statuses.length,statusCount,'hidden late success cannot publish');
  await render(true);assert.equal(container.querySelector('[data-epoch-uuid="epoch-A"]').disabled,false);await flushFrames();
  assert.deepEqual([...container.querySelectorAll('.tp-column-content')].map(p=>p.scrollTop),[40,60,120],'exact return preserves manual offsets after canceled work and selected-row RAF');
  // A newer manual scroll during revalidation takes precedence over its snapshot.
  await render(false);hold=deferred();await render(true);
  await domAct(async()=>{const pane=container.querySelectorAll('.tp-column-content')[2];pane.scrollTop=180;pane.dispatchEvent(new dom.window.Event('scroll',{bubbles:true}));});
  await domAct(async()=>{hold.resolve({...leaf,has_more:true,total:120});hold=null;await new Promise(resolve=>setImmediate(resolve));});await flushFrames();
  assert.equal(container.querySelectorAll('.tp-column-content')[2].scrollTop,180,'pending refresh must not override newer manual scroll');
  // Explicit pagination must reset; it is not a return restoration.
  await domAct(async()=>container.querySelector('[aria-label="Next page in column 3"]').click());await flushFrames();
  assert.equal(requests.at(-1).offset,60);assert.equal(container.querySelectorAll('.tp-column-content')[2].scrollTop,0);
  await render(false);await render(true,{selected:'epoch-B'});await flushFrames();
  assert.ok(container.querySelector('[data-epoch-uuid="epoch-B"]'));assert.equal(container.querySelectorAll('.tp-column-content')[2].scrollTop,0,'new focus must not inherit prior offsets');
  await render(false,{selected:'epoch-B'});await render(true,{selected:'epoch-B',filters:{cell_type:'new'}});await flushFrames();
  assert.equal(container.querySelectorAll('.tp-column-content')[2].scrollTop,0,'changed scope must not inherit prior offsets');

  const currentView={selected:'epoch-B',filters:{cell_type:'new'}};
  const retainedRow=container.querySelector('[data-epoch-uuid="epoch-B"]');assert.ok(retainedRow);
  await render(false,currentView);
  assert.equal(container.querySelector('[data-epoch-uuid="epoch-B"]'),retainedRow,'same view must retain its row immediately before owner eviction');
  globalThis[key].owner={...globalThis[key].owner,identity:'owner-B'};
  await render(false,currentView);
  assert.equal(container.querySelector('[data-epoch-uuid="epoch-B"]'),null,'changing only owner evicts the retained row');
  await render(true,currentView);
  assert.ok(container.querySelector('[data-epoch-uuid="epoch-B"]'),'new owner mounts the current view before the independent filter eviction');
  await render(false,{...currentView,filters:{cell_type:'other'}});
  assert.equal(container.querySelector('[data-epoch-uuid="epoch-B"]'),null);
 }finally{await domAct(async()=>view.unmount());await server.close();delete globalThis[key];globalThis.requestAnimationFrame=oldRaf;globalThis.cancelAnimationFrame=oldCancel;dom.window.close();globalThis.window=priorWindow;globalThis.document=priorDocument;}

});


test('fresh continuation retry obtains root revision before branch/pagination and stops on supersession',async()=>{
 for(const continuation of [{path:[hex(7)],offset:0},{path:[],offset:60}]){
  const requests=[];const load=async(_,{body:request})=>{requests.push(request);if((request.path.length||request.offset)&&!request.revision)throw Error('A tree revision is required for continuation pages');return ancestor(request);};
  await loadColumnTreePages({scope:{protocolId:protocol,splits:'date,cell'},...continuation,freshContinuation:true,load});
  assert.deepEqual(requests[0].path,[]);assert.equal(requests[0].offset,0);assert.equal(requests[0].revision,undefined);
  assert.deepEqual(requests[1].path,continuation.path);assert.equal(requests[1].offset,continuation.offset);assert.equal(requests[1].revision,hex(1));
 }
 const hold=deferred();let current=true,calls=0;
 const work=loadColumnTreePages({scope:{protocolId:protocol,splits:'date,cell'},path:[hex(7)],freshContinuation:true,isCurrent:()=>current,load:()=>{calls++;return hold.promise;}});
 current=false;hold.resolve(page);await assert.rejects(work,{name:'AbortError'});assert.equal(calls,1);
});
