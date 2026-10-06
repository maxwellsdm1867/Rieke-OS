import test from 'node:test';
import assert from 'node:assert/strict';
import {loadColumnTreePages} from './columnTreeReads.js';
const revision='a'.repeat(64),key='b'.repeat(64),scope={protocolId:'p',splits:'date',filters:{}};
const identity={version:1,protocol_uuid:'p',tree_revision:revision,project_uuid:'project',project_path:'/fixture',generation:{metadata:'m',source:'s',annotation:'a',binding:'b',publication:'p',typed:null}};
const root={kind:'branches',path:[],offset:60,depth:0,limit:60,total:1,branches:[],epochs:[],split_order:['date'],revision,read_identity:identity,tree_column_pages:true};
const target={kind:'epochs',path:[key],offset:0,depth:1,limit:60,total:1,branches:[],epochs:[{epoch_uuid:'epoch'}],split_order:['date'],revision,read_identity:identity,tree_column_pages:true,ancestors:[{parent_offset:60}],ancestor_pages:[root]};
test('known live capability batches a cold target and shares the exact witness',async()=>{
 const calls=[];
 const pages=await loadColumnTreePages({scope,path:[key],retainedPages:[root],load:async(endpoint,{body})=>{calls.push(body);return structuredClone(target);}});
 assert.equal(calls.length,1);assert.equal(calls[0].include_ancestors,true);assert.deepEqual(pages[0],root);
});
test('retained parent geometry with a read owner preserves fresh-target and attested warm reads',async()=>{
 const calls=[],reads=[];const lease={};
 const readOwner={available:true,active:()=>true,attest:()=>lease,current:()=>true,read:async(proof,body)=>{assert.equal(proof,lease);reads.push(body);return root;}};
 await loadColumnTreePages({scope,path:[key],retainedPages:[root],readOwner,load:async(endpoint,{body})=>{calls.push(body);return target;}});
 assert.equal(calls.length,1);assert.equal(calls[0].include_ancestors,undefined);assert.equal(reads.length,1);
});
test('unknown capability retains ordinary requests and never retries a failed batch',async()=>{
 const calls=[];
 await loadColumnTreePages({scope,path:[key],load:async(endpoint,{body})=>{calls.push(body);return body.path.length?target:root;}});
 assert.equal(calls.length,2);assert.ok(calls.every(body=>!body.include_ancestors));
 let attempts=0;
 await assert.rejects(loadColumnTreePages({scope,path:[key],retainedPages:[root],load:async()=>{attempts++;throw Object.assign(Error('stale'),{status:409});}}));
 assert.equal(attempts,1);
});
for(const [name,change] of Object.entries({identity:p=>p.ancestor_pages[0].read_identity={...identity,generation:{metadata:'other'}},path:p=>p.ancestor_pages[0].path=[key],offset:p=>p.ancestor_pages[0].offset=0,revision:p=>p.ancestor_pages[0].revision='old',capability:p=>delete p.tree_column_pages,missing:p=>delete p.ancestor_pages,targetPath:p=>p.path=['c'.repeat(64)],targetOffset:p=>p.offset=60,split:p=>p.split_order=['cell'],limit:p=>p.limit=100,parentDepth:p=>p.ancestor_pages[0].depth=1}))test(`live batch rejects ${name} before publication`,async()=>{
 const page=structuredClone(target);change(page);
 await assert.rejects(loadColumnTreePages({scope,path:[key],retainedPages:[root],load:async()=>page}));
});
test('fresh continuation discovers support in its required root read',async()=>{
 const calls=[];
 await loadColumnTreePages({scope,path:[key],freshContinuation:true,load:async(endpoint,{body})=>{calls.push(body);return body.path.length?target:root;}});
 assert.equal(calls.length,2);assert.equal(calls[1].revision,revision);assert.equal(calls[1].include_ancestors,true);
});
test('live batch cannot publish when superseded',async()=>{
 let release,current=true;
 const pending=loadColumnTreePages({scope,path:[key],retainedPages:[root],isCurrent:()=>current,load:()=>new Promise(resolve=>release=resolve)});
 current=false;release(target);await assert.rejects(pending,{name:'AbortError'});
});

test('validated live bundle seeds bounded immutable parents for the next fresh witness',async()=>{
 const {createTreeBranchReadCache}=await import('./treeBranchReadCache.js');
 const cache=createTreeBranchReadCache(),ownerScope={projectUuid:'project',projectPath:'/fixture',actorId:'author',revision:1,activation:'one'};
 cache.activate(ownerScope);
 const readOwner={available:true,active:()=>cache.isActive(ownerScope),attest:(body,page)=>cache.attest(ownerScope,body,page),read:(...args)=>cache.read(...args),current:lease=>cache.assertCurrent(lease)};
 const anchor={...target,anchor:{epoch_uuid:'epoch',path:[key],index:0,offset:0}};let calls=0;
 try{
  await loadColumnTreePages({scope,anchor:'epoch',retainedPages:[root],readOwner,load:async()=>{calls++;return structuredClone(anchor);}});
  assert.equal(cache.stats().entries,1);
  const pages=await loadColumnTreePages({scope,path:[key],retainedPages:[root],readOwner,load:async()=>{calls++;return structuredClone(target);}});
  assert.equal(calls,2,'one fresh target per operation, no parent HTTP');assert.equal(cache.stats().hits,1);assert.equal(Object.isFrozen(pages[0]),true);
 }finally{cache.retire();}
});

const deepScope={...scope,splits:'date,cell,block'},deepKeys=['b','c','d'].map(x=>x.repeat(64));
const deepParents=deepKeys.map((_,depth)=>({...root,path:deepKeys.slice(0,depth),depth,split_order:['date','cell','block'],offset:depth*60,ancestors:deepKeys.slice(0,depth).map((_,i)=>({parent_offset:i*60}))}));
const deepTarget={...target,path:deepKeys,depth:3,split_order:['date','cell','block'],anchor:{epoch_uuid:'epoch',path:deepKeys,index:0,offset:0},ancestors:deepKeys.map((_,i)=>({parent_offset:i*60}))};
delete deepTarget.ancestor_pages;
function deepResponse(body){return body.anchor_uuid?structuredClone(deepTarget):{...structuredClone(deepParents.at(-1)),ancestor_pages:structuredClone(deepParents.slice(0,-1))};}
test('initial deep live anchor discovers batching and preserves recorded offsets in two reads',async()=>{
 const calls=[];
 const pages=await loadColumnTreePages({scope:deepScope,anchor:'epoch',load:async(endpoint,{body})=>{calls.push(body);return deepResponse(body);}});
 assert.equal(calls.length,2);assert.equal(calls[0].include_ancestors,undefined);assert.equal(calls[1].include_ancestors,true);
 assert.equal(calls[1].anchor_uuid,undefined);assert.deepEqual(calls[1].path,deepKeys.slice(0,2));assert.equal(calls[1].offset,120);assert.deepEqual(calls[1].ancestor_offsets,[0,60,120]);
 assert.deepEqual(pages,[...deepParents,deepTarget]);
});
test('initial deep live anchor rejects authority change between target and parent bundle',async()=>{
 await assert.rejects(loadColumnTreePages({scope:deepScope,anchor:'epoch',load:async(endpoint,{body})=>{
  const value=deepResponse(body);if(body.include_ancestors)for(const page of [value,...value.ancestor_pages])page.read_identity={...identity,generation:{...identity.generation,annotation:'changed'}};return value;
 }}),/changed/);
});
test('older deep target keeps bounded ordinary parent requests',async()=>{
 const calls=[];
 const pages=await loadColumnTreePages({scope:deepScope,anchor:'epoch',load:async(endpoint,{body})=>{
  calls.push(body);const value=body.anchor_uuid?structuredClone(deepTarget):structuredClone(deepParents[body.path.length]);delete value.tree_column_pages;return value;
 }});
 assert.equal(calls.length,4);assert.equal(pages.length,4);assert.ok(calls.every(body=>!body.include_ancestors));
});
test('initial parent bundle cannot publish after cancellation',async()=>{
 let release,current=true;const pending=loadColumnTreePages({scope:deepScope,anchor:'epoch',isCurrent:()=>current,load:async(endpoint,{body})=>body.anchor_uuid?deepResponse(body):new Promise(resolve=>release=()=>resolve(deepResponse(body)))});
 while(!release)await new Promise(resolve=>setTimeout(resolve,0));current=false;release();await assert.rejects(pending,{name:'AbortError'});
});
