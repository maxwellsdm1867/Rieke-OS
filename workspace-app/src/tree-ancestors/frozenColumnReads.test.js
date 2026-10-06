import test from 'node:test';
import assert from 'node:assert/strict';
import {loadColumnTreePages} from './columnTreeReads.js';
const revision='a'.repeat(64),key='b'.repeat(64),token='candidate-token';
const scope={protocolId:'p',readContext:{root:'/candidates/c',candidate_scope_revision:token,tree_column_pages:true},splits:'date',filters:{cell_uuid:'cell'}};
const fence={revision,generation:{metadata:'m',source:'s'},candidate_scope_revision:token,query_revision:token,expected_binding_version:1};
const parent={...fence,generation:{...fence.generation},kind:'branches',path:[],offset:60};
const target={...fence,kind:'epochs',path:[key],offset:0,ancestors:[{parent_offset:60}],ancestor_pages:[parent]};
test('advertised frozen column read obtains fresh target and parents in one bounded request',async()=>{
 const calls=[];const load=async(path,options)=>{calls.push({path,...options});return structuredClone(target);};
 const pages=await loadColumnTreePages({scope,path:[key],revisionOverride:revision,load});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/candidates/c/tree/page');
 assert.deepEqual(calls[0].body,{candidate_scope_revision:token,filters:{cell_uuid:'cell'},splits:'date',path:[key],offset:0,limit:60,revision,include_ancestors:true,ancestor_offsets:[]});
 assert.deepEqual(pages,[parent,Object.fromEntries(Object.entries(target).filter(([key])=>key!=='ancestor_pages'))]);
});
test('anchor uses recorded offsets; ordinary restoration retains explicit offsets and absent placeholders',async()=>{
 let sent;const load=async(path,{body})=>{sent=body;return structuredClone(target);};
 await loadColumnTreePages({scope,anchor:'epoch',columnPositions:[{offset:0}],load});assert.deepEqual(sent.ancestor_offsets,[0]);
 const pages=await loadColumnTreePages({scope,path:[key],columnPositions:[{offset:0}],load:async()=>({...target,ancestor_pages:[{...parent,offset:0}]})});assert.equal(pages[0].offset,0);
 await loadColumnTreePages({scope,path:[key],columnPositions:[{}],load});assert.deepEqual(sent.ancestor_offsets,[null]);
});
for(const [name,change] of Object.entries({missing:p=>delete p.ancestor_pages,extra:p=>p.ancestor_pages.push(parent),path:p=>p.ancestor_pages[0].path=[key],offset:p=>p.ancestor_pages[0].offset=0,revision:p=>p.ancestor_pages[0].revision='c'.repeat(64),scope:p=>p.ancestor_pages[0].candidate_scope_revision='old',generation:p=>p.ancestor_pages[0].generation.metadata='old',binding:p=>p.ancestor_pages[0].expected_binding_version=2,terminal:p=>p.ancestor_pages[0].kind='epochs'}))test(`frozen batch rejects ${name} before publication`,async()=>{
 const response=structuredClone(target);change(response);
 await assert.rejects(loadColumnTreePages({scope,path:[key],load:async()=>response}));
});
test('a late frozen batch cannot publish after supersession or cancellation',async()=>{
 let release,current=true;const controller=new AbortController();
 const pending=loadColumnTreePages({scope,path:[key],signal:controller.signal,isCurrent:()=>current,load:()=>new Promise(resolve=>release=resolve)});
 current=false;controller.abort();release(target);await assert.rejects(pending,{name:'AbortError'});
});
test('old frozen contexts retain fresh per-page reads without batching',async()=>{
 const old={...scope,readContext:{...scope.readContext,tree_column_pages:undefined}};const calls=[];
 const pages=await loadColumnTreePages({scope:old,path:[key],load:async(path,{body})=>{calls.push(body);return body.path.length?target:parent;}});
 assert.equal(pages.length,2);assert.equal(calls.length,2);assert.ok(calls.every(body=>!('include_ancestors' in body)));
});
