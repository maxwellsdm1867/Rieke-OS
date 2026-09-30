import test from 'node:test';
import assert from 'node:assert/strict';
import {releaseLink,updateNotice,updateLabel,watchAppUpdates,mergeUpdateCheck} from './appUpdates.js';
test('only an available release creates an update indicator',()=>{
  for(const state of ['unavailable','unconfigured','error','up_to_date'])assert.equal(updateNotice({state,available:'1.0.0'}),null);
  assert.equal(updateNotice({state:'update_available',available:{version:'1.2.0'}}).version,'1.2.0');
});
test('a failed refresh retains a known update until a successful check replaces it',()=>{
  const previous={state:'update_available',available:'1.2.0',installed:'1.1.0',
    release_url:'https://github.com/maxwellsdm1867/disco/releases/tag/v1.2.0',
    release_notes:'Changes',checked_at:'2026-09-29T00:00:00Z',can_stage:true};
  const failed=mergeUpdateCheck(previous,{state:'error',available:null,release_url:null,
    checked_at:'2026-09-29T00:15:00Z',message:'Offline',can_stage:false});
  assert.equal(updateNotice(failed).version,'1.2.0');
  assert.equal(failed.release_url,previous.release_url);
  assert.equal(failed.release_notes,previous.release_notes);
  assert.equal(failed.checked_at,previous.checked_at);
  assert.equal(failed.can_stage,false);
  assert.equal(failed.check_error,'Offline');
  for(const state of ['up_to_date','unavailable']){
    const refreshed=mergeUpdateCheck(failed,{state,available:null});
    assert.equal(updateNotice(refreshed),null);
    assert.equal(refreshed.check_error,undefined);
  }
  assert.equal(mergeUpdateCheck(null,{state:'error'}).state,'error');
  assert.equal(mergeUpdateCheck({state:'up_to_date',installed:'1.2.0'},{state:'error'}).installed,'1.2.0');
  assert.equal(updateNotice(mergeUpdateCheck(previous,{state:'update_available',available:'1.3.0'})).version,'1.3.0');
});
test('release links cannot navigate to executable or untrusted destinations',()=>{
  for(const value of ['javascript:alert(1)','https://github.com.evil.test/releases','https://github.com/other/repo/releases','https://user:password@github.com/maxwellsdm1867/disco/releases'])assert.equal(releaseLink(value),null);
  assert.ok(releaseLink('https://github.com/maxwellsdm1867/disco/releases/tag/v1.0.0'));
});
test('automatically checks at startup, periodically, and on return after elapsed interval',()=>{
  let calls=0,tick,visible,time=0,cleared=false;
  const documentObject={visibilityState:'visible',addEventListener:(event,fn)=>visible=fn,removeEventListener:()=>visible=null};
  const stop=watchAppUpdates(()=>calls++,{interval:100,now:()=>time,documentObject,setTimer:fn=>{tick=fn;return 9;},clearTimer:id=>cleared=id===9});
  assert.equal(calls,1);time=100;tick();assert.equal(calls,2);
  documentObject.visibilityState='hidden';time=200;tick();assert.equal(calls,2);
  documentObject.visibilityState='visible';visible();assert.equal(calls,3);
  time=210;visible();assert.equal(calls,3);
  stop();assert.equal(cleared,true);assert.equal(visible,null);
});
test('visible status distinguishes no releases and failed checks from up to date',()=>{
  assert.equal(updateLabel({state:'up_to_date'}),'Up to date');
  assert.equal(updateLabel({state:'unavailable'}),'No release published');
  assert.equal(updateLabel({state:'error'}),'Update check unavailable');
});

test('new update discovery is deduplicated across scans, readiness and launcher transitions',async()=>{
 const {claimUpdateDiscovery}=await import('./appUpdates.js');
 const values=new Map(),storage={getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)};
 const seen=new Set(),status={state:'Available',available:'0.2.0',channel:'unsigned-testing'};
 assert.equal(claimUpdateDiscovery(status,seen,storage),true);
 assert.equal(claimUpdateDiscovery(status,seen,storage),false);
 assert.equal(claimUpdateDiscovery({...status,state:'Ready'},new Set(),storage),false);
 assert.equal(claimUpdateDiscovery({...status,available:'0.2.1'},seen,storage),true);
 assert.equal(claimUpdateDiscovery({...status,state:'error'},seen,storage),false);
});

test('session cookie dedupes release display across origin storage and bounds retained claims',async()=>{
 const {claimUpdateDiscovery}=await import('./appUpdates.js');
 let cookie='';const documentObject={get cookie(){return cookie;},set cookie(value){cookie=value.split(';')[0];}};
 const store=()=>{const data=new Map();return{getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value)};};
 const status={state:'Available',channel:'unsigned-testing',available:'0.2.1'};
 assert.equal(claimUpdateDiscovery(status,new Set(),store(),documentObject),true);
 assert.equal(claimUpdateDiscovery(status,new Set(),store(),documentObject),false);
 for(let n=2;n<25;n++)claimUpdateDiscovery({...status,available:`0.2.${n}`},new Set(),store(),documentObject);
 const retained=JSON.parse(decodeURIComponent(cookie.split('=').slice(1).join('=')));
 assert.equal(retained.length,12);
 assert.equal(cookie.includes('Max-Age'),false);
 assert.equal(cookie.includes('Expires'),false);
});
test('unavailable cookies and storage retain component-only notification dedupe',async()=>{
 const {claimUpdateDiscovery}=await import('./appUpdates.js');const seen=new Set();
 const documentObject={get cookie(){throw new Error('cookies unavailable');},set cookie(value){throw new Error('cookies unavailable');}};
 const storage={getItem(){throw new Error('storage unavailable');},setItem(){throw new Error('storage unavailable');}};
 const status={state:'Available',available:'0.9.0'};
 assert.equal(claimUpdateDiscovery(status,seen,storage,documentObject),true);
 assert.equal(claimUpdateDiscovery(status,seen,storage,documentObject),false);
});

test('an existing origin session claim seeds the cross-port cookie without rediscovery',async()=>{
 const {claimUpdateDiscovery}=await import('./appUpdates.js');let cookie='';
 const documentObject={get cookie(){return cookie;},set cookie(value){cookie=value.split(';')[0];}};
 const status={state:'Available',available:'0.8.0'};
 assert.equal(claimUpdateDiscovery(status,new Set(),{getItem:()=> '1'},documentObject),false);
 assert.equal(claimUpdateDiscovery(status,new Set(),{getItem:()=> null,setItem(){}},documentObject),false);
});

test('missing release links use the existing official repository',()=>{
 assert.equal(updateNotice({state:'Available',available:'1.2.0'}).url,'https://github.com/maxwellsdm1867/Rieke-OS/releases');
});
