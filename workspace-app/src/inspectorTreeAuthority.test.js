import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

// Actual Inspector, viewer, PagedTree, HierarchyTree, hooks and selection reader.
// Only HTTP and browser platform are fixtures; no component or hook replacement.
async function mountFixture({ownerProjectPath='/owned-fixture'}={}){
 const dom=new JSDOM('<div id="root"></div>',{url:'http://fixture/',pretendToBeVisual:true}),saved=new Map();
 const put=(key,value)=>{saved.set(key,Object.getOwnPropertyDescriptor(globalThis,key));Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});};
 for(const key of ['window','document','navigator','localStorage','HTMLElement','MutationObserver'])put(key,dom.window[key]);
 put('requestAnimationFrame',fn=>setTimeout(()=>fn(performance.now()),0));put('cancelAnimationFrame',clearTimeout);
 put('ResizeObserver',class {observe(){}unobserve(){}disconnect(){}});
 // JSDOM has no canvas renderer; samples are absent and no drawing claim is made.
 dom.window.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:()=>({width:0})},{get:(target,key)=>target[key]||(()=>{})});
 dom.window.HTMLElement.prototype.scrollIntoView=function(){};dom.window.HTMLElement.prototype.scrollTo=function(){};
 const big=Array.from({length:121},(_,i)=>({epoch_uuid:`big-${i}`,cell_uuid:'cell-big',cell_label:'Big',date:'2026-10-04',epoch_number:i+1,streams:[],parameters:{},curation:{included:true,tags:[],review_state:'unreviewed'},annotations:{cell_tags:[],epoch_tags:[],effective_tags:[],revisions:{cell:{},epoch:{}}}}));
 const other=Array.from({length:4},(_,i)=>({...big[i],epoch_uuid:`other-${i}`,cell_uuid:'cell-other',cell_label:'Other'}));
 // Deliberately different flat/tree layouts: big59 is outside flat page zero.
 const flat=[...other,...big],cells=[{cell_uuid:'cell-big',label:'Big',date:'2026-10-04',epochs:121},{cell_uuid:'cell-other',label:'Other',date:'2026-10-04',epochs:4}];
 const fixture={requests:[],errors:[],query:'query-1',binding:2,treeRevision:'tree-1',hold:null};
 const selectedRows=(rows,filters)=>filters?.tag_predicate?rows.filter(row=>row.epoch_uuid!=='big-0'):rows;
 const page=offset=>({kind:'epochs',ancestors:[{key:'big-branch',parent_offset:0}],path:['big-branch'],offset,limit:60,total:121,has_more:offset+60<121,depth:1,split_order:['cell'],levels:[{field:'cell',label:'Cell'}],revision:fixture.treeRevision,epochs:big.slice(offset,offset+60),branches:[],fields:[{field:'cell',label:'Cell'}]});
 put('fetch',async(input,options={})=>{
  const url=new URL(input,'http://fixture'),body=options.body?JSON.parse(options.body):null;
  const request={path:url.pathname+url.search,body,signal:options.signal,at:Date.now()};fixture.requests.push(request);if(fixture.requests.length>150)throw Error('Unbounded test HTTP requests: '+request.path);let result;
  if(url.pathname==='/api/protocols/protocol-A/epochs'){
   const members=selectedRows(flat,Object.fromEntries(url.searchParams)),anchor=url.searchParams.get('anchor_uuid'),offset=anchor?Math.floor(members.findIndex(row=>row.epoch_uuid===anchor)/60)*60:Number(url.searchParams.get('offset')||0);
   result={offset,limit:60,total:members.length,epochs:members.slice(offset,offset+60),cells,query_revision:fixture.query,expected_binding_version:fixture.binding};
  }else if(url.pathname==='/api/tree-pages')result=body.anchor_uuid?page(Math.floor(big.findIndex(row=>row.epoch_uuid===body.anchor_uuid)/60)*60):body.path.length?page(body.offset):{kind:'branches',path:[],offset:0,limit:60,total:1,has_more:false,depth:0,split_order:['cell'],levels:[{field:'cell',label:'Cell'}],revision:fixture.treeRevision,fields:[{field:'cell',label:'Cell'}],field:{field:'cell',label:'Cell'},branches:[{key:'big-branch',path:['big-branch'],value:'cell-big',label:'Big',count:121}],epochs:[]};
  else if(/^\/api\/epochs\/[^/]+$/.test(url.pathname))result=flat.find(row=>row.epoch_uuid===url.pathname.split('/').at(-1));
  else if(url.pathname==='/api/annotation-profiles')result={profiles:[{profile_uuid:'author-A',display_name:'Fixture author'}],selected_profile_uuid:'author-A'};
  else if(url.pathname==='/api/protocols/protocol-A/tree-fields')result={fields:[]};
  else if(['/api/metadata/fields','/api/explore/field-registry'].includes(url.pathname))result={fields:[]};
  else if(['/api/annotation-tags','/api/tags'].includes(url.pathname))result={tags:[]};
  else if(url.pathname.endsWith('/exports'))result={exports:[]};
  else if(url.pathname==='/api/annotations/read')result={targets:Object.fromEntries(body.target_uuids.map(id=>[id,{target_uuid:id,target_kind:body.target_kind,tags:[],revisions:{}}]))};
  else {fixture.errors.push(request.path);throw Error('Unexpected HTTP fixture request: '+request.path);}
  if(url.pathname==='/api/tree-pages'&&body.filters?.tag_predicate){
   if(body.anchor_uuid==='big-0'){request.completed=Date.now();return {ok:false,status:400,json:async()=>({error:'Epoch is outside this tree selection'})};}
   const members=selectedRows(big,body.filters);
   result={...result,total_epochs:members.length,...(result.kind==='epochs'?{epochs:members.slice(body.offset,body.offset+60),total:members.length,has_more:body.offset+60<members.length}:{branches:result.branches.map(branch=>({...branch,count:members.length}))})};
  }
  if(fixture.hold)await fixture.hold(request);request.completed=Date.now();return {ok:true,status:200,json:async()=>result};
 });
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Inspector}=await server.ssrLoadModule('/src/epoch-browser/ui/Inspector.jsx');
 const {AnnotationProfileProvider}=await server.ssrLoadModule("/src/annotations/annotationProfile.js");
 const {TreeBranchReadOwner}=await server.ssrLoadModule('/src/tree-ancestors/treeBranchReads.jsx');
 const {createTreeBranchReadCache}=await server.ssrLoadModule('/src/tree-ancestors/treeBranchReadCache.js');
 const cache=createTreeBranchReadCache();
 const props={projectId:'project',protocol:{definition:{protocol_uuid:'protocol-A',name:'Fixture'},query_revision:'query-1',expected_binding_version:2,cells},filters:{},revision:0,splitRecipe:['cell'],initialNavigation:{treeMode:true}};
 const root=createRoot(document.getElementById('root'));
 const render=async(extra={})=>{await act(async()=>root.render(React.createElement(AnnotationProfileProvider,{projectId:'project'},React.createElement(TreeBranchReadOwner,{projectId:'project',projectPath:Object.hasOwn(extra,'ownerProjectPath')?extra.ownerProjectPath:ownerProjectPath,revision:extra.revision??0,cache},React.createElement(React.Activity,{mode:extra.hidden?'hidden':'visible'},React.createElement(Inspector,{...props,...extra}))))));};
 const settle=async()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,20));});
 const wait=async(predicate,label)=>{for(let i=0;i<100;i++){if(predicate())return;await settle();}assert.fail(label+'; alerts='+[...document.querySelectorAll('[role=alert]')].map(node=>node.textContent)+'; unexpected='+fixture.errors);};
 const click=async(node,shiftKey=false)=>{assert.ok(node,'Rendered control exists');assert.equal(node.disabled,false,'Rendered control enabled');await act(async()=>node.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true,shiftKey})));};
 const leaf=i=>document.querySelector(`[data-epoch-uuid="big-${i}"]`);
 const button=label=>[...document.querySelectorAll('button')].find(node=>node.getAttribute('aria-label')===label);
 try{await render();}catch(error){await act(async()=>root.unmount());await server.close();dom.window.close();for(const [key,descriptor]of saved){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}throw error;}
 return {fixture,cache,props,render,
  async retained({active,selected='big-0',revision=0,ownerRevision=0,...treeProps}){
   const {default:Host}=await server.ssrLoadModule('/src/tree-browser/ui/RetainedTreePresentation.jsx');
   await act(async()=>root.render(React.createElement(AnnotationProfileProvider,{projectId:'project'},React.createElement(TreeBranchReadOwner,{projectId:'project',projectPath:'/owned-fixture',revision:ownerRevision,cache},React.createElement(Host,{active,tree:{protocolId:'protocol-A',filters:{},splits:'cell',revision,selected,...treeProps}})))));
  },settle,wait,click,leaf,button,async open(){await wait(()=>document.querySelector('.ht-branch > button'),'cell branch');await click(document.querySelector('.ht-branch > button'));await wait(()=>leaf(0)&&!leaf(0).disabled,'first tree page ready');},async close(){await act(async()=>root.unmount());await server.close();dom.window.close();for(const [key,descriptor]of saved){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}};
}

test('tree 60/61 range retains its first-click anchor through same-authority flat-list navigation',async()=>{
 const h=await mountFixture();try{
  await h.open();
  await h.wait(()=>document.querySelector('#epoch-metadata-sidebar .annotation-composer input')&&!document.querySelector('#epoch-metadata-sidebar .annotation-composer input').disabled,'valid profile permits tag editing before navigation');
  assert.equal(document.querySelector('.ht-leaf .epoch-inclusion-toggle').disabled,false);
  let release;const pending=new Promise(resolve=>{release=resolve;});
  h.fixture.hold=request=>request.path.includes('anchor_uuid=big-59')?pending:undefined;
  await h.click(h.leaf(59));
  await h.wait(()=>h.fixture.requests.some(row=>row.path.includes('anchor_uuid=big-59')),'flat focus locator started');
  assert.equal(h.leaf(59).disabled,true,'Selection initiation stays gated during pending receipt');
  assert.equal(document.querySelector('.hierarchy-tree .tree-group-tag-button').disabled,true,'Tree group tag mutation remains gated');
  // StableContent retains prior metadata under aria-hidden while loading. Its
  // preexisting inert='' React warning is disclosed; not a disabled-input proof.
  assert.equal(document.querySelector('.ht-leaf .epoch-inclusion-toggle').disabled,true,'Inclusion remains gated');
  release();
  await h.wait(()=>h.fixture.requests.some(row=>row.path.includes('anchor_uuid=big-59')&&row.completed),'flat focus locator completed');
  await h.wait(()=>h.leaf(59)&&!h.leaf(59).disabled,'same-authority focus navigation settled');
  await h.click(h.button('Next Epochs page'));await h.wait(()=>h.leaf(60)&&!h.leaf(60).disabled,'second tree page ready');
  await h.click(h.leaf(60),true);await h.settle();
  await h.wait(()=>document.querySelector('#epoch-metadata-sidebar h2')?.textContent==='2 epochs','Expected exact two-epoch range after original anchor, no reanchor');
  const actual=[...document.querySelectorAll('[data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid);
  await h.click(h.button('Previous Epochs page'));await h.wait(()=>h.leaf(59)&&!h.leaf(59).disabled,'first tree page restored');
  actual.unshift(...[...document.querySelectorAll('[data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid));
  assert.deepEqual(actual,['big-59','big-60']);assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

// The other end of the same bug: the initial anchor is loaded, but focusing
// the shift target changes the flat page while a real range reader is pending.
test('tree 0 through 60 range can publish after same-authority target focus lookup',async()=>{
 const h=await mountFixture();let release;try{
  await h.open();await h.click(h.leaf(0));
  await h.click(h.button('Next Epochs page'));await h.wait(()=>h.leaf(60)&&!h.leaf(60).disabled,'second tree page ready');
  const pending=new Promise(resolve=>{release=resolve;});
  h.fixture.hold=request=>request.path==='/api/tree-pages'&&request.body.path.length&&request.body.offset===0?pending:undefined;
  const start=h.fixture.requests.length;await h.click(h.leaf(60),true);
  await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path==='/api/tree-pages'&&row.body.offset===0),'actual supplemental range read started');
  await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path.includes('anchor_uuid=big-60')&&row.completed),'target focus lookup completed');
  release();await h.wait(()=>document.querySelector('#epoch-metadata-sidebar h2')?.textContent==='61 epochs','Expected 61-epoch publication after same-authority focus lookup');
  const actual=[...document.querySelectorAll('[data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid);
  await h.click(h.button('Previous Epochs page'));await h.wait(()=>h.leaf(0)&&!h.leaf(0).disabled,'first tree page restored');
  actual.unshift(...[...document.querySelectorAll('[data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid));
  assert.deepEqual(actual,Array.from({length:61},(_,i)=>`big-${i}`));assert.deepEqual(h.fixture.errors,[]);
 }finally{release?.();await h.close();}
});

for(const change of ['revision','binding','filter','query','paused','draft-disabled','hidden','owner-retired','explicit-cancel','failed-flat-receipt','mismatched-flat-receipt']){
 test(`mounted split tree rejects late range publication after ${change}`,async()=>{
  const h=await mountFixture();let release;try{
   await h.open();await h.click(h.leaf(0));
   await h.click(h.button('Next Epochs page'));await h.wait(()=>h.leaf(60)&&!h.leaf(60).disabled,'second page');
   const pending=new Promise(resolve=>{release=resolve;});
   h.fixture.hold=request=>{
    if(request.path==='/api/tree-pages'&&request.body.path.length&&request.body.offset===0)return pending;
    if(change==='failed-flat-receipt'&&request.path.includes('anchor_uuid=big-60'))throw Error('Flat authority unavailable');
   };
   if(change==='mismatched-flat-receipt'){h.fixture.query='query-changed';h.fixture.binding=3;}
   const start=h.fixture.requests.length;await h.click(h.leaf(60),true);
   await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path==='/api/tree-pages'&&row.body.offset===0),'pending real range');
   if(change==='revision')await h.render({revision:1});
   if(change==='binding')await h.render({protocol:{...h.props.protocol,expected_binding_version:3}});
   if(change==='query')await h.render({protocol:{...h.props.protocol,query_revision:'query-next'}});
   if(change==='filter')await h.render({filters:{cell_type:'other'}});
   if(change==='paused')await h.render({readPaused:true});
   if(change==='draft-disabled')await h.render({draftSelection:{disabled:true}});
   if(change==='hidden')await h.render({hidden:true});
   // Public injected cache retirement is synchronous and does not cause React
   // to render: this specifically detects a missing completion-time owner check.
   if(change==='owner-retired'){await h.wait(()=>h.leaf(60)&&!h.leaf(60).disabled,'settled focus before synchronous retirement');await h.settle();h.cache.retire();}
   if(change==='explicit-cancel'){await h.wait(()=>h.leaf(61)&&!h.leaf(61).disabled,'new click ready');await h.click(h.leaf(61));}
   if(change!=='owner-retired')await h.settle();release();await h.settle();await h.settle();
   assert.notEqual(document.querySelector('#epoch-metadata-sidebar h2')?.textContent,'61 epochs','Obsolete range must not publish');
   assert.ok(document.querySelectorAll('[data-epoch-uuid].selected').length<=1,'Only display focus may remain');
   assert.deepEqual(h.fixture.errors,[]);
  }finally{release?.();await h.close();}
 });
}

test('actual retained design tree preserves active focus anchor across its column pages',async()=>{
 const h=await mountFixture();try{
  await h.open();await h.click(h.button('Open and edit tree'));
  await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-0"]')&&!document.querySelector('.column-tree [data-epoch-uuid="big-0"]').disabled,'design first page');
  const leaf=i=>document.querySelector(`.column-tree [data-epoch-uuid="big-${i}"]`);
  const first=leaf(59);await h.click(first);
  await h.wait(()=>leaf(59)&&!leaf(59).disabled,'focus navigation ready');
  assert.ok(leaf(59)===first,'Active focus must retain the mounted selection owner');
  await h.click(h.button('Next page in column 2'));await h.wait(()=>leaf(60)&&!leaf(60).disabled,'design second page');
  await h.click(leaf(60),true);
  await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-60"].selected'),'shift target');
  await h.click(h.button('Previous page in column 2'));await h.wait(()=>leaf(59)&&!leaf(59).disabled,'return design first page');
  assert.equal(leaf(59).classList.contains('selected'),true,'Original anchor is a selected UUID');
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

test('actual retained wrapper evicts hidden A/B/A and changed-on-return focus without reviving old rows',async()=>{
 const h=await mountFixture();try{
  const leaf=id=>document.querySelector(`.column-tree [data-epoch-uuid="${id}"]`);
  await h.retained({active:true});await h.wait(()=>leaf('big-0')&&!leaf('big-0').disabled,'initial retained view');const original=leaf('big-0');
  await h.retained({active:false});assert.ok(leaf('big-0')===original,'same exact hidden view retained');
  await h.retained({active:false,selected:'big-60'});assert.equal(leaf('big-0'),null,'hidden new focus evicts');
  await h.retained({active:false,selected:'big-0'});assert.equal(leaf('big-0'),null,'hidden A/B/A cannot resurrect old slot');
  await h.retained({active:true});await h.wait(()=>leaf('big-0')&&!leaf('big-0').disabled,'new active slot');assert.ok(leaf('big-0')!==original);
  const returned=leaf('big-0');await h.retained({active:false});await h.retained({active:true,selected:'big-60'});
  await h.wait(()=>leaf('big-60')&&!leaf('big-60').disabled,'changed-on-return locator');assert.equal(returned.isConnected,false);
  await h.retained({active:false,selected:'big-60'});await h.retained({active:false,selected:'big-60',ownerRevision:1});assert.equal(leaf('big-60'),null,'owner-only change evicts');
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

test('design tree external out-of-page focus blocks old mutation controls until originating locator finishes',async()=>{
 const h=await mountFixture();let release;try{
  await h.open();await h.click(h.button('Open and edit tree'));
  await h.wait(()=>document.querySelector('.column-tree .epoch-inclusion-toggle')&&!document.querySelector('.column-tree .epoch-inclusion-toggle').disabled,'validated design mutation baseline');
  const pending=new Promise(resolve=>{release=resolve;});h.fixture.hold=request=>request.path==='/api/tree-pages'&&request.body.anchor_uuid==='big-120'?pending:undefined;
  await h.render({initialEpochUuid:'big-120'});
  await h.wait(()=>h.fixture.requests.some(row=>row.body?.anchor_uuid==='big-120'&&row.path==='/api/tree-pages'),'external tree locator started');
  assert.equal(document.querySelector('.column-tree .epoch-inclusion-toggle').disabled,true);
  assert.equal(document.querySelector('.column-tree .tree-group-tag-button').disabled,true);
  release();await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-120"]')&&!document.querySelector('.column-tree .epoch-inclusion-toggle').disabled,'fresh out-of-page focus proof');
  assert.deepEqual(h.fixture.errors,[]);
 }finally{release?.();await h.close();}
});

for(const change of ['unchanged','revision','binding','owner-replaced','owner-retired','hide','hide-late-failure']){
 test(`actual design range delayed publication: ${change}`,async()=>{
  const h=await mountFixture();let release;try{
   await h.open();await h.click(h.button('Open and edit tree'));await h.click(h.button('Show tree selection tags'));
   const leaf=i=>document.querySelector(`.column-tree [data-epoch-uuid="big-${i}"]`);
   const ready=()=>leaf(0)&&!document.querySelector('.column-tree .tree-group-tag-button').disabled;
   await h.wait(ready,'design ready');await h.click(leaf(0));
   await h.click(h.button('Next page in column 2'));await h.wait(()=>leaf(60)&&!document.querySelector('.column-tree .tree-group-tag-button').disabled,'design next ready');
   const pending=new Promise((resolve,reject)=>{release=()=>change==='hide-late-failure'?reject(Error('Obsolete range failure')):resolve();});
   h.fixture.hold=request=>request.path==='/api/tree-pages'&&request.body.path.length&&request.body.offset===0?pending:undefined;
   const start=h.fixture.requests.length;await h.click(leaf(60),true);
   await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path==='/api/tree-pages'&&row.body.offset===0),'actual design supplemental read');
   if(change==='revision')await h.render({revision:1});
   if(change==='binding')await h.render({protocol:{...h.props.protocol,expected_binding_version:3}});
   if(change==='owner-replaced')await h.render({ownerProjectPath:'/replacement-fixture'});
   if(change==='owner-retired'){
    await h.wait(()=>!document.querySelector('.column-tree .tree-group-tag-button').disabled&&document.querySelector('.tree-selection-tags .annotation-composer input')&&document.querySelector('.tree-preview-identity')?.textContent.includes('Epoch 61'),'settled design detail before synchronous retirement');
    await h.settle();h.cache.retire();
   }
   if(change.startsWith('hide'))await h.click([...document.querySelectorAll('button')].find(node=>node.textContent===' Back to epochs'));
   release();await h.settle();await h.settle();
   if(change==='owner-retired'){
    const target=document.querySelector('.tree-selection-tags .annotation-composer input');
    assert.ok(target,'Visible design tag target exists');
    assert.equal(target.closest('[hidden]'),null,'Assertion uses the active design preview, not hidden metadata');
    assert.equal(target.getAttribute('aria-label'),'Tag this epoch','Retired owner must not publish 61 selected tag targets');
   }
   if(change==='unchanged'){
    await h.wait(()=>leaf(60)?.classList.contains('selected'),'selected target');
    const actual=[...document.querySelectorAll('.column-tree [data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid);
    h.fixture.hold=null;await h.click(h.button('Previous page in column 2'));await h.wait(()=>leaf(0)&&!leaf(0).disabled,'selected first page');
    actual.unshift(...[...document.querySelectorAll('.column-tree [data-epoch-uuid].selected')].map(node=>node.dataset.epochUuid));
    assert.deepEqual(actual,Array.from({length:61},(_,i)=>`big-${i}`));
    assert.equal(document.querySelector('.tree-selection-tags .annotation-composer input')?.getAttribute('aria-label'),'Tag 61 selected epochs','Visible target label detects the positive selection');
   }else {
    assert.ok(document.querySelectorAll('.column-tree [data-epoch-uuid].selected').length<=1,'Only display focus may remain');
    // A published 61-range has only one selected row on page60. Inspect the
    // public previous page as well; page-local count alone cannot detect it.
    if(!change.startsWith('hide')&&change!=='owner-retired'){
     h.fixture.hold=null;const previous=h.button('Previous page in column 2');
     if(previous&&!previous.disabled){await h.click(previous);await h.wait(()=>leaf(0)&&!leaf(0).disabled,'first page after revocation');assert.equal(document.querySelectorAll('.column-tree [data-epoch-uuid].selected').length,0,'No old range IDs on first page');}
    }
    assert.notEqual(document.querySelector('#epoch-metadata-sidebar h2')?.textContent,'61 epochs');
   }
   assert.ok(![...document.querySelectorAll('.tree-view-workspace [role=alert]')].some(node=>node.textContent.includes('Obsolete range failure')),'Late failure must not publish');
   assert.deepEqual(h.fixture.errors,[]);
  }finally{release?.();await h.close();}
 });
}

test('actual retained wrapper rejects malformed opt-in authority and keeps omitted legacy behavior',async()=>{
 const h=await mountFixture();let focuses=0;try{
  const leaf=()=>document.querySelector('.column-tree [data-epoch-uuid="big-0"]');
  for(const proof of [null,{}, {identity:'a',available:true}, {identity:'',available:true,current:()=>true}, {identity:'a',available:1,current:()=>true}, {identity:'a',available:true,current:()=>{throw Error('Unavailable');}}]){
   await h.retained({active:true,selectionAuthority:proof,onSelectEpoch:()=>focuses++});await h.wait(()=>leaf()&&!leaf().disabled,'rendered actual column');
   await h.click(leaf());assert.equal(focuses,0,'Malformed proof may not initiate');
  }
  await h.retained({active:true,onSelectEpoch:()=>focuses++});await h.click(leaf());assert.equal(focuses,1,'Omitted proof retains legacy initiation');
 }finally{await h.close();}
});

test('old design locator completion cannot relabel metadata or release replacement-scope controls',async()=>{
 const h=await mountFixture();let releaseOld,releaseNew;try{
  await h.open();await h.click(h.button('Open and edit tree'));
  await h.wait(()=>document.querySelector('.column-tree .epoch-inclusion-toggle')&&!document.querySelector('.column-tree .epoch-inclusion-toggle').disabled,'initial design ready');
  const old=new Promise(resolve=>{releaseOld=resolve;}),fresh=new Promise(resolve=>{releaseNew=resolve;});
  h.fixture.hold=request=>request.path==='/api/tree-pages'?(request.body.filters?.cell_type==='replacement'?fresh:request.body.anchor_uuid==='big-120'?old:undefined):undefined;
  await h.render({initialEpochUuid:'big-120'});await h.wait(()=>h.fixture.requests.some(row=>row.body?.anchor_uuid==='big-120'),'old locator started');
  await h.render({initialEpochUuid:'big-120',filters:{cell_type:'replacement'}});
  await h.wait(()=>h.fixture.requests.some(row=>row.body?.filters?.cell_type==='replacement'),'replacement tree started');
  releaseOld();await h.settle();await h.settle();
  assert.ok(![...document.querySelectorAll('.column-tree .epoch-inclusion-toggle')].some(node=>!node.disabled),'Old success cannot unlock replacement controls');
  assert.equal(document.querySelector('.column-tree [data-epoch-uuid="big-120"]'),null,'Old metadata may not publish under replacement scope');
  releaseNew();await h.wait(()=>document.querySelector('.column-tree .tp-branch'),'replacement root publishes its own result');
  assert.equal(document.querySelector('.column-tree [data-epoch-uuid="big-120"]'),null,'Filter change retires prior focus');
  assert.ok(h.fixture.requests.filter(row=>row.body?.filters?.cell_type==='replacement').every(row=>!row.body.anchor_uuid),'Replacement must not reuse the old focus locator');
  assert.deepEqual(h.fixture.errors,[]);
 }finally{releaseOld?.();releaseNew?.();await h.close();}
});

test('fresh real provider with unavailable project scope rejects selection despite valid page and profile receipts',async()=>{
 const h=await mountFixture({ownerProjectPath:null});try{
  await h.open();
  assert.ok(h.fixture.requests.some(row=>row.path==='/api/annotation-profiles'&&row.completed),'Real profile receipt completed');
  assert.ok(h.fixture.requests.some(row=>row.path.includes('/protocols/protocol-A/epochs?')&&row.completed),'Fresh flat authority receipt completed');
  assert.ok(h.fixture.requests.some(row=>row.path==='/api/tree-pages'&&row.body.path.length&&row.completed),'Real tree page completed');
  await h.click(h.leaf(59));
  await h.click(h.button('Next Epochs page'));await h.wait(()=>h.leaf(60)&&!h.leaf(60).disabled,'next tree page');
  await h.click(h.leaf(60),true);await h.settle();
  assert.equal(document.querySelectorAll('.hierarchy-tree [data-epoch-uuid].selected').length,0,'Unavailable owner cannot grant focus or range selection');
  assert.equal(h.fixture.requests.some(row=>row.path.includes('anchor_uuid=')),false,'Unavailable provider cannot initiate focus locator');
  assert.match(document.body.textContent,/Choose an epoch/);
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

test('real provider null to available permits its first gesture after ordinary readiness',async()=>{
 const h=await mountFixture({ownerProjectPath:null});try{
  await h.open();
  const start=h.fixture.requests.length;
  await h.render({ownerProjectPath:'/owned-fixture'});
  // HierarchyTree's scope key does not include provider ownership: matching
  // completed flat/tree receipts remain current; no fresh tree load is expected.
  await h.wait(()=>h.leaf(59)&&!h.leaf(59).disabled,'ordinary rendered selection readiness');
  assert.ok(h.fixture.requests.some(row=>row.path==='/api/annotation-profiles'&&row.completed),'Valid profile receipt');
  assert.ok(h.fixture.requests.some(row=>row.path.includes('/protocols/protocol-A/epochs?')&&row.completed),'Completed matching flat receipt');
  assert.ok(h.fixture.requests.some(row=>row.path==='/api/tree-pages'&&row.body.path.length&&row.completed),'Completed matching tree receipt');
  assert.equal(h.fixture.requests.some(row=>row.path.includes('anchor_uuid=big-59')),false,'No prior focus gesture');
  await h.click(h.leaf(59));
  await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path.includes('anchor_uuid=big-59')&&row.completed),'First valid gesture starts and completes focus locator');
  await h.wait(()=>h.leaf(59)?.classList.contains('selected'),'First gesture publishes focus');
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

for(const design of [false,true])test(`filter change retires excluded focus before ${design?'column':'hierarchy'} tree reads`,async()=>{
 const h=await mountFixture();try{
  await h.open();await h.click(h.leaf(0));
  await h.wait(()=>h.leaf(0)?.classList.contains('selected'),'initial focused epoch');
  if(design){await h.click(h.button('Open and edit tree'));await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-0"]'),'focused design');}
  const start=h.fixture.requests.length;
  const filters={tag_predicate:JSON.stringify({all:[{not:{field:'annotations/epoch/tags',operator:'contains',value:'tagged'}}]})};
  await h.render({filters});
  await h.wait(()=>h.fixture.requests.slice(start).some(row=>row.path==='/api/tree-pages'&&row.body.filters?.tag_predicate&&row.completed),'new filter tree read');
  await h.settle();
  const reads=h.fixture.requests.slice(start).filter(row=>row.path==='/api/tree-pages');
  assert.ok(reads.length>0);assert.ok(reads.every(row=>!row.body.anchor_uuid),'Retired focus must not anchor the replacement filter');
  assert.ok(!document.body.textContent.includes('Epoch is outside this tree selection'));
  assert.ok(document.querySelector(design?'.column-tree .tp-branch':'.ht-branch > button'),'Replacement root remains browsable');
  if(design)assert.equal(document.querySelector('.tree-trace-pane'),null,'Filter change removes the old trace pane');
  const clearStart=h.fixture.requests.length;await h.render({filters:{}});
  await h.wait(()=>h.fixture.requests.slice(clearStart).some(row=>row.path==='/api/tree-pages'&&row.completed),'clear filter root');
  assert.ok(h.fixture.requests.slice(clearStart).filter(row=>row.path==='/api/tree-pages').every(row=>!row.body.anchor_uuid));
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

test('explicit replacement-scope epoch navigation still anchors its requested target',async()=>{
 const h=await mountFixture();try{
  await h.open();await h.click(h.leaf(0));await h.click(h.button('Open and edit tree'));
  await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-0"]'),'initial design focus');
  const start=h.fixture.requests.length;
  await h.render({filters:{cell_type:'replacement'},initialEpochUuid:'big-120'});
  await h.wait(()=>document.querySelector('.column-tree [data-epoch-uuid="big-120"]'),'explicit new target');
  assert.ok(h.fixture.requests.slice(start).some(row=>row.body?.filters?.cell_type==='replacement'&&row.body.anchor_uuid==='big-120'));
  assert.ok(h.fixture.requests.slice(start).every(row=>row.body?.anchor_uuid!=='big-0'));
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});

test('column design keeps a trace-only pane beside terminal epochs and closes it with its branch',async()=>{
 const h=await mountFixture();try{
  await h.open();await h.click(h.button('Open and edit tree'));
  await h.wait(()=>document.querySelector('.tree-trace-pane .tree-preview-identity'),'trace pane');
  const pane=document.querySelector('.tree-trace-pane');
  assert.equal(pane.parentElement.className,'tp-columns');
  assert.ok(pane.previousElementSibling.classList.contains('tp-terminal'));
  assert.equal(pane.querySelector('.annotation-composer,.curation-bar,.metadata-panel'),null);
  assert.equal(document.querySelector('.tree-recording-preview'),null);
  await h.click(document.querySelector('.column-tree [data-epoch-uuid="big-1"]'));
  await h.wait(()=>document.querySelector('.tree-trace-pane')?.textContent.includes('Epoch 2'),'changed trace identity');
  await h.click(h.button('Close raw recording preview'));
  assert.equal(document.querySelector('.tree-trace-pane'),null);
  await h.click(h.button('Show raw recording preview'));
  await h.wait(()=>document.querySelector('.tree-trace-pane'),'reopened trace');
  await h.click(document.querySelector('.column-tree .tp-branch.selected'));
  await h.wait(()=>!document.querySelector('.tp-terminal'),'closed branch');
  assert.equal(document.querySelector('.tree-trace-pane'),null);
  assert.deepEqual(h.fixture.errors,[]);
 }finally{await h.close();}
});
