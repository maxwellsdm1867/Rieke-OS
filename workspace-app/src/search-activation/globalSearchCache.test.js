import test from 'node:test';
import assert from 'node:assert/strict';
import {createGlobalSearchHarness} from '../test-support/globalSearchHarness.js';

const rows=h=>h.root.findAllByProps({className:'global-search-result'});
const open=h=>h.act(()=>h.root.findByProps({'aria-label':'Search project metadata and UUIDs'}).props.onClick());
const close=h=>h.act(()=>h.root.findByProps({'aria-label':'Close search'}).props.onClick());
const query=(h,value)=>h.act(()=>h.root.findByProps({'aria-label':'Search UUID, field, or typed value'}).props.onChange({target:{value}}));
const settle=(h,count)=>h.waitFor(()=>h.fixture.requests.length===count&&rows(h).length===1&&!rows(h)[0].props.disabled);
const deferred=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes;});return {promise,resolve};};
const result=id=>({results:[{kind:'cell',id,cell_uuid:id,label:`Synthetic ${id}`}],total:1});

test('warm reopen renders immediately and adds zero GETs against two checkpoint GETs',async()=>{
 const h=await createGlobalSearchHarness();
 try{await h.render();await open(h);await query(h,'CellA');await settle(h,1);await close(h);await open(h);
   assert.equal(rows(h).length,1);assert.equal(rows(h)[0].props.disabled,false);
   await h.act(()=>new Promise(resolve=>setTimeout(resolve,220)));
   assert.equal(h.fixture.requests.length,1);assert.equal(h.fixture.cache.stats().entries,1);
 }finally{await h.close();}
});

test('expired compatible content is inert during refresh, ordinary error is explicit, empty success replaces',async()=>{
 const h=await createGlobalSearchHarness();
 try{h.fixture.at=0;await h.render();await open(h);await query(h,'CellA');await settle(h,1);await close(h);
   const held=deferred();h.fixture.at=31000;h.fixture.respond=()=>held.promise;await open(h);
   assert.equal(rows(h).length,1);assert.equal(rows(h)[0].props.disabled,true);
   await h.waitFor(()=>h.fixture.requests.length===2);held.resolve({fixtureStatus:503,error:'Fixture offline'});
   await h.waitFor(()=>h.root.findAllByProps({role:'alert'}).length===1);
   assert.equal(rows(h).length,1);assert.equal(rows(h)[0].props.disabled,true);
   assert.match(h.root.findByProps({role:'alert'}).children.join(' '),/Fixture offline/);
   h.fixture.respond=()=>({results:[],total:0});await h.act(()=>h.root.findByProps({children:'Retry search'}).props.onClick());
   await h.waitFor(()=>h.fixture.requests.length===3&&rows(h).length===0&&h.root.findAllByProps({role:'alert'}).length===0);
   assert.equal(h.fixture.cache.stats().entries,1);
 }finally{await h.close();}
});

test('409 clears old rows, never auto retries, and explicit retry reads again',async()=>{
 const h=await createGlobalSearchHarness();
 try{h.fixture.at=0;await h.render();await open(h);await query(h,'CellA');await settle(h,1);await close(h);
   h.fixture.at=31000;h.fixture.respond=()=>({fixtureStatus:409,error:'Fixture stale authority'});await open(h);
   await h.waitFor(()=>h.root.findAllByProps({role:'alert'}).length===1);
   assert.equal(rows(h).length,0);assert.equal(h.fixture.cache.stats().entries,0);
   await h.act(()=>new Promise(resolve=>setTimeout(resolve,220)));assert.equal(h.fixture.requests.length,2);
   h.fixture.respond=()=>result('after-conflict');await h.act(()=>h.root.findByProps({children:'Retry search'}).props.onClick());await settle(h,3);
 }finally{await h.close();}
});

test('latest query/revision intent wins when older transport ignores abort',async()=>{
 const h=await createGlobalSearchHarness(),held=deferred();let chosen=[];
 try{h.fixture.respond=()=>held.promise;await h.render({onCell:row=>chosen.push(row.id)});await open(h);await query(h,'old');
   await h.waitFor(()=>h.fixture.requests.length===1);h.fixture.respond=()=>result('latest');await query(h,'new');await settle(h,2);
   const obsolete=rows(h)[0].props.onClick;
   const next=deferred();h.fixture.respond=()=>next.promise;await h.render({revision:1,onCell:row=>chosen.push(row.id)});
   assert.equal(rows(h).length,0);await h.act(obsolete);assert.deepEqual(chosen,[]);
   await h.waitFor(()=>h.fixture.requests.length===3);held.resolve(result('old'));next.resolve(result('revised'));await settle(h,3);
   assert.equal(rows(h)[0].findByType('strong').children[0],'Synthetic revised');
   assert.equal(h.fixture.requests[0].signal.aborted,true);
 }finally{await h.close();}
});

test('same entity UUID cannot cross project, actor/provisional status, or retired activation',async()=>{
 const h=await createGlobalSearchHarness();let chosen=[];
 try{await h.render({onCell:row=>chosen.push(row.id)});await open(h);await query(h,'CellA');await settle(h,1);
   let obsolete=rows(h)[0].props.onClick;
   for(const [index,scope] of [{projectId:'synthetic-project-b'},{projectId:'synthetic-project-b',actorId:'profile-loading'},{projectId:'synthetic-project-b',actorId:'profile-unavailable'},{projectId:'synthetic-project-b',actorId:'synthetic-actor-b'}].entries()){
     await h.render({...scope,onCell:row=>chosen.push(row.id)});assert.equal(rows(h).length,0);await h.act(obsolete);assert.deepEqual(chosen,[]);await settle(h,index+2);obsolete=rows(h)[0].props.onClick;
   }
   for(const [index,event] of ['online','focus','pageshow'].entries()){
     await h.event(event);assert.equal(rows(h).length,0);await h.act(obsolete);assert.deepEqual(chosen,[]);await settle(h,index+6);obsolete=rows(h)[0].props.onClick;
   }
   assert.equal(h.fixture.cache.stats().entries,1);
 }finally{await h.close();}
});

test('close/unmount cancels held reads, late transport cannot publish, no-project dispatches nothing',async()=>{
 const h=await createGlobalSearchHarness(),held=deferred();
 try{await h.render({projectId:null});await open(h);await query(h,'CellA');await h.act(()=>new Promise(resolve=>setTimeout(resolve,220)));assert.equal(h.fixture.requests.length,0);
   h.fixture.respond=()=>held.promise;await h.render();await h.waitFor(()=>h.fixture.requests.length===1);await close(h);assert.equal(h.fixture.requests[0].signal.aborted,true);
   await h.unmount();held.resolve(result('late'));await h.act(()=>new Promise(resolve=>setTimeout(resolve,10)));
   assert.equal(h.fixture.cache.stats().entries,0);assert.equal(h.fixture.cache.stats().inflight,0);
 }finally{await h.close();}
});

test('same UUID with a different open identity and desktop backend lifecycle retires reads',async()=>{
 const h=await createGlobalSearchHarness();let chosen=[];
 try{await h.render({onCell:row=>chosen.push(row.id)});await open(h);await query(h,'CellA');await settle(h,1);
   const obsolete=rows(h)[0].props.onClick;
   await h.render({projectOpenIdentity:'synthetic-open-b',onCell:row=>chosen.push(row.id)});
   assert.equal(rows(h).length,0);await h.act(obsolete);assert.deepEqual(chosen,[]);await settle(h,2);
   await h.event('desktop-status',{state:'Recovery'});assert.equal(rows(h).length,0);await settle(h,3);
   await h.event('desktop-status',{state:'Recovery'});assert.equal(h.fixture.requests.length,3);
   await h.event('desktop-status',{state:'Running'});await settle(h,4);
   assert.equal(h.listenerCount('online'),1);await h.unmount();assert.equal(h.listenerCount('online'),0);assert.equal(h.listenerCount('desktop-status'),0);
 }finally{await h.close();}
});

test('freshness expiry while mounted refreshes once with previous content inert',async()=>{
 const h=await createGlobalSearchHarness({cacheOptions:{freshMs:40,retainMs:5000}}),held=deferred();
 try{h.fixture.at=0;await h.render();await open(h);await query(h,'CellA');await settle(h,1);h.fixture.respond=()=>held.promise;h.fixture.at=41;
   const obsolete=rows(h)[0].props.onClick;await h.waitFor(()=>h.fixture.requests.length===2);
   assert.equal(rows(h).length,1);assert.equal(rows(h)[0].props.disabled,true);await h.act(obsolete);
   held.resolve(result('renewed'));await settle(h,2);assert.equal(rows(h)[0].findByType('strong').children[0],'Synthetic renewed');
 }finally{await h.close();}
});

test('A to B to A reversal rejects the retired A transport even with the identical key',async()=>{
 const h=await createGlobalSearchHarness(),oldA=deferred(),b=deferred(),newA=deferred();
 try{h.fixture.respond=()=>oldA.promise;await h.render();await open(h);await query(h,'A');await h.waitFor(()=>h.fixture.requests.length===1);
   h.fixture.respond=()=>b.promise;await query(h,'B');await h.waitFor(()=>h.fixture.requests.length===2);
   h.fixture.respond=()=>newA.promise;await query(h,'A');await h.waitFor(()=>h.fixture.requests.length===3);
   oldA.resolve(result('obsolete-A'));b.resolve(result('obsolete-B'));await h.act(()=>new Promise(resolve=>setTimeout(resolve,10)));
   assert.equal(rows(h).length,0);assert.equal(h.fixture.cache.stats().entries,0);
   newA.resolve(result('current-A'));await settle(h,3);assert.equal(rows(h)[0].findByType('strong').children[0],'Synthetic current-A');
 }finally{await h.close();}
});

test('oversized refreshed result bypasses retention and cannot resurrect predecessor on reopen',async()=>{
 const h=await createGlobalSearchHarness({cacheOptions:{bytes:1000}});
 try{h.fixture.at=0;await h.render();await open(h);await query(h,'A');await settle(h,1);await close(h);
   h.fixture.at=31000;h.fixture.respond=()=>({results:[{kind:'cell',id:'B',label:'B'.repeat(2000)}],total:1});await open(h);await settle(h,2);
   assert.equal(h.fixture.cache.stats().entries,0);await close(h);h.fixture.respond=()=>result('C');await open(h);
   assert.equal(rows(h).length,0);await settle(h,3);assert.equal(rows(h)[0].findByType('strong').children[0],'Synthetic C');
 }finally{await h.close();}
});

test('App owner derives distinct loading, failed, browse-only and selected-profile namespaces',async()=>{
 const h=await createGlobalSearchHarness({workspaceOwner:true});let chosen=[];
 try{await h.render({onCell:row=>chosen.push(row.id)});await open(h);await query(h,'A');await settle(h,1);
   let obsolete=rows(h)[0].props.onClick;
   for(const [index,profile] of [{profileUuid:'author-a',loading:true,error:''},{profileUuid:'author-a',loading:false,error:'Fixture preference failed'},{profileUuid:'',loading:false,error:''},{profileUuid:'author-b',loading:false,error:''}].entries()){
     h.fixture.profile=profile;await h.render({onCell:row=>chosen.push(row.id)});assert.equal(rows(h).length,0);await h.act(obsolete);assert.deepEqual(chosen,[]);await settle(h,index+2);obsolete=rows(h)[0].props.onClick;
   }
 }finally{await h.close();}
});
