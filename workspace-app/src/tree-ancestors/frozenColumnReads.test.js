import test from 'node:test';
import assert from 'node:assert/strict';
import {loadColumnTreePages} from './columnTreeReads.js';
const revision='a'.repeat(64),key='b'.repeat(64),token='candidate-token';
const scope={protocolId:'p',readContext:{root:'/candidates/c',candidate_scope_revision:token,tree_column_pages:true},splits:'date',filters:{cell_uuid:'cell'}};
const fence={revision,generation:{metadata:'m',source:'s'},candidate_scope_revision:token,query_revision:token,expected_binding_version:1};
const parent={...fence,generation:{...fence.generation},kind:'branches',path:[],offset:60};
const target={...fence,kind:'epochs',path:[key],offset:0,ancestors:[{parent_offset:60}],ancestor_pages:[parent]};
const freshRoot={...fence,kind:'branches',path:[],offset:0};
test('frozen continuation renewal pins the retained path to a fresh scoped root without borrowing old authority',async()=>{
 const calls=[];
 const pages=await loadColumnTreePages({scope,path:[key],freshContinuation:true,revisionOverride:'c'.repeat(64),load:async(endpoint,{body})=>{
  calls.push({endpoint,body});
  if(!body.path.length){assert.equal(body.revision,undefined);return structuredClone(freshRoot);}
  assert.equal(body.revision,revision);return structuredClone(target);
 }});
 assert.equal(calls.length,2);assert.ok(calls.every(call=>call.endpoint==='/candidates/c/tree/page'));
 assert.ok(calls.every(call=>call.body.candidate_scope_revision===token));
 assert.deepEqual(calls[1].body.path,[key]);assert.equal(pages.at(-1).revision,revision);
});
for(const [name,change] of Object.entries({revision:p=>delete p.revision,scope:p=>p.candidate_scope_revision='old',query:p=>p.query_revision='old',binding:p=>p.expected_binding_version=-1,generation:p=>p.generation=null,path:p=>p.path=[key],offset:p=>p.offset=60}))test(`frozen renewal refuses invalid ${name} root before requesting retained descendants`,async()=>{
 let calls=0;const root=structuredClone(freshRoot);change(root);
 await assert.rejects(loadColumnTreePages({scope,path:[key],freshContinuation:true,load:async()=>{calls++;return root;}}),/continuation root/);
 assert.equal(calls,1);
});
for(const [name,change] of Object.entries({scope:p=>p.candidate_scope_revision='old',query:p=>p.query_revision='old',binding:p=>p.expected_binding_version=2,generation:p=>p.generation.metadata='changed'}))test(`frozen renewal refuses target ${name} drift from its fresh root`,async()=>{
 const changed=structuredClone(target);change(changed);
 await assert.rejects(loadColumnTreePages({scope,path:[key],freshContinuation:true,load:async(endpoint,{body})=>body.path.length?changed:structuredClone(freshRoot)}),/continuation authority/);
});
test('superseded frozen root cannot issue a retained continuation request',async()=>{
 let release,calls=0,current=true;
 const pending=loadColumnTreePages({scope,path:[key],freshContinuation:true,isCurrent:()=>current,load:()=>{calls++;return new Promise(resolve=>release=resolve);}});
 current=false;release(freshRoot);await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,1);
});
test('advertised frozen column read obtains fresh target and parents in one bounded request',async()=>{
 const calls=[];const load=async(path,options)=>{calls.push({path,...options});return structuredClone(target);};
 const pages=await loadColumnTreePages({scope,path:[key],revisionOverride:revision,load});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/candidates/c/tree/page');
 assert.deepEqual(calls[0].body,{counts_only:true,candidate_scope_revision:token,filters:{cell_uuid:'cell'},splits:'date',path:[key],offset:0,limit:60,revision,include_ancestors:true,ancestor_offsets:[]});
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
test('incoming expand under displayed parents with the pinned fence reads only its target',async()=>{
 const shown={...fence,generation:{...fence.generation},kind:'branches',path:[],offset:0};
 const fresh={...fence,generation:{...fence.generation},kind:'epochs',path:[key],offset:0,ancestors:[{parent_offset:0}]};
 const calls=[];
 const pages=await loadColumnTreePages({scope,path:[key],revisionOverride:revision,retainedPages:[shown],columnPositions:[{offset:0}],load:async(path,{body})=>{calls.push(body);return structuredClone(fresh);}});
 assert.equal(calls.length,1);assert.equal('include_ancestors' in calls[0],false,'no ancestor batch when retained parents match');
 assert.deepEqual(pages,[shown,fresh]);
});
for(const [name,change] of Object.entries({generation:p=>p.generation.metadata='newer',binding:p=>p.expected_binding_version=2,query:p=>p.query_revision='other'}))test(`incoming expand re-reads ancestors in one batch when the target ${name} differs from displayed parents`,async()=>{
 const shown={...fence,generation:{...fence.generation},kind:'branches',path:[],offset:0};
 const fresh={...fence,generation:{...fence.generation},kind:'epochs',path:[key],offset:0,ancestors:[{parent_offset:0}]};change(fresh);
 if(name==='query')fresh.candidate_scope_revision=token;
 const calls=[];
 const load=async(path,{body})=>{calls.push(body);const value=structuredClone(fresh);if(body.include_ancestors)value.ancestor_pages=[{...structuredClone(shown),generation:value.generation,expected_binding_version:value.expected_binding_version,query_revision:value.query_revision}];return value;};
 const result=loadColumnTreePages({scope,path:[key],revisionOverride:revision,retainedPages:[shown],columnPositions:[{offset:0}],load});
 if(name==='query'){await assert.rejects(result);assert.equal(calls.length,2);assert.equal(calls[1].include_ancestors,true);return;}
 const pages=await result;
 assert.equal(calls.length,2);assert.equal(calls[1].include_ancestors,true,'one bounded fresh batch');
 assert.equal(pages[0].generation.metadata,fresh.generation.metadata);
});
