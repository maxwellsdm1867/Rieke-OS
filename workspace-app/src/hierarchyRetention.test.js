import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

const branchKeys=['a'.repeat(64),'b'.repeat(64)];
const revisions=['c'.repeat(64),'d'.repeat(64)];

async function fixture({frozen=false,columns=false,wrapped=false,epochCount=1,observeCommits=false}={}){
  const dom=new JSDOM('<main></main>',{url:'http://fixture/'});
  const previous=Object.fromEntries(['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame'].map(key=>[key,globalThis[key]]));
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,
    requestAnimationFrame:callback=>setTimeout(callback,0),cancelAnimationFrame:clearTimeout});
  const state={version:0,holdRoot:false,requests:[],held:[],snapshots:[],metadata:[],holdLeaf:false,commits:[]};
  function page(body,version){
    const branches=branchKeys.map((key,index)=>({key,path:[key],label:`Branch ${index+1}`,value:`Branch ${index+1}`,count:epochCount}));
    return {...(frozen?{candidate_scope_revision:`scope-${version}`,query_revision:`scope-${version}`,expected_binding_version:1,generation:{metadata:'fixture'}}:{}),revision:revisions[version],kind:body.path.length?'epochs':'branches',path:body.path,depth:body.path.length,
      offset:body.offset||0,limit:60,total:body.path.length?epochCount:2,total_epochs:2*epochCount,split_order:['date'],levels:[{field:'date',label:'Date'}],
      ancestors:body.path.length?[{...branches.find(branch=>branch.key===body.path[0]),parent_offset:0}]:[],has_more:false,
      branches:body.path.length?[]:branches,epochs:body.path.length?Array.from({length:epochCount},(_,i)=>({epoch_uuid:`epoch-${body.path[0][0]}${i?'-'+i:''}`,cell_uuid:'cell',epoch_number:i+1})):[]};
  }
  globalThis.fetch=async(url,options)=>{
    assert.equal(url,frozen?'/api/protocols/p/workbench/candidates/c/tree/page':'/api/tree-pages');
    const body=JSON.parse(options.body),response=page(body,state.version);
    if(state.mismatchLeaf&&body.path.length)response.revision=revisions[0];
    state.requests.push({body,signal:options.signal});
    if(frozen&&(body.path.length||body.offset)&&!body.anchor_uuid&&!body.revision)return new Response(JSON.stringify({error:'A tree revision is required for continuation pages'}),{status:400});
    if(state.holdRoot&&!body.path.length||state.holdLeaf&&body.path.length)await new Promise(resolve=>state.held.push({resolve,response}));
    return new Response(JSON.stringify(response),{status:200});
  };
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,
    server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
  const {default:HierarchyTree}=await server.ssrLoadModule(columns?'/src/tree-browser/ui/ColumnTree.jsx':'/src/tree-browser/ui/HierarchyTree.jsx');
  const {default:RetainedTreePresentation}=wrapped?await server.ssrLoadModule('/src/tree-browser/ui/RetainedTreePresentation.jsx'):{default:null};
  function CommitProbe(){React.useLayoutEffect(()=>{state.commits.push({pane:!!document.querySelector('.tree-trace-pane')});});return null;}
  const root=createRoot(document.querySelector('main'));
  const render=(mode='visible',revision=0,extra={})=>act(async()=>{
    const tree={protocolId:'p',splits:'date',revision,browseOnly:true,
      ...(frozen?{projectId:'project',readContext:{root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:`scope-${state.version}`,expected_binding_version:1}}:{}),...extra,
      onNavigationChange:value=>state.snapshots.push(value),onMetadata:value=>state.metadata.push(value)};
    const child=wrapped?React.createElement(RetainedTreePresentation,{active:mode==='visible',tree}):React.createElement(HierarchyTree,tree);
    root.render(React.createElement(React.Activity,{mode:wrapped?'visible':mode},observeCommits?
      React.createElement(React.Fragment,null,child,React.createElement(CommitProbe)):child));
  });
  const expand=index=>act(async()=>document.querySelectorAll(columns?'.tp-branch':'.ht-root > .ht-branch > button')[index].click());
  const scroll=()=>document.querySelector(columns?'.tp-columns':'.ht-scroll');
  async function position(top,left){await act(async()=>{scroll().scrollTop=top;scroll().scrollLeft=left;scroll().dispatchEvent(new dom.window.Event('scroll'));await new Promise(resolve=>setTimeout(resolve,5));});}
  const release=()=>act(async()=>state.held.shift().resolve());
  async function close(){await act(()=>root.unmount());await server.close();dom.window.close();for(const [key,value] of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
  const userScroll=(top,left)=>act(()=>{scroll().dispatchEvent(new dom.window.WheelEvent('wheel',{bubbles:true,deltaY:1}));scroll().scrollTop=top;scroll().scrollLeft=left;});
  return {state,render,expand,scroll,position,release,userScroll,close};
}

test('hierarchy reconnect revalidates every retained page and restores sibling expansion and scroll',async()=>{
  const h=await fixture();
  try{
    await h.render();await h.expand(0);await h.expand(1);await h.position(240,35);
    assert.equal(document.querySelectorAll('.ht-branch.expanded').length,2);
    assert.equal(h.state.requests.length,3);
    const original=document.querySelector('.hierarchy-tree');
    await h.render('hidden');h.state.holdRoot=true;await h.render();
    assert.equal(h.state.held.length,1,'reveal performs a new authoritative root read');
    assert.equal(h.state.requests.at(-1).body.revision,revisions[0],'saved revision is checked by the server');
    h.scroll().scrollTop=0;h.scroll().scrollLeft=0; // The browser clamps while the fresh list is empty.
    await h.release();
    assert.equal(document.querySelector('.hierarchy-tree'),original);
    assert.equal(document.querySelectorAll('.ht-branch.expanded').length,2);
    assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,2);
    assert.equal(h.state.requests.length,6,'both expanded pages are reread, not treated as fresh from RAM');
    assert.equal(h.scroll().scrollTop,240);assert.equal(h.scroll().scrollLeft,35);
    assert.deepEqual(h.state.snapshots.at(-1).hierarchy.expanded,branchKeys.map(key=>[key]));
    h.state.holdRoot=false;await h.render('hidden');await h.render();
    assert.equal(h.state.requests.length,9);assert.equal(h.scroll().scrollTop,240);
    await h.render('hidden');h.state.holdRoot=true;await h.render();
    await h.userScroll(70,10);await h.release();
    assert.equal(h.scroll().scrollTop,70,'new user scroll wins over delayed restoration');assert.equal(h.scroll().scrollLeft,10);
  }finally{await h.close();}
});

test('changed hierarchy scope cannot restore old expansion or publish a delayed reconnect response',async()=>{
  const h=await fixture();
  try{
    await h.render();await h.expand(0);await h.expand(1);await h.position(180,20);
    await h.render('hidden');h.state.holdRoot=true;await h.render();
    const old=h.state.requests.at(-1),published=h.state.metadata.length;
    h.state.version=1;h.state.holdRoot=false;await h.render('visible',1);
    assert.equal(old.signal.aborted,true);
    assert.equal(h.state.requests.at(-1).body.revision,undefined,'new scope does not borrow the saved revision');
    assert.equal(document.querySelectorAll('.ht-branch.expanded').length,0);
    assert.equal(h.scroll().scrollTop,0);assert.equal(h.scroll().scrollLeft,0);
    assert.equal(h.state.metadata.length,published+1);
    assert.equal(h.state.metadata.at(-1).revision,revisions[1]);
    await h.release();
    assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,0);
    assert.equal(h.state.metadata.length,published+1,'aborted old scope cannot publish a receipt');
    assert.equal(h.state.snapshots.at(-1).revision,revisions[1]);
  }finally{await h.close();}
});

test('changed server revision rejects retained hierarchy presentation as current authority',async()=>{
  const h=await fixture();
  try{
    await h.render();await h.expand(0);await h.render('hidden');
    h.state.version=1;await h.render();
    assert.match(document.querySelector('[role="alert"]').textContent,/Tree revision changed/);
    assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,0);
    assert.equal(h.state.metadata.at(-1).revision,revisions[0],'unverified replacement publishes no metadata receipt');
  }finally{await h.close();}
});

test('Workbench hierarchy refresh retains sibling expansion while rereading every path under fresh authority',async()=>{
 const h=await fixture({frozen:true});try{
  await h.render();await h.expand(0);await h.expand(1);await h.position(240,35);
  const before=h.state.requests.length;
  h.state.version=1;h.state.holdRoot=true;
  await h.render('visible',1);
  assert.equal(h.state.requests.at(-1).body.revision,undefined,'new authority does not borrow an old revision');
  assert.equal(document.querySelectorAll('.ht-branch.expanded').length,2);
  assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,2,'old rows remain visible but inert');
  assert.ok([...document.querySelectorAll('[data-epoch-uuid],.incoming-epoch-select')].every(button=>button.disabled));
  h.state.holdLeaf=true;await h.release();assert.equal(h.state.held.length,1);
  assert.equal(h.state.requests.at(-1).body.revision,revisions[1],'fresh root pins descendants');
  assert.ok([...document.querySelectorAll('[data-epoch-uuid]')].every(button=>button.disabled));
  await h.release();assert.equal(h.state.held.length,1);await h.release();
  assert.equal(h.state.requests.length,before+3);
  assert.ok(h.state.requests.slice(before).every(row=>row.body.candidate_scope_revision==='scope-1'));
  assert.equal(document.querySelectorAll('.ht-branch.expanded').length,2);
  assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,2);
  assert.ok([...document.querySelectorAll('[data-epoch-uuid]')].every(button=>!button.disabled));
  assert.equal(h.scroll().scrollTop,240);assert.equal(h.scroll().scrollLeft,35);
 }finally{await h.close();}
});

test('Workbench columns retain path and scroll across annotation revisions using fresh path receipts',async()=>{
 const h=await fixture({frozen:true,columns:true});try{
  await h.render();await h.expand(1);await h.position(0,135);
  const panes=[...document.querySelectorAll('.tp-column-content')];
  assert.equal(panes.length,2);
  await act(()=>{panes[0].scrollTop=80;panes[1].scrollTop=190;panes[1].dispatchEvent(new window.Event('scroll'));});
  const before=h.state.requests.length;
  h.state.version=1;h.state.holdLeaf=true;await h.render('visible',1);
  const first=h.state.requests[before];
  assert.deepEqual(first.body.path,[]);assert.equal(first.body.revision,undefined,'renewal first obtains an unborrowed root revision');
  assert.deepEqual(h.state.requests[before+1].body.path,[branchKeys[1]]);
  assert.equal(h.state.requests[before+1].body.revision,revisions[1],'retained continuation uses the fresh root revision');
  assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,1);
  assert.ok([...document.querySelectorAll('[data-epoch-uuid]')].every(row=>row.disabled));
  await h.release();
  assert.equal(h.state.requests.at(-1).body.revision,revisions[1]);
  assert.deepEqual(h.state.snapshots.at(-1).path,[branchKeys[1]]);
  assert.equal(h.scroll().scrollLeft,135);
  assert.deepEqual([...document.querySelectorAll('.tp-column-content')].map(pane=>pane.scrollTop),[80,190]);
  assert.equal(h.state.metadata.at(-1).revision,revisions[1]);
 }finally{await h.close();}
});

test('mismatched descendant revision cannot make a retained Workbench hierarchy actionable',async()=>{
 const h=await fixture({frozen:true});try{
  await h.render();await h.expand(0);await h.expand(1);
  const published=h.state.metadata.length;
  h.state.version=1;h.state.mismatchLeaf=true;await h.render('visible',1);
  assert.match(document.querySelector('[role="alert"]').textContent,/Tree revision changed/);
  assert.equal(h.state.metadata.length,published);
  assert.ok([...document.querySelectorAll('[data-epoch-uuid]')].every(button=>button.disabled));
 }finally{await h.close();}
});

for(const columns of [false,true])test(`Workbench ${columns?'column':'hierarchy'} refresh keeps an explicit caller revision mandatory`,async()=>{
 const h=await fixture({frozen:true,columns});try{
  await h.render('visible',0,{expectedRevision:revisions[0]});await h.expand(0);
  const published=h.state.metadata.length,before=h.state.requests.length;
  h.state.version=1;await h.render('visible',1,{expectedRevision:revisions[0]});
  assert.equal(h.state.requests[before].body.revision,revisions[0]);
  assert.ok(document.querySelector('[role="alert"]'));assert.equal(h.state.metadata.length,published);
 }finally{await h.close();}
});

for(const columns of [false,true])test(`paused Workbench ${columns?'columns':'hierarchy'} retain nodes without reading retired context`,async()=>{
 const h=await fixture({frozen:true,columns});try{
  await h.render();await h.expand(1);const nodes=[...document.querySelectorAll('[data-epoch-uuid]')],before=h.state.requests.length;
  await h.render('visible',1,{readPaused:true});
  assert.equal(h.state.requests.length,before,'paused old context cannot issue a read');
  h.state.version=1;await h.render('visible',1,{readPaused:true});
  assert.equal(h.state.requests.length,before,'new context remains paused until its owner admits reads');
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes);
  assert.ok(nodes.every(node=>node.disabled));
  h.state.holdRoot=true;await h.render('visible',1,{readPaused:false});
  assert.equal(h.state.requests.length,before+1);assert.deepEqual(h.state.requests.at(-1).body.path,[]);
  assert.equal(h.state.requests.at(-1).body.revision,undefined);
  await h.render('visible',1,{readPaused:true});assert.equal(h.state.requests.at(-1).signal.aborted,true);
  await h.release();assert.equal(h.state.requests.length,before+1,'retired root cannot launch descendants');
  h.state.holdRoot=false;h.state.holdLeaf=true;await h.render('visible',1,{readPaused:false});
  const afterRoot=h.state.requests.length;assert.equal(h.state.requests.at(-1).body.revision,revisions[1]);
  await h.render('visible',1,{readPaused:true});assert.equal(h.state.requests.at(-1).signal.aborted,true);
  await h.release();assert.equal(h.state.requests.length,afterRoot,'retired leaf cannot continue or publish');
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes);
  h.state.holdLeaf=false;await h.render('visible',1,{readPaused:false});
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes);
  assert.ok(nodes.every(node=>!node.disabled));assert.equal(h.state.metadata.at(-1).revision,revisions[1]);
 }finally{await h.close();}
});

test('actual frozen retention wrapper keeps sixty column nodes and scroll while fresh authority gates actions',async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true,epochCount:60});let focused=0,selectedWrites=0;
 const props={selectedEpochs:['epoch-b','epoch-b-1'],highlightedEpochs:['epoch-b','epoch-b-1'],setSelectedEpochs:()=>selectedWrites++,onSelectEpoch:()=>focused++};
 try{
  await h.render('visible',0,props);await h.expand(1);await h.position(0,135);
  const nodes=[...document.querySelectorAll('[data-epoch-uuid]')],panes=[...document.querySelectorAll('.tp-column-content')];assert.equal(nodes.length,60);
  await act(()=>{panes[0].scrollTop=80;panes[1].scrollTop=190;panes[1].dispatchEvent(new window.Event('scroll'));});
  h.state.version=1;h.state.holdRoot=true;h.state.holdLeaf=true;await h.render('visible',1,props);
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes,'Wrapper must retain the actual sixty epoch nodes during root renewal');
  assert.ok(nodes.every(node=>node.disabled));const selection=nodes[0].parentElement.querySelector('.incoming-selection-switch');assert.equal(selection.disabled,true);
  await act(()=>{nodes[0].click();selection.click();});assert.equal(focused,0);assert.equal(selectedWrites,0);
  h.state.holdRoot=false;await h.release();
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes);assert.ok(nodes.every(node=>node.disabled));
  assert.equal(h.state.requests.at(-1).body.revision,revisions[1]);h.state.holdLeaf=false;await h.release();
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')],nodes,'Fresh same-cohort authority must not remount epoch rows');
  assert.ok(nodes.every(node=>!node.disabled));assert.equal(h.scroll().scrollLeft,135);
  assert.deepEqual([...document.querySelectorAll('.tp-column-content')].map(pane=>pane.scrollTop),[80,190]);
  assert.deepEqual(nodes.slice(0,3).map(node=>node.getAttribute('aria-pressed')),['true','true','false']);
  assert.deepEqual(nodes.slice(0,3).map(node=>node.getAttribute('aria-current')),['true','true',null]);
  assert.equal(selection.disabled,false);await act(()=>{nodes[0].click();selection.click();});assert.equal(focused,1);assert.equal(selectedWrites,1);
 }finally{await h.close();}
});

for(const boundary of ['project','actor','cohort','selected view'])test(`frozen retention wrapper evicts changed ${boundary}`,async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true});try{
  const context={root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:'scope-0',expected_binding_version:1,selection_token:'old-token',selection_view_key:'selected-one'};
  await h.render('visible',0,{readContext:context});await h.expand(1);const node=document.querySelector('.column-tree');
  const extra=boundary==='project'?{projectId:'other-project'}:{readContext:{...context,...(boundary==='actor'?{actor:'other'}:boundary==='cohort'?{cohort_key:'other'}:{selection_view_key:'selected-two',selection_token:'new-token'})}};
  await h.render('visible',0,{readContext:context,...extra});assert.notEqual(document.querySelector('.column-tree'),node);assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,0);
 }finally{await h.close();}
});

test('frozen wrapper retains a stable selected view through token renewal but not a token without semantic proof',async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true});try{
  const context={root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:'scope-0',expected_binding_version:1,selection_token:'old-token',selection_view_key:'selected-one'};
  await h.render('visible',0,{readContext:context});await h.expand(1);const node=document.querySelector('.column-tree');
  h.state.version=1;await h.render('visible',1,{readContext:{...context,candidate_scope_revision:'scope-1',selection_token:'new-token'}});
  assert.equal(document.querySelector('.column-tree'),node);assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,1);
  const unproven={...context,candidate_scope_revision:'scope-1',selection_token:'token-one'};delete unproven.selection_view_key;
  await h.render('visible',1,{readContext:unproven});await h.expand(1);const exact=document.querySelector('.column-tree');
  await h.render('visible',1,{readContext:{...unproven,selection_token:'token-two'}});assert.notEqual(document.querySelector('.column-tree'),exact);
 }finally{await h.close();}
});

test('frozen wrapper still unmounts hidden content instead of gaining live retention eligibility',async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true});try{
  await h.render();await h.expand(1);const node=document.querySelector('.column-tree');await h.render('hidden');assert.equal(document.querySelector('.column-tree'),null);
  await h.render();assert.notEqual(document.querySelector('.column-tree'),node);
 }finally{await h.close();}
});

test('frozen column trailing geometry keeps its exact section during pause and renewal but hides unrelated paths',async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true,epochCount:60});
 const pane=React.createElement('section',{className:'tree-trace-pane'},React.createElement('header',null,React.createElement('button',null,'Close preview')),React.createElement('div',{className:'tree-trace-body'},'Readonly trace'));
 const props={selected:'epoch-b',trailingPaneKey:'epoch-b',trailingPane:pane};
 try{
  await h.render();await h.expand(1);await h.render('visible',0,props);await h.position(0,135);
  const before=document.querySelector('.tree-trace-pane'),parent=before.parentElement;
  assert.ok(before);assert.equal(before.tagName,'SECTION');assert.equal(parent,h.scroll());
  const assertSame=()=>{assert.equal(document.querySelector('.tree-trace-pane'),before);assert.equal(before.parentElement,parent);assert.equal(before.getAttribute('inert'),'');assert.equal(before.getAttribute('aria-hidden'),'true');assert.equal(h.scroll().scrollLeft,135);};
  await h.render('visible',1,{...props,readPaused:true,actionsDisabled:true});assertSame();
  h.state.version=1;h.state.holdRoot=true;h.state.holdLeaf=true;await h.render('visible',1,props);assertSame();
  h.state.holdRoot=false;await h.release();assertSame();h.state.holdLeaf=false;await h.release();
  assert.equal(document.querySelector('.tree-trace-pane'),before);assert.equal(before.hasAttribute('inert'),false);assert.equal(h.scroll().scrollLeft,135);
  h.state.mismatchLeaf=true;await h.render('visible',2,props);assertSame();assert.ok(document.querySelector('[role="alert"]'));
  h.state.mismatchLeaf=false;
  const retry=[...document.querySelectorAll('button')].find(node=>node.textContent.includes('Show tree'));assert.ok(retry);
  await act(()=>retry.click());assert.equal(document.querySelector('.tree-trace-pane'),before);assert.equal(before.hasAttribute('inert'),false);assert.equal(h.scroll().scrollLeft,135);
  h.state.holdLeaf=true;await h.expand(0);assert.equal(document.querySelector('.tree-trace-pane'),null,'Sibling intent must remove an unrelated recording immediately');
  h.state.holdLeaf=false;await h.release();assert.equal(document.querySelector('.tree-trace-pane'),null);
 }finally{await h.close();}
});


for(const boundary of ['actor','cohort','selected view','focus'])test(`blocked frozen trailing pane never borrows a changed ${boundary}`,async()=>{
 const h=await fixture({frozen:true,columns:true,wrapped:true});try{
  const context={root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:'scope-0',expected_binding_version:1,selection_token:'token-one',selection_view_key:'view-one'};
  const pane=React.createElement('section',{className:'tree-trace-pane'},React.createElement('button',null,'Trace control'));
  const props={readContext:context,selected:'epoch-b',trailingPaneKey:'epoch-b',trailingPane:pane};
  await h.render('visible',0,{readContext:context});await h.expand(1);await h.render('visible',0,props);await h.position(0,135);assert.ok(document.querySelector('.tree-trace-pane'));
  const changed=boundary==='focus'?{selected:'other',trailingPaneKey:'other'}:{readContext:{...context,...(boundary==='actor'?{actor:'other'}:boundary==='cohort'?{cohort_key:'other'}:{selection_view_key:'view-two',selection_token:'token-two'})}};
  await h.render('visible',1,{...props,...changed,readPaused:true,actionsDisabled:true});assert.equal(document.querySelector('.tree-trace-pane'),null);
 }finally{await h.close();}
});


test('direct frozen column commit hides prior-scope trace before passive renewal begins',async()=>{
 const h=await fixture({frozen:true,columns:true,observeCommits:true});try{
  const context={root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:'scope-0',expected_binding_version:1};
  const props={readContext:context,selected:'epoch-b',trailingPaneKey:'epoch-b',trailingPane:React.createElement('section',{className:'tree-trace-pane'},'Trace')};
  await h.render();await h.expand(1);await h.render('visible',0,props);await h.position(0,135);assert.ok(document.querySelector('.tree-trace-pane'));
  const before=h.state.commits.length;h.state.holdRoot=true;
  await h.render('visible',0,{...props,readContext:{...context,actor:'other'}});
  assert.equal(h.state.commits[before].pane,false,'The first layout commit must not expose old frozen content while awaiting passive effects');
  await h.release();
 }finally{await h.close();}
});
