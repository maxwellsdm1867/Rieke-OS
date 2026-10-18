import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const priorResize=globalThis.ResizeObserver;
test.before(()=>{globalThis.ResizeObserver=class{observe(){} disconnect(){}};});
test.after(()=>{if(priorResize)globalThis.ResizeObserver=priorResize;else delete globalThis.ResizeObserver;});
function keyEvent(shiftKey=false){const region={tagName:'DIV',closest:()=>null,hasAttribute:()=>false,focus(){}};return {key:'Tab',shiftKey,target:region,currentTarget:region,preventDefault(){},stopPropagation(){}};}
const revision='surface-query';
const candidateRoot='/protocols/protocol-A/workbench/candidates/candidate-A';
const initial={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:revision,expected_binding_version:2},projectId:'project-A',filters:{},revision:0,initialEpochUuid:'epoch-8'};
function attach(h){
 h.fixture.respond=(url,options,result)=>{
  const original=url.pathname,body=options.body?JSON.parse(options.body):{};
  if(original==='/api/explore/epochs'){
   url.pathname='/api/protocols/protocol-A/epochs';
   for(const key of ['cell_uuid','offset','anchor_uuid','limit','include_cells'])if(body[key]!==undefined)url.searchParams.set(key,String(body[key]));
   return {...result(),revision:body.revision};
  }
  if(original.startsWith('/api'+candidateRoot)){
   const suffix=original.slice(('/api'+candidateRoot).length);
   url.pathname=suffix.startsWith('/epochs/epoch-')?'/api'+suffix:'/api/protocols/protocol-A'+suffix;
  }
  const value=result();
  return value.epochs?{...value,query_revision:revision}:value;
 };
}
function row(root,n,cell='Cell 0'){return root.findAllByType('button').find(node=>node.props['aria-label']===`Inspect 2026-09-29 · ${cell} epoch ${n}`);}
async function openCell(h,index=0){
 const date=h.root.findAllByType('details').find(n=>n.props.className==='cell-tree-date');if(!date.props.open)await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
 const cell=h.root.findAllByType('details').filter(n=>n.props.className==='cell-tree-cell')[index];
 const before=h.fixture.requests.length;cell.findByType('summary').props.onClick?.({target:{closest:()=>null}});
 assert.equal(h.fixture.requests.length,before,'a browse cell click never reads or replaces inspection');
 await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
 await h.waitFor(()=>!!row(h.root,1,`Cell ${index}`));return cell;
}
function options(surface,saved,onSession){
 if(surface==='predicate')return {projectId:'project-A',predicate:{all:[]},splits:['date','cell'],preview:{tree_revision:revision,catalog:{fields:[]}},session:saved||{revision,focused:'epoch-8'},onSession};
 return {...initial,initialNavigation:saved,onSessionChange:onSession,...(surface==='workbench'?{readContext:{root:candidateRoot,candidate_scope_revision:revision,cohort_key:'immutable-cohort-A'},draftSelection:{selected:['epoch-2'],disabled:false},onSelectionChange(){}}:{})};
}
for(const surface of ['pinned','predicate','workbench']){
 test(`${surface}: real list preserves siblings during expansion, fast clicks, Tab/backward and page crossing`,async t=>{
  const h=await createWorkflowHarness({total:700,liveMetadata:false,realTreePane:true});attach(h);let saved;
  try{
   const Component=await h.component(surface==='predicate'?'MatchingEpochs':'Inspector');
   await h.mount(Component,options(surface,null,value=>{saved=value;}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);
   const node=row(h.root,9),before=h.fixture.requests.length;
   await openCell(h,1);assert.equal(h.viewer.epoch.epoch_uuid,'epoch-8');assert.equal(row(h.root,9),node);
   assert.ok(h.fixture.requests.slice(before).every(r=>r.path.includes('cell_uuid=cell-1')||r.body?.cell_uuid==='cell-1'));
   const times=[];
   for(const ordinal of [10,11,12,11,10,9,15,16,17,16]){
    const start=performance.now();await h.act(()=>row(h.root,ordinal).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===`epoch-${ordinal-1}`);times.push(performance.now()-start);assert.equal(row(h.root,9),node);
   }
   for(const key of ['Tab','Tab','Tab','Tab','Tab'])await h.act(()=>h.viewer.onKeyDown(keyEvent()));
   await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-20');
   await h.act(()=>h.viewer.onKeyDown(keyEvent(true)));
   await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-19');
   const more=h.root.findAllByType('button').find(n=>n.props.children==='Load more epochs');await h.act(()=>more.props.onClick());await h.waitFor(()=>!!row(h.root,70));
   const requests=h.fixture.requests.length,crossStart=performance.now();await h.act(()=>row(h.root,70).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-69'&&!h.viewer.navigation.loading);
   const cross=performance.now()-crossStart;assert.equal(row(h.root,9),node);assert.ok(saved);
   assert.equal(h.fixture.requests.slice(requests).filter(r=>r.path.includes('cell_uuid=')||r.body?.cell_uuid).length,0);
   if(surface==='workbench')assert.deepEqual(h.viewer.treePane.listProps.targets,['epoch-2']);
   assert.ok(h.fixture.requests.every(r=>r.method==='GET'||r.path==='/explore/epochs'),'navigation sends only read operations');
   if(surface==='workbench')assert.ok(h.fixture.requests.filter(r=>r.path.includes('/epochs?')).every(r=>r.path.startsWith(candidateRoot)),'no live protocol fallback');
   times.sort((a,b)=>a-b);t.diagnostic(JSON.stringify({surface,metric:'mounted action to requested epoch ready; mock API; no browser paint',samples:times.length,median_ms:(times[4]+times[5])/2,max_ms:times.at(-1),cross_page_ms:cross}));
  }finally{await h.close();}
 });
 test(`${surface}: list/tree/list and leave-for-overview/return retain epoch and expanded cells`,async()=>{
  const h=await createWorkflowHarness({total:700,liveMetadata:false,realTreePane:true});attach(h);let saved;
  try{
   const Component=await h.component(surface==='predicate'?'MatchingEpochs':'Inspector'),props=options(surface,null,value=>{saved=value;});
   await h.mount(Component,props);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);await openCell(h,1);
   await h.act(()=>row(h.root,18).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-17');
   const navigation={...saved.listNavigation,scrollTop:180};await h.act(()=>h.viewer.treePane.listProps.onNavigationChange(navigation));
   await h.act(()=>h.viewer.treePane.onTreeMode(true));await h.act(()=>h.viewer.treePane.onTreeMode(false));await h.waitFor(()=>!!row(h.root,18));
   assert.equal(h.viewer.epoch.epoch_uuid,'epoch-17');assert.equal(h.viewer.treePane.listProps.initialNavigation.scrollTop,180);
   assert.deepEqual(h.root.findAllByType('details').filter(n=>n.props.className==='cell-tree-cell').map(n=>n.props.open),[true,true]);
   const snapshot=saved;await h.render(()=>React.createElement('div',null,'Project Overview'),{});
   await h.render(Component,options(surface,snapshot,value=>{saved=value;}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-17'&&!!row(h.root,18));
   assert.equal(h.viewer.treePane.listProps.initialNavigation.scrollTop,180);
   assert.deepEqual(h.root.findAllByType('details').filter(n=>n.props.className==='cell-tree-cell').map(n=>n.props.open),[true,true]);
  }finally{await h.close();}
 });
}

test('predicate list session is isolated by project, predicate, split order and preview revision',async()=>{
 for(const change of [{projectId:'other-project'},{predicate:{all:[{field:'cell/label',operator:'eq',value:'other'}]}},{splits:['cell','date']},{preview:{tree_revision:'other-revision',catalog:{fields:[]}}}]){
  const h=await createWorkflowHarness({total:700,liveMetadata:false,realTreePane:true});attach(h);let saved;
  try{
   const Component=await h.component('MatchingEpochs'),props=options('predicate',null,value=>{saved=value;});await h.mount(Component,props);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);
   const snapshot=saved;await h.render(()=>null,{});await h.render(Component,{...options('predicate',snapshot,()=>{}),...change});
   await h.waitFor(()=>!h.viewer.navigation.loading);
   assert.equal(h.root.findAllByType('details').find(n=>n.props.className==='cell-tree-date').props.open,false);
  }finally{await h.close();}
 }
});

for(const surface of ['pinned','predicate','workbench'])test(`${surface}: delayed A/B/A clicks keep rows mounted and only the latest result wins`,async()=>{
 const h=await createWorkflowHarness({total:700,liveMetadata:false,realTreePane:true});attach(h);const held=[];
 try{
  const Component=await h.component(surface==='predicate'?'MatchingEpochs':'Inspector');await h.mount(Component,options(surface));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);
  await h.act(()=>h.root.findAllByType('button').find(n=>n.props.children==='Load more epochs').props.onClick());await h.waitFor(()=>!!row(h.root,70));
  const original=h.fixture.respond,node=row(h.root,9),before=h.fixture.requests.length;
  h.fixture.respond=(url,options,result)=>{
   const anchor=url.searchParams.get('anchor_uuid')||(options.body?JSON.parse(options.body).anchor_uuid:null);
   if(anchor)return new Promise(resolve=>held.push({anchor,resolve:()=>resolve(original(url,options,result)),signal:options.signal}));
   return original(url,options,result);
  };
  for(const [index,ordinal] of [70,71,70].entries()){await h.act(()=>row(h.root,ordinal).props.onClick({}));await h.waitFor(()=>held.length===index+1);assert.equal(row(h.root,9)===node,true);}
  await h.waitFor(()=>held.length===3);
  assert.deepEqual(held.map(x=>x.anchor),['epoch-69','epoch-70','epoch-69']);assert.equal(held[0].signal.aborted,true);assert.equal(held[1].signal.aborted,true);
  await h.act(()=>held[2].resolve());await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-69'&&!h.viewer.navigation.loading);
  await h.act(()=>{held[0].resolve();held[1].resolve();});await h.settle(30);
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-69');assert.equal(row(h.root,9),node);
  assert.equal(h.fixture.requests.slice(before).filter(r=>r.path.includes('cell_uuid=')||r.body?.cell_uuid).length,0);
 }finally{held.forEach(x=>x.resolve());await h.close();}
});

test('failed pinned epoch locator keeps existing rows and never jumps inspection to the first epoch',async()=>{
 const h=await createWorkflowHarness({total:138,liveMetadata:false,realTreePane:true});attach(h);
 try{
  const Component=await h.component('Inspector');await h.mount(Component,options('pinned'));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);
  await h.act(()=>h.root.findAllByType('button').find(n=>n.props.children==='Load more epochs').props.onClick());await h.waitFor(()=>!!row(h.root,70));
  const original=h.fixture.respond,node=row(h.root,9),before=h.fixture.requests.length;
  h.fixture.respond=(url,options,result)=>url.searchParams.has('anchor_uuid')?{failure:503,error:'Fixture locator unavailable'}:original(url,options,result);
  await h.act(()=>row(h.root,70).props.onClick({}));await h.settle(100);
  assert.equal(row(h.root,9)===node,true,'an error must not remount unrelated loaded rows');
  assert.notEqual(h.viewer.epoch?.epoch_uuid,'epoch-0');
  assert.equal(h.fixture.requests.slice(before).filter(r=>r.path.includes('cell_uuid=')).length,0);
 }finally{await h.close();}
});

test('retained workspace owner keeps independent pinned, predicate and workbench positions across Overview and history-style returns',async t=>{
 const h=await createWorkflowHarness({total:700,liveMetadata:false,realTreePane:true});attach(h);
 const saved=new Map(),presentation={remember:(route,value)=>saved.set(route.key,value)};
 const previous={requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame,MutationObserver:globalThis.MutationObserver};
 const observers=new Set(),panes=[];
 globalThis.requestAnimationFrame=callback=>setTimeout(callback,0);globalThis.cancelAnimationFrame=clearTimeout;
 globalThis.MutationObserver=class{constructor(callback){this.callback=callback;}observe(){observers.add(this);}disconnect(){observers.delete(this);}};
 h.fixture.createNodeMock=element=>{if(element.props.className!=='inspection-cell-tree')return undefined;const listeners=new Map();const pane={scrollTop:0,scrollHeight:2000,clientHeight:500,addEventListener:(name,callback)=>listeners.set(name,callback),removeEventListener:name=>listeners.delete(name),listeners};panes.push(pane);return {closest:()=>pane,querySelector:()=>h.fixture.pending.size?{}:null};};
 try{
  const Inspector=await h.component('Inspector'),Matching=await h.component('MatchingEpochs');
  const {RetainedWorkspaceViews}=await h.module('retainedWorkspaceViews.js');
  const routes=Object.fromEntries(['pinned','predicate','workbench','overview'].map(name=>[name,{key:name,page:name==='predicate'?'explore':name==='overview'?'overview':'protocol',protocol:'protocol-A'}]));
  function Shell({destination}){return React.createElement(RetainedWorkspaceViews,{route:routes[destination],projectId:'project-A',projectPath:'/owned-fixture',presentation,render:(route,{remember})=>route.key==='overview'?React.createElement('h1',null,'Project Overview'):React.createElement(route.key==='predicate'?Matching:Inspector,options(route.key,saved.get(route.key),remember))});}
  const active=()=>h.root.findAllByProps({'data-workspace-active':'true'})[0];
  const viewer=()=>active().findByType('workflow-viewer').props;
  const positions={pinned:14,predicate:24,workbench:34};
  await h.mount(Shell,{destination:'overview'});
  for(const surface of ['pinned','predicate','workbench']){
   await h.render(Shell,{destination:surface});await h.waitFor(()=>viewer().epoch?.epoch_uuid==='epoch-8');
   const date=active().findAllByType('details').find(n=>n.props.className==='cell-tree-date');await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
   const cell=active().findAllByType('details').find(n=>n.props.className==='cell-tree-cell');await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));await h.waitFor(()=>!!row(active(),positions[surface]));
   await h.act(()=>row(active(),positions[surface]).props.onClick({}));await h.waitFor(()=>viewer().epoch?.epoch_uuid===`epoch-${positions[surface]-1}`);
   await h.act(()=>{const pane=panes.at(-1);pane.scrollTop=positions[surface]*10;pane.listeners.get('scroll')();});
  }
  const timings=[];
  for(const surface of ['pinned','predicate','workbench','predicate','pinned']){
   await h.render(Shell,{destination:'overview'});const start=performance.now();await h.render(Shell,{destination:surface});
   await h.waitFor(()=>viewer().epoch?.epoch_uuid===`epoch-${positions[surface]-1}`&&!!row(active(),positions[surface]));
   timings.push({surface,ms:performance.now()-start});
   for(const observer of [...observers])observer.callback();await h.settle(20);
   assert.equal(panes.at(-1).scrollTop,positions[surface]*10,'ready return retains actual pane position');
   assert.equal(active().findAllByType('details').find(n=>n.props.className==='cell-tree-cell').props.open,true);
   assert.equal(viewer().treePane.listProps.initialNavigation.scrollTop,positions[surface]*10);
   for(const other of ['pinned','predicate','workbench'])assert.equal(saved.get(other).focused,`epoch-${positions[other]-1}`,'another destination must not overwrite this session');
  }
  t.diagnostic(JSON.stringify({metric:'retained owner return to same epoch ready; mock API; no browser paint',timings}));
 }finally{await h.close();Object.assign(globalThis,previous);}
});

for(const surface of ['pinned','predicate','workbench'])test(`${surface}: rapid Tab across a held page boundary honors all eight steps without rebuilding the list`,async()=>{
 const h=await createWorkflowHarness({total:138,liveMetadata:false,realTreePane:true});attach(h);const held=[];
 try{
  const Component=await h.component(surface==='predicate'?'MatchingEpochs':'Inspector');await h.mount(Component,options(surface));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8');await openCell(h);
  await h.act(()=>row(h.root,58).props.onClick({}));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-57');
  const node=row(h.root,9),before=h.fixture.requests.length,original=h.fixture.respond;
  h.fixture.respond=(url,options,result)=>{
   const body=options.body?JSON.parse(options.body):{},offset=url.searchParams.get('offset')??body.offset,cell=url.searchParams.get('cell_uuid')??body.cell_uuid;
   return String(offset)==='60'&&!cell?new Promise(resolve=>held.push(()=>resolve(original(url,options,result)))):original(url,options,result);
  };
  for(let i=0;i<8;i++)await h.act(()=>h.viewer.onKeyDown(keyEvent()));
  await h.waitFor(()=>held.length>0);assert.equal(row(h.root,9)===node,true);assert.equal(held.length,1,'coalesce one destination page');
  await h.act(()=>held.splice(0).forEach(release=>release()));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-65'&&!h.viewer.navigation.loading);
  assert.equal(row(h.root,9)===node,true);
  const appended=h.fixture.requests.slice(before).filter(r=>r.path.includes('cell_uuid=')||r.body?.cell_uuid);
  assert.equal(appended.length,1,'load only the missing visible cell page');
  assert.equal(Number(appended[0].body?.offset??new URL(appended[0].path,'http://fixture').searchParams.get('offset')),60);
 }finally{held.forEach(release=>release());await h.close();}
});
