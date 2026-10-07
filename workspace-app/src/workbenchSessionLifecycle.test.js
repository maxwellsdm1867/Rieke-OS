import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');
const protocolId='session-protocol',candidateId='session-candidate',base=`/protocols/${protocolId}/workbench`,candidateRoot=`${base}/candidates/${candidateId}`;
const cells=[{cell_uuid:'cell-one',epochs:2,label:'Cell one',date:'2026-10-02'}];
const epochs=[1,2].map(index=>({epoch_uuid:`epoch-${index}`,cell_uuid:'cell-one',streams:[],curation:{included:true,tags:[]}}));
const context=()=>({candidate_revision_uuid:candidateId,candidate_scope_revision:'scope-one',candidate_recipe_sha256:'recipe-one',expected_binding_version:1,protocol:{definition:{protocol_uuid:protocolId},query_revision:'scope-one',expected_binding_version:1,cells},draft:{draft_version:1,selection_mode:'selected',decisions:[],decisions_total:0,decisions_truncated:false},counts:{pending_epochs:2,pending_cells:1}});
const prepared={contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-one',candidate_revision_uuid:candidateId,root:candidateRoot,candidate_scope_revision:'scope-one',queue_revision:'queue-one',context:context()};
const queue={data:{queue_revision:'queue-one',pending_epoch_count:2,pending_cell_count:1,total_candidate_count:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}},loading:false};
async function harness(){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost/'}),calls=[],errors=[];
 const key=`__workbenchSession${Math.random().toString(36).slice(2)}`,fixture={renders:0,viewer:null,prepared,contexts:new Map([[candidateId,context()]])};globalThis[key]=fixture;
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true,fetch:async(input,options={})=>{
  const url=new URL(input,'http://localhost'),path=url.pathname.replace(/^\/api/,'');calls.push({path,method:options.method||'GET'});let value;
  if(path.endsWith('/workbench/prepare'))value=fixture.prepare?await fixture.prepare():fixture.prepared;
  else if(path.endsWith('/context'))value=fixture.contexts.get(path.split('/').at(-2));
  else if(path.endsWith('/epochs')){const current=fixture.contexts.get(path.split('/').at(-2));value={epochs,cells,total:2,offset:0,limit:60,query_revision:current.candidate_scope_revision,expected_binding_version:1};}
  else if(path.includes('/epochs/'))value=epochs.find(epoch=>epoch.epoch_uuid===path.split('/').at(-1));
  else if(path==='/metadata/fields')value={fields:[]};
  else throw Error(`Unexpected request ${path}`);
  return {ok:true,status:200,json:async()=>value};
 }};
 const old=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const originalError=console.error;console.error=(...args)=>errors.push(args.map(String).join(' '));
 // Mount the actual Inspector and its resource/session effects; omit only
 // visual children that require browser layout or canvas.
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',plugins:[{
  name:'session-view-presentation',enforce:'pre',resolveId(source,importer){
   if(importer?.endsWith('/Inspector.jsx')&&source.endsWith('.jsx')&&!['./EpochBrowserChrome.jsx','../../tree-ancestors/treeBranchReads.jsx','../../components/NavigationLoading.jsx','../../components/Common.jsx','../../incoming-workbench/ui/IncomingSelectionTools.jsx'].includes(source))return `\0session-${source}`;
   if(importer?.endsWith('/FrozenIncomingReview.jsx')&&source==='../../typed-query/ui/ProtocolViewFilter.jsx')return '\0session-null';
  },load(id){
   if(id==='\0session-./EpochViewer.jsx')return `import React from 'react';const f=globalThis[${JSON.stringify(key)}];export default function Viewer(props){f.viewer=props;f.renders++;return React.createElement('div',{'data-real-inspector':true},'Actual Inspector session',props.before);}`;
   if(id==='\0session-../../traces/ui/TraceViewer.jsx')return 'function Trace(){return null;}Trace.supportsFrozenReadContext=true;export default Trace;';
   if(id.startsWith('\0session-'))return 'export default function(){return null;}';
  }
 }]});
 const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
 const container=document.getElementById('root');let mounted=createRoot(container),saved={},publications=0;
 class Boundary extends React.Component{state={error:null};static getDerivedStateFromError(error){return {error};}render(){return this.state.error?React.createElement('p',{'data-loop-error':true},this.state.error.message):this.props.children;}}
 // Bound the broken implementation so regression runs fail rather than hang.
 function Shell(props){return React.createElement(Review,{protocolId,projectId:'project-one',queue,revision:0,session:saved,onSession:value=>{publications++;if(publications>80)throw Error('Session publication loop exceeded 80 updates');saved=value;},...props});}
 const render=props=>act(async()=>mounted.render(React.createElement(React.StrictMode,null,React.createElement(Boundary,null,React.createElement(Shell,props)))));
 return {container,calls,errors,fixture,get saved(){return saved;},get publications(){return publications;},render,async settle(){await act(async()=>{await new Promise(resolve=>setTimeout(resolve,120));});},async remount(){await act(async()=>mounted.unmount());mounted=createRoot(container);await render();},async close(){await act(async()=>mounted.unmount());await server.close();console.error=originalError;dom.window.close();delete globalThis[key];for(const [key,value] of old)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}};
}

test('real Inspector session effects settle inside cumulative Workbench and preserve navigation through refresh/remount',async()=>{
 const h=await harness();try{
  await h.render();await h.settle();
  assert.equal(h.container.querySelector('[data-loop-error]')?.textContent||null,null,'Viewer session publication must not feed an endless parent update');
  assert.ok(h.container.querySelector('[data-real-inspector]'));
  assert.ok(h.publications<20,`Initial view published ${h.publications} times`);
  const initial=h.publications;await h.settle();assert.equal(h.publications,initial,'idle viewer must stop publishing');
  await act(async()=>h.fixture.viewer.treePane.listProps.onFocus('epoch-2',epochs[1]));await h.settle();
  assert.equal(h.saved.drafts[candidateId].viewer.focused,'epoch-2');
  for(let revision=1;revision<=3;revision++){await h.render({revision});await h.settle();assert.equal(h.saved.drafts[candidateId].viewer.focused,'epoch-2');assert.equal(h.container.querySelector('[data-loop-error]')?.textContent||null,null);const count=h.publications;await h.settle();assert.equal(h.publications,count);}
  await h.remount();await h.settle();assert.equal(h.saved.drafts[candidateId].viewer.focused,'epoch-2');
  assert.equal(h.calls.filter(call=>call.path===base+'/prepare').length,1);
  assert.deepEqual(h.calls.filter(call=>call.method!=='GET').map(call=>call.path),[base+'/prepare'],'browsing must not save a draft or accept/export');
  assert.deepEqual(h.errors,[]);
 }finally{await h.close();}
});

test('one draft control instance stays in the top action bar through normal and tree-design modes',async()=>{
 const h=await harness();try{
  await h.render();await h.settle();
  const controls=h.container.querySelector('.incoming-draft-tools'),host=h.container.querySelector('.incoming-draft-host');
  assert.ok(controls);assert.equal(controls.parentElement,host);assert.ok(host.closest('.incoming-action-bar'));
  assert.equal(h.container.querySelector('.incoming-browser .incoming-draft-tools'),null);
  const highlight=()=>controls.querySelector('.epoch-highlight-action');
  assert.equal(highlight().textContent.trim(),'Select Highlighted (0)');assert.equal(highlight().disabled,true);
  assert.equal(h.fixture.viewer.treePane.highlightTools,undefined);
  await act(async()=>h.fixture.viewer.treePane.listProps.setHighlightedEpochs(['epoch-1','epoch-2']));await h.settle();
  assert.equal(highlight().textContent.trim(),'Select Highlighted (2)');assert.equal(highlight().disabled,false);
  await act(async()=>highlight().click());await h.settle();assert.equal(highlight().textContent.trim(),'Deselect Highlighted (2)');
  await act(async()=>highlight().click());await h.settle();assert.equal(highlight().textContent.trim(),'Select Highlighted (2)');
  const button=()=>controls.querySelector('button.primary');assert.equal(button().textContent.trim(),'Merge (0 epochs)');assert.equal(button().disabled,true);
  await act(async()=>h.fixture.viewer.treePane.listProps.onSelectCell(cells[0],epochs[0]));await h.settle();
  assert.equal(button().textContent.trim(),'Merge (0 epochs)','cell inspection is not selection');
  await act(async()=>h.fixture.viewer.treePane.listProps.setTargets(['epoch-1','epoch-2']));await h.settle();
  assert.equal(button().textContent.trim(),'Merge (2 epochs)');
  for(let i=0;i<3;i++){
   await act(async()=>h.fixture.viewer.toolbar.onDesign());await h.settle();assert.equal(h.fixture.viewer.designMode,true);
   assert.equal(h.container.querySelector('.incoming-draft-tools'),controls);assert.equal(button().textContent.trim(),'Merge (2 epochs)');
   await act(async()=>h.fixture.viewer.toolbar.onBrowse());await h.settle();assert.equal(h.fixture.viewer.designMode,false);
   assert.equal(h.container.querySelectorAll('.incoming-draft-tools').length,1);assert.equal(h.container.querySelector('.incoming-draft-tools'),controls);
  }
  await act(async()=>h.fixture.viewer.treePane.listProps.onFocus('epoch-2',epochs[1]));await h.settle();assert.equal(button().textContent.trim(),'Merge (2 epochs)','inspection preserves explicit selection');
  await act(async()=>controls.querySelector('button[aria-pressed]').click());await h.settle();assert.equal(button().textContent.trim(),'Merge (2 epochs)');assert.equal(controls.querySelector('button[aria-pressed]').textContent.trim(),'Return to all');
  await act(async()=>controls.querySelector('button[aria-pressed]').click());await h.settle();assert.equal(button().textContent.trim(),'Merge (2 epochs)');
  assert.deepEqual(h.calls.filter(call=>call.method!=='GET').map(call=>call.path),[base+'/prepare']);assert.deepEqual(h.errors,[]);
 }finally{await h.close();}
});

function nextScope(h,{protocol=protocolId,id='replacement',token='queue-two'}={}){
 const nextContext={...context(),candidate_revision_uuid:id,candidate_scope_revision:`scope-${id}`,candidate_recipe_sha256:`recipe-${id}`,
  protocol:{...context().protocol,definition:{protocol_uuid:protocol},query_revision:`scope-${id}`}};
 const next={...prepared,candidate_revision_uuid:id,candidate_scope_revision:nextContext.candidate_scope_revision,queue_revision:token,
  root:`/protocols/${protocol}/workbench/candidates/${id}`,context:nextContext};
 h.fixture.prepared=next;h.fixture.contexts.set(id,nextContext);
 return {...queue,data:{...queue.data,queue_revision:token}};
}

test('a freshly prepared scope keeps tree mode and focus without carrying selection, edits or old read authority',async()=>{
 const h=await harness();try{
  const oldViewer={designMode:true,treeOpen:true,treeMode:true,focused:'epoch-2',focusCell:null,offset:0,
   annotationDrafts:{unsafe:'unfinished tag'},curationTagDraft:'unfinished dataset tag',
   designNavigation:{revision:'old-tree',path:['old-path'],scrollTop:81},listNavigation:{scope:'old',scrollTop:90},designPath:['old-path']};
  await h.render({session:{prepared,drafts:{[candidateId]:{viewer:oldViewer,selected:['epoch-1'],operation:'old-operation'}}}});await h.settle();
  assert.equal(h.fixture.viewer.designMode,true);
  const oldDraft=h.saved.drafts[candidateId];
  let finish;h.fixture.prepare=()=>new Promise(resolve=>{finish=resolve;});
  const updatedQueue=nextScope(h);
  await h.render({revision:1,queue:updatedQueue});await h.settle();
  assert.equal(h.fixture.viewer.designMode,true,'old view remains visible while fresh preparation is pending');
  assert.equal(h.fixture.viewer.columnTree.actionsDisabled,true,'visible old tree is inert');
  await act(async()=>finish(h.fixture.prepared));await h.settle();
  const replacement=h.saved.drafts.replacement;
  assert.equal(h.fixture.viewer.designMode,true,'fresh browser remains in the tree designer');
  assert.equal(replacement.viewer.focused,'epoch-2');
  assert.equal(replacement.viewer.treeMode,true);
  assert.deepEqual(replacement.selected,[]);
  assert.equal(replacement.operation,null);assert.equal(replacement.preview,null);assert.equal(replacement.receipt,null);
  assert.deepEqual(replacement.exportState,{});assert.equal(replacement.unconfirmed,false);assert.equal(replacement.acceptPending,false);
  assert.deepEqual(replacement.viewer.annotationDrafts,{});assert.equal(replacement.viewer.curationTagDraft,'');
  assert.equal(replacement.viewer.designNavigation,null);assert.equal(replacement.viewer.listNavigation,null);assert.deepEqual(replacement.viewer.designPath,[]);
  assert.deepEqual(h.saved.drafts[candidateId].selected,oldDraft.selected,'old candidate keeps its exact selection');
  assert.equal(h.saved.drafts[candidateId].operation,'old-operation');
  assert.ok(h.calls.some(call=>call.path.endsWith('/candidates/replacement/context')),'fresh context is still required');
  assert.deepEqual(h.calls.filter(call=>call.method!=='GET').map(call=>call.path),[base+'/prepare']);
  assert.deepEqual(h.errors,[]);
 }finally{await h.close();}
});

for(const different of ['existing viewer','project','protocol'])test(`presentation handoff respects ${different} boundary`,async()=>{
 const h=await harness();try{
  const drafts={[candidateId]:{viewer:{designMode:true,focused:null}}};
  if(different==='existing viewer')drafts.replacement={viewer:{designMode:false,treeOpen:false,focused:null}};
  await h.render({session:{prepared,drafts}});await h.settle();assert.equal(h.fixture.viewer.designMode,true);
  const nextProtocol=different==='protocol'?'another-protocol':protocolId;
  const nextQueue=nextScope(h,{protocol:nextProtocol});
  await h.render({revision:1,queue:nextQueue,protocolId:nextProtocol,projectId:different==='project'?'another-project':'project-one'});await h.settle();
  assert.equal(h.fixture.viewer.designMode,false);
  if(different==='existing viewer')assert.equal(h.saved.drafts.replacement.viewer.treeOpen,false);
  assert.deepEqual(h.saved.drafts.replacement.selected,[]);
  assert.deepEqual(h.errors,[]);
 }finally{await h.close();}
});
