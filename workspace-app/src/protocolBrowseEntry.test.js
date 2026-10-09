import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {deferred} from './test-support/pagedTreeHarness.js';

const props={id:'protocol-A',projectId:'project',revision:0,structureRevision:0,session:{tab:'inspect'},onChange(){}};
const browsePath='/protocols/protocol-A?projection=browse';
const entry=(full,changes={})=>({definition:full.definition,query_revision:full.query_revision,
 expected_binding_version:full.expected_binding_version,selection_options:{cell_types:['ON']},groups:['Recorded group'],source_eligibility:full.source_eligibility,...changes});
const ready=h=>h.waitFor(()=>{try{return !h.viewer.treePane.listProps.disabled;}catch{return false;}});
const tab=(h,name)=>h.act(()=>h.root.findByProps({'aria-label':name}).props.onClick());

test('actual Protocol cold Inspect and return request a compact entry; only visible Overview/export demand summaries',async()=>{
 const h=await createWorkflowHarness({liveMetadata:false});
 h.fixture.respond=(url,options,fallback)=>url.searchParams.get('projection')==='browse'?entry(fallback()):fallback();
 try{
  await h.mount(h.Protocol,props);await ready(h);
  assert.equal(h.fixture.requests.filter(r=>r.path===browsePath).length,1);
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A').length,0);
  assert.equal(h.viewer.navigation.total,500);
  assert.deepEqual(h.viewer.treePane.listProps.cells.map(c=>[c.cell_uuid,c.epochs]),[['cell-0',500]]);
  await tab(h,'Overview');
  await h.waitFor(()=>h.root.findAllByType('workflow-child').some(n=>n.props.data?.counts?.epochs===500));
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A').length,1);
  const visible=h.root.findAllByType('workflow-child').find(n=>n.props.data?.counts?.epochs===500).props.data;
  assert.deepEqual(visible.counts,{epochs:500,cells:1,included:500});
  await tab(h,'Inspect');await ready(h);
  assert.equal(h.fixture.requests.filter(r=>r.path===browsePath).length,2,'return obtains a fresh descriptor');
  assert.equal(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A').length,1);
  const mounts=h.fixture.mounts;
  await tab(h,'Export');await h.waitFor(()=>h.root.findAllByType('workflow-dialog').length===1);
  assert.ok(h.fixture.requests.filter(r=>r.path==='/protocols/protocol-A').length>1);
  assert.equal(h.fixture.mounts,mounts,'showing export never replaces the active Inspector');
  const save=h.root.findByType('workflow-dialog').findAllByType('button').find(n=>n.children.some(v=>typeof v==='string'&&v.includes('Save & export')));
  assert.equal(save.props.disabled,false);
 }finally{await h.close();}
});

test('held structural entry refresh retains Inspector inert until a fresh descriptor and page arrive',async()=>{
 const h=await createWorkflowHarness({liveMetadata:false}),pending=deferred();let held=false;
 h.fixture.respond=(url,options,fallback)=>url.searchParams.get('projection')==='browse'?(held?pending.promise:entry(fallback())):fallback();
 try{
  await h.mount(h.Protocol,props);await ready(h);const mounts=h.fixture.mounts;
  held=true;h.fixture.generation=1;
  await h.render(h.Protocol,{...props,revision:1,structureRevision:1});
  assert.equal(h.fixture.mounts,mounts);assert.equal(h.fixture.unmounts,0);
  assert.equal(h.viewer.treePane.listProps.disabled,true);
  assert.equal(h.viewer.columnTree.actionsDisabled,true);
  await h.act(()=>pending.resolve(entry({definition:{protocol_uuid:'protocol-A',name:'Test'},query_revision:'query-1',expected_binding_version:2,source_eligibility:{}})));
  await ready(h);
  assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-1');
  assert.equal(h.fixture.mounts,mounts);
 }finally{pending.resolve({});await h.close();}
});

for(const identity of ['actor','project'])test(`${identity} A/B/A entry requests reject late completions even when transport ignores abort`,async()=>{
 const h=await createWorkflowHarness({liveMetadata:false}),pending=[];
 h.fixture.respond=(url,options,fallback)=>url.searchParams.get('projection')==='browse'?new Promise(resolve=>pending.push({resolve,value:entry(fallback())})):fallback();
 try{
  await h.mount(h.Protocol,props);await h.waitFor(()=>pending.length===1);
  if(identity==='actor')h.fixture.profile={...h.fixture.profile,profileUuid:'other'};
  await h.render(h.Protocol,identity==='project'?{...props,projectId:'other-project'}:props);await h.waitFor(()=>pending.length===2);
  if(identity==='actor')h.fixture.profile={...h.fixture.profile,profileUuid:'author'};
  await h.render(h.Protocol,props);await h.waitFor(()=>pending.length===3);
  await h.act(()=>pending[0].resolve({...pending[0].value,definition:{protocol_uuid:'protocol-A',name:'Retired A'}}));
  await h.act(()=>pending[1].resolve({...pending[1].value,definition:{protocol_uuid:'protocol-A',name:'Retired B'}}));
  assert.equal(h.root.findAllByType('workflow-viewer').length,0);
  await h.act(()=>pending[2].resolve({...pending[2].value,definition:{protocol_uuid:'protocol-A',name:'Current A'}}));
  await ready(h);
  assert.equal(h.root.findByProps({className:'protocol-view-context'}).findByType('strong').children.join(''),'Current A');
  assert.equal(h.fixture.requests.filter(r=>r.path.includes('/epochs?')).length,1);
 }finally{for(const item of pending)item.resolve(item.value);await h.close();}
});

test('request-owner replacement cannot publish the retired descriptor at the same URL',async()=>{
 const h=await createWorkflowHarness({liveMetadata:false}),pending=[];
 try{
  const {WorkspaceRequestProvider}=await h.module('workspaceRequest.js');
  const {api}=await h.module('api.js');
  const request=identity=>(path,options)=>path===browsePath?new Promise(resolve=>pending.push({identity,resolve})):api(path,options);
  const a={identity:'owner-a',request:request('a')},b={identity:'owner-b',request:request('b')};
  const Root=({port})=>React.createElement(WorkspaceRequestProvider,{port},React.createElement(h.Protocol,props));
  await h.mount(Root,{port:a});await h.waitFor(()=>pending.length===1);
  await h.render(Root,{port:b});await h.waitFor(()=>pending.length===2);
  await h.act(()=>pending[0].resolve({definition:{protocol_uuid:'protocol-A',name:'Retired owner'},query_revision:'query-0',expected_binding_version:2}));
  assert.equal(h.root.findAllByType('workflow-viewer').length,0);
  await h.act(()=>pending[1].resolve({definition:{protocol_uuid:'protocol-A',name:'Current owner'},query_revision:'query-0',expected_binding_version:2}));
  await ready(h);
  assert.equal(h.root.findByProps({className:'protocol-view-context'}).findByType('strong').children.join(''),'Current owner');
 }finally{for(const item of pending)item.resolve({});await h.close();}
});

test('read-only Inspect remains available when no annotation profile can be loaded',async()=>{
 const h=await createWorkflowHarness({liveMetadata:false});
 h.fixture.profile={profileUuid:'',loading:false,error:'Profile unavailable'};
 h.fixture.respond=(url,options,fallback)=>url.searchParams.get('projection')==='browse'?entry(fallback()):fallback();
 try{
  await h.mount(h.Protocol,props);await h.waitFor(()=>h.root.findAllByType('workflow-viewer').length===1);
  assert.equal(h.viewer.navigation.total,500);
  assert.equal(h.fixture.requests.filter(r=>r.path===browsePath).length,1);
 }finally{await h.close();}
});
