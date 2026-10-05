import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const root=fileURLToPath(new URL('..',import.meta.url));
const create=(plugins=[])=>createServer({plugins,root,configFile:false,optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
const frozenBrowserProbe={name:'frozen-browser-probe',enforce:'pre',resolveId(source,importer){if(importer?.endsWith('/FrozenIncomingReview.jsx')&&['../../components/Inspector.jsx','../../typed-query/ui/ProtocolViewFilter.jsx'].includes(source))return `\0probe-${source}`;},load(id){if(id==='\0probe-../../components/Inspector.jsx')return `import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default function Inspector(props){return React.createElement('div',{'data-frozen-scope':props.readContext.candidate_scope_revision,'data-revision':props.revision});}`;if(id==='\0probe-../../typed-query/ui/ProtocolViewFilter.jsx')return `export default function Filter(){return null;}`;}};

test('selected merge requires explicit review, saves exact selection and preserves exclusions before preview',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch,calls=[];let renderer;
 let context={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'selected',decisions:[{epoch_uuid:'old',selected:true,reviewed:true,excluded:true}],decisions_total:1,decisions_truncated:false},counts:{pending_epochs:2,pending_cells:1},protocol:{definition:{protocol_uuid:'history'}}};
 globalThis.fetch=async(path,options={})=>{
  if(options.method==='PATCH'){const body=JSON.parse(options.body);calls.push({path,body});assert.equal(body.expected_version,context.draft.draft_version);assert.equal(body.expected_candidate_scope_revision,'scope');const decisions=[...context.draft.decisions];for(const next of body.decisions){const index=decisions.findIndex(value=>value.epoch_uuid===next.epoch_uuid),value={selected:false,reviewed:false,excluded:false,...decisions[index],...next};if(index<0)decisions.push(value);else decisions[index]=value;}context={...context,draft:{...context.draft,draft_version:context.draft.draft_version+1,decisions,decisions_total:decisions.length}};}
  if(options.method==='POST'){assert.ok(String(path).endsWith('/preview'));const body=JSON.parse(options.body);calls.push({path,body});assert.equal(body.expected_draft_version,2);assert.equal(body.mode,'selected');return {ok:true,status:200,json:async()=>({preview_sha256:'sealed',expected_binding_version:2,expected_query_revision:'query',selected_epoch_count:2,accepted_epoch_count:2,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:42,accepted_cell_count:1})};}
  return {ok:true,status:200,json:async()=>context};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'history',item:{candidate_revision_uuid:'candidate'},capabilities:{drafts:true,frozen_browse:true,additive_accept:true}}));});
  const inspector=()=>renderer.root.find(node=>node.type?.name==='Inspector');
  await act(async()=>inspector().props.onSelectionChange(['a','b']));assert.deepEqual(calls,[]);
  await act(async()=>inspector().props.draftSelection.onMerge(['a','b']));assert.deepEqual(calls,[],'opening review must not auto-review');
  assert.equal(inspector().props.draftSelection.disabled,true);
  const review=renderer.root.findAllByType('button').find(node=>label(node)==='Mark selected reviewed & preview');
  await act(async()=>review.props.onClick());
  assert.deepEqual(calls[0].body.decisions,[{epoch_uuid:'old',selected:false},{epoch_uuid:'a',selected:true,reviewed:true},{epoch_uuid:'b',selected:true,reviewed:true}]);
  assert.deepEqual(context.draft.decisions[0],{epoch_uuid:'old',selected:false,reviewed:true,excluded:true});
  assert.equal(calls.length,2);assert.ok(renderer.root.findAllByType('button').some(node=>label(node)==='Add these additions to main'));
  await act(async()=>renderer.unmount());
 }finally{globalThis.fetch=oldFetch;await server.close();}
});

test('batched draft saves keep browser reads on the paused committed scope until the final receipt',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer,release,operation,patches=0;
 let context={candidate_scope_revision:'scope-0',draft:{draft_version:0,selection_mode:'selected',decisions:[],decisions_total:0,decisions_truncated:false},counts:{pending_epochs:501,pending_cells:1},protocol:{definition:{protocol_uuid:'history'}}};
 globalThis.fetch=async(path,options={})=>{
  if(options.method==='PATCH'){
   const body=JSON.parse(options.body);assert.equal(body.expected_version,patches);assert.equal(body.expected_candidate_scope_revision,`scope-${patches}`);
   patches++;if(patches===2)await new Promise(resolve=>{release=resolve;});
   context={...context,candidate_scope_revision:`scope-${patches}`,draft:{...context.draft,draft_version:patches,decisions:[...context.draft.decisions,...body.decisions]}};
   context.draft.decisions_total=context.draft.decisions.length;
  }
  return {ok:true,status:200,json:async()=>context};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'history',item:{candidate_revision_uuid:'candidate'},capabilities:{drafts:true,frozen_browse:true}}));});
  const inspector=()=>renderer.root.find(node=>node.type?.name==='Inspector');const mounted=inspector();
  await act(async()=>{operation=inspector().props.onReviewDecision({epoch_uuids:Array.from({length:501},(_,i)=>`epoch-${i}`),changes:{reviewed:true}});});
  assert.equal(patches,2);assert.equal(inspector(),mounted);assert.equal(inspector().props.readPaused,true);assert.equal(inspector().props.readContext.candidate_scope_revision,'scope-0','intermediate batch scopes must not start descendant reads');
  await act(async()=>{release();await operation;});assert.equal(patches,3);assert.equal(inspector().props.readPaused,false);assert.equal(inspector().props.readContext.candidate_scope_revision,'scope-3');assert.equal(context.draft.decisions.length,501);
  await act(async()=>renderer.unmount());
 }finally{globalThis.fetch=oldFetch;await server.close();}
});

test('actual Workbench renders authoritative queue and session worklist controls',async()=>{
 const server=await create();
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
  const item={protocol_uuid:'history',protocol_name:'VariableHistoryNoiseCurInject',candidate_revision_uuid:'candidate-immutable',baseline_revision_uuid:'base-immutable',status:'pending',created_at:'2026-10-02T01:00:00Z',source_filename:'incoming.h5',diff_counts:{added:12,removed:0,changed:2},next_count:50};
  const props={protocolId:'history',suggestions:[item,{...item,protocol_uuid:'other',protocol_name:'Other'}],projectId:'project',authority:null};
  const html=renderToStaticMarkup(React.createElement(Workbench,props));
  for(const text of ['Incoming proposals','candidate-immutable','base-immutable','incoming.h5','Earlier unmerged updates'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/>Other</);assert.match(html,/disabled=""[^>]*>Merge &amp; export/);
  const cumulative={contract_version:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},queue_revision:'union',pending_cell_count:2,pending_epoch_count:30,candidates:[{...item,pending_epoch_count:20},{...item,candidate_revision_uuid:'second-proposal',pending_epoch_count:20}]};
  const cumulativeHtml=renderToStaticMarkup(React.createElement(Workbench,{...props,authority:cumulative}));
  assert.match(cumulativeHtml,/2<\/strong>.*cells/);assert.match(cumulativeHtml,/30<\/strong>.*epochs/);assert.match(cumulativeHtml,/second-proposal/);assert.doesNotMatch(cumulativeHtml,/Earlier unmerged updates/);
  const blockedHtml=renderToStaticMarkup(React.createElement(Workbench,{...props,authority:{...cumulative,pending_cell_count:0,pending_epoch_count:0,candidates:[{...item,status:'conflict',pending_epoch_count:0},{...item,candidate_revision_uuid:'blocked-source',status:'source_blocked',pending_epoch_count:0}]}}));
  assert.match(blockedHtml,/Conflict requires review/);assert.match(blockedHtml,/Source unavailable/);assert.match(blockedHtml,/blocked-source/);assert.doesNotMatch(blockedHtml,/No current incoming proposals/);
  const unknownHtml=renderToStaticMarkup(React.createElement(Workbench,{...props,authority:{...cumulative,pending_cell_count:null}}));assert.match(unknownHtml,/Cells unavailable/);assert.doesNotMatch(unknownHtml,/0 distinct cells/);
  let renderer,saved;
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,{...props,onSession:value=>{saved=value;}}));});
  await act(async()=>renderer.root.findByType('input').props.onChange());
  assert.deepEqual(saved.selected,['history:candidate-immutable']);
  assert.ok(renderer.root.findAllByType('button').some(button=>label(button)==='Review selected'));
  assert.equal(saved.active,null);
  await act(async()=>renderer.unmount());
  const restored=renderToStaticMarkup(React.createElement(Workbench,{...props,session:saved}));
  assert.match(restored,/1 selected proposals/);
  const dir=fileURLToPath(new URL('../../review-evidence',import.meta.url));
  await mkdir(dir,{recursive:true});await writeFile(`${dir}/workbench-component.html`,html);
 }finally{await server.close();}
});
test('App and affected dialog/browser/sidebar JSX transform from isolated source',async()=>{
 const server=await create();
 try{
  for(const file of ['App.jsx','components/MetadataExplorer.jsx','components/IncomingExportDialog.jsx','components/ExportSelectionDialog.jsx','components/ProtocolSidebar.jsx','incoming-workbench/ui/FrozenIncomingReview.jsx','components/WorkbenchExportDialog.jsx']){
   const result=await server.transformRequest(`/src/${file}`);assert.ok(result?.code.length>0,file);
  }
 }finally{await server.close();}
});

test('mounted additive review preserves an uncertain acceptance operation and recovers its receipt without rebinding',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;
 const calls=[];let renderer,saved,accepts=0,changed=0;
 const root='/protocols/history/workbench/candidates/proposal';
 const priorPreview={preview_sha256:'sealed-preview',expected_binding_version:2,expected_query_revision:'main-query',selected_epoch_count:7,accepted_epoch_count:7,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:47,accepted_cell_count:2,mode:'all',expected_candidate_scope_revision:'exact-frozen-scope',expected_draft_version:4};
 const context={candidate_scope_revision:'exact-frozen-scope',draft:{draft_version:4,selection_mode:'all'},protocol:null};
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):undefined;
  calls.push({path:endpoint,method:options.method||'GET',body});
  let value=context,status=200;
  if(endpoint===`${root}/preview`)value={preview_sha256:'sealed-preview',expected_binding_version:2,expected_query_revision:'main-query',selected_epoch_count:7,accepted_epoch_count:7,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:47,accepted_cell_count:2};
  else if(endpoint===`${root}/accept`){if(accepts++===0){status=503;value={error:'Reply lost after possible commit'};}else value={binding:{revision_uuid:'main-plus-additions',version:3},event_uuid:'one-event',operation_uuid:body.operation_uuid};}
  else assert.equal(endpoint,`${root}/context`,'frozen review makes no global browse or replacement request');
  return {ok:status===200,status,json:async()=>value};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},protocolId:'history',item:{candidate_revision_uuid:'proposal'},session:{preview:priorPreview,operation:'historical-operation'},onSession:value=>{saved=value;},onChange:()=>changed++}));});
  assert.ok(renderer.root.findAllByType('p').some(node=>label(node).includes('No global query is substituted')));
  const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  assert.ok(renderer.root.findAllByType('dt').some(node=>label(node)==='Existing main epochs retained'));
  await act(async()=>button('Add these additions to main').props.onClick());
  assert.equal(saved.unconfirmed,true);assert.ok(saved.operation);assert.equal(saved.preview.mode,'all');
  assert.equal(button('Merge all'),undefined);assert.equal(button('Cancel merge preview'),undefined);
  const operation=saved.operation;
  await act(async()=>renderer.unmount());
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},protocolId:'history',item:{candidate_revision_uuid:'proposal'},session:saved,onSession:value=>{saved=value;},onChange:()=>changed++}));});
  await act(async()=>button('Recover acceptance receipt').props.onClick());
  assert.equal(saved.receipt.binding.revision_uuid,'main-plus-additions');assert.equal(saved.unconfirmed,false);assert.equal(changed,1);
  const acceptanceCalls=calls.filter(call=>call.path.endsWith('/accept'));
  assert.equal(acceptanceCalls.length,2);assert.deepEqual(acceptanceCalls[0].body,acceptanceCalls[1].body);assert.equal(acceptanceCalls[1].body.operation_uuid,operation);
  assert.equal(calls.filter(call=>call.path.endsWith('/preview')).length,0);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('known cumulative authority survives a pending or failed refresh without switching to a live query',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;
 const queue={contract_version:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:false},queue_revision:'exact-union',pending_cell_count:2,pending_epoch_count:20,candidates:[]};
 let requests=0,release,renderer,state;
 globalThis.fetch=async()=>{if(requests++===0)return {ok:true,status:200,json:async()=>queue};await new Promise(resolve=>{release=resolve;});return {ok:false,status:503,json:async()=>({error:'unavailable'})};};
 try{
  const {default:useQueue}=await server.ssrLoadModule('/src/incoming-workbench/useWorkbenchQueue.js');
  function Probe(){state=useQueue('protocol',0);return React.createElement('span',null,state.data?.queue_revision||'unknown');}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  assert.equal(state.data.queue_revision,'exact-union');
  await act(async()=>state.reload());
  assert.equal(state.loading,true);assert.equal(state.data.queue_revision,'exact-union');
  await act(async()=>release());
  assert.equal(state.loading,false);assert.equal(state.data.queue_revision,'exact-union');assert.match(state.error,/unavailable/);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('accept then export failure preserves acceptance receipt and retries identical export across remount',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[];
 let renderer,saved={},exports=0,changed=0,acceptAttempts=0;
 const root='/protocols/history/workbench/candidates/proposal';let receiptRoot;
 const counts={selected_epoch_count:2,accepted_epoch_count:2,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:42,accepted_cell_count:1};
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):undefined;
  calls.push({path:endpoint,method:options.method||'GET',body});let status=200,value;
  if(endpoint===`${root}/context`)value={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'selected'}};
  else if(endpoint===`${root}/preview`)value={...counts,preview_sha256:'preview',expected_binding_version:1,expected_query_revision:'main'};
  else if(endpoint===`${root}/accept`){if(acceptAttempts++===0){status=503;value={error:'Acceptance reply lost'};}else{receiptRoot=`/protocols/history/workbench/receipts/${body.operation_uuid}`;value={operation_uuid:body.operation_uuid,binding:{revision_uuid:'new-main',version:2},event_uuid:'accept-audit'};}}
  else if(endpoint===`${receiptRoot}/export-context`){assert.equal(saved.receipt.event_uuid,'accept-audit','acceptance published before export evidence read');value={export_scope_revision:'exact-new-set',accepted_epoch_count:2,accept_operation_uuid:saved.receipt.operation_uuid};}
  else if(endpoint===`${receiptRoot}/exports`){if(exports++===0){status=503;value={error:'Export reply lost'};}else value={dataset_uuid:'one-dataset',event_uuid:'export-event',artifact_sha256:'artifact-hash',epoch_count:2,download_url:'/download',format:body.format,operation_uuid:body.operation_uuid,export_scope:{kind:'workbench_incoming'}};}
  else assert.fail(`Unexpected endpoint ${endpoint}`);
  return {ok:status===200,status,json:async()=>value};
 };
 try{
  const {default:Dialog}=await server.ssrLoadModule('/src/components/WorkbenchExportDialog.jsx');
  function Probe(){const [state,setState]=React.useState(saved);return React.createElement(Dialog,{protocolId:'history',item:{candidate_revision_uuid:'proposal'},accept:true,state,onState:value=>{saved=value;setState(value);},onChanged:()=>changed++});}
  const mount=async()=>{await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});};
  await mount();await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.phase,'previewed');assert.equal(calls.filter(call=>call.path.endsWith('/accept')).length,0,'counts shown before acceptance');
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.phase,'acceptance-unconfirmed');assert.ok(saved.acceptOperation);assert.equal(changed,0);
  await act(async()=>renderer.unmount());await mount();
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.phase,'export-failed');assert.equal(saved.receipt.binding.version,2);assert.equal(changed,1);assert.ok(saved.prepared);
  const firstExport=calls.find(call=>call.path.endsWith('/exports'));
  await act(async()=>renderer.unmount());await mount();
  assert.equal(renderer.root.findAllByType('input').find(node=>node.props.maxLength===120).props.disabled,true,'saved export body cannot change');
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.exported.dataset_uuid,'one-dataset');const acceptCalls=calls.filter(call=>call.path.endsWith('/accept'));assert.equal(acceptCalls.length,2);assert.deepEqual(acceptCalls[0],acceptCalls[1]);assert.equal(calls.filter(call=>call.path.endsWith('/preview')).length,1);
  assert.deepEqual(calls.filter(call=>call.path.endsWith('/exports')),[firstExport,firstExport]);
  assert.equal(renderer.root.findByType('a').props.href,'/download');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('completed independent export can proceed to review and fresh accept/export while preserving download',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer,saved;
 let context={candidate_scope_revision:'new-scope',protocol:{definition:{protocol_uuid:'history'}},draft:{draft_version:5,selection_mode:'selected',decisions:[{epoch_uuid:'a',selected:false,reviewed:true,excluded:false}],decisions_total:1,decisions_truncated:false}};
 globalThis.fetch=async(path,options={})=>{if(options.method==='PATCH')context={...context,draft:{...context.draft,draft_version:6}};return {ok:true,status:200,json:async()=>String(path).endsWith('/preview')?{preview_sha256:'fresh',expected_binding_version:2,expected_query_revision:'query',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:40,next_epoch_count:41,accepted_cell_count:1}:context};};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const completed={workflow:'export',prepared:{path:'/old',body:{}},exported:{dataset_uuid:'old-dataset',download_url:'/old-download',epoch_count:2},exportOperation:'old-export'};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{protocolId:'history',item:{candidate_revision_uuid:'proposal'},capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true},session:{selected:['a'],exportState:completed},onSession:value=>{saved=value;}}));});
  const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  assert.equal(button('Merge all'),undefined);
  await act(async()=>button('Merge & export').props.onClick());
  assert.equal(saved.exportState.prepared,undefined);assert.equal(saved.exportState.completed[0].exported.dataset_uuid,'old-dataset');
  assert.equal(renderer.root.findByType('form').props.children.at(-1).props.children,'Accept & export');
  assert.equal(renderer.root.findByType('a').props.href,'/old-download');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('definitively rejected acceptance refreshes on reopen and permits a fresh attempt',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,saved={phase:'rejected',preview:null,acceptOperation:null,error:'Old source scope'};
 globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({candidate_scope_revision:'fresh',draft:{draft_version:6,selection_mode:'selected'}})});
 try{
  const {default:Dialog}=await server.ssrLoadModule('/src/components/WorkbenchExportDialog.jsx');
  function Probe(){const [state,setState]=React.useState(saved);return React.createElement(Dialog,{protocolId:'history',item:{candidate_revision_uuid:'proposal'},accept:true,state,onState:value=>{saved=value;setState(value);}});}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  assert.equal(saved.phase,null);assert.match(saved.error,/Fresh proposal loaded/);
  assert.equal(renderer.root.findAllByType('button').find(node=>label(node)==='Preview additions').props.disabled,false);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('unsupported direct export format releases rejected request so fresh format can be chosen',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,saved={};
 const root='/protocols/history/workbench/candidates/proposal';
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):null;
  let status=200,value={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'selected'}};
  if(endpoint===`${root}/preview`)value={selected_epoch_count:2,accepted_epoch_count:2,already_present_epoch_count:0,retained_epoch_count:3,next_epoch_count:5,accepted_cell_count:1,preview_sha256:'preview',expected_binding_version:1,expected_query_revision:'main'};
  if(endpoint===`${root}/exports`){assert.equal(body.format,'matlab-mat');status=400;value={error:'MATLAB cannot preserve annotation grouping'};}
  return {ok:status===200,status,json:async()=>value};
 };
 try{
  const {default:Dialog}=await server.ssrLoadModule('/src/components/WorkbenchExportDialog.jsx');
  function Probe(){const [state,setState]=React.useState(saved);return React.createElement(Dialog,{protocolId:'history',item:{candidate_revision_uuid:'proposal'},state,onState:value=>{saved=value;setState(value);}});}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  await act(async()=>renderer.root.findAllByType('input').find(node=>node.props.value==='matlab-mat').props.onChange());
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.phase,'previewed');
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(saved.phase,null);assert.match(saved.error,/MATLAB cannot preserve/);assert.equal(saved.prepared,null);assert.equal(saved.exportOperation,null);
  await act(async()=>renderer.unmount());await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  assert.equal(saved.phase,null);assert.equal(renderer.root.findAllByType('fieldset').at(-1).props.disabled,false);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('shared change callback and external revision refresh frozen token while preserving uncertain operation',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,saved,contextReads=0;
 const root='/protocols/history/workbench/candidates/proposal',calls=[];
 globalThis.fetch=async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');calls.push(endpoint);assert.equal(endpoint,`${root}/context`,'no global query fallback');
  return {ok:true,status:200,json:async()=>({candidate_scope_revision:`scope-v${++contextReads}`,draft:{draft_version:3,selection_mode:'all'},protocol:null})};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const preview={mode:'all',expected_candidate_scope_revision:'original-operation-scope',expected_draft_version:1,preview_sha256:'sealed',expected_binding_version:2,expected_query_revision:'main',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:2,next_epoch_count:3,accepted_cell_count:1};
  function Probe({external=0}){const [revision,setRevision]=React.useState(0);return React.createElement(Review,{protocolId:'history',item:{candidate_revision_uuid:'proposal'},revision:revision+external,capabilities:{frozen_browse:true,drafts:true,additive_accept:true},session:{unconfirmed:true,preview,operation:'same-operation'},onChange:()=>setRevision(value=>value+1),onSession:value=>{saved=value;}});}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  await act(async()=>renderer.root.findByType(Review).props.onChange({kind:'annotations'}));
  assert.equal(contextReads,2);assert.ok(renderer.root.findAllByType('code').some(node=>label(node).includes('scope-v2')));
  await act(async()=>renderer.update(React.createElement(Probe,{external:5})));
  assert.equal(contextReads,3);assert.equal(saved.operation,'same-operation');assert.deepEqual(saved.preview,preview);assert.equal(saved.unconfirmed,true);assert.equal(calls.length,3);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('default cumulative Workbench prepares once per queue fence, refreshes after partial acceptance, and keeps proposal history separate',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,preparedCalls=0,saved;
 const protocol='history',root='/protocols/history/workbench';
 const makeQueue=(token,count)=>({contract_version:1,queue_revision:token,pending_epoch_count:count,pending_cell_count:1,candidates:[{protocol_uuid:protocol,candidate_revision_uuid:'original-a',status:'pending',pending_epoch_count:count},{protocol_uuid:protocol,candidate_revision_uuid:'original-b',status:'pending',pending_epoch_count:count}],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}});
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):null;let value;
  if(endpoint===`${root}/prepare`){preparedCalls++;const id=`union-${body.expected_queue_revision}`;value={contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:`prepare-${body.expected_queue_revision}`,candidate_revision_uuid:id,root:`${root}/candidates/${id}`,candidate_scope_revision:'frozen',queue_revision:body.expected_queue_revision,context:{candidate_revision_uuid:id,candidate_scope_revision:'frozen',draft:{draft_version:1,selection_mode:'selected'},protocol:{protocol_uuid:protocol}}};}
  else if(endpoint.endsWith('/context'))value={candidate_scope_revision:'fresh',draft:{draft_version:1,selection_mode:'selected'},protocol:null,counts:{pending_epochs:endpoint.includes('queue-1')?3:1}};
  else assert.fail(`No global fallback or invented client union: ${endpoint}`);
  return {ok:true,status:200,json:async()=>value};
 };
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
  const props={protocolId:protocol,authority:makeQueue('queue-1',3),onSession:value=>{saved=value;}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,props));});
  assert.equal(preparedCalls,1);assert.ok(renderer.root.findAllByType('span').some(node=>String(node.props.className||'').includes('incoming-bar-scope')));
  await act(async()=>renderer.update(React.createElement(Workbench,{...props,authority:{...props.authority}})));
  assert.equal(preparedCalls,1,'ordinary rerender/poll result does not prepare again');
  await act(async()=>renderer.update(React.createElement(Workbench,{...props,revision:1,authority:makeQueue('queue-2',1)})));
  assert.equal(preparedCalls,2);assert.equal(saved.cumulative.prepared.candidate_revision_uuid,'union-queue-2');
  assert.ok(renderer.root.findAll(node=>node.props['aria-label']==='Distinct pending incoming counts').some(node=>label(node).includes('1epochs')));
  const historyButton=renderer.root.findAllByType('button').find(node=>label(node)==='Proposal history');
  await act(async()=>historyButton.props.onClick());
  assert.ok(renderer.root.findAllByType('code').some(node=>label(node)==='original-a'));assert.equal(preparedCalls,2);
  await act(async()=>renderer.root.findAllByType('button').find(node=>label(node)==='Return to cumulative incoming review').props.onClick());
  assert.equal(preparedCalls,2,'resuming same prepared snapshot does not write again');
  await act(async()=>renderer.update(React.createElement(Workbench,{...props,authority:makeQueue('all-excluded',0)})));
  assert.equal(preparedCalls,3,'history permits restoring excluded draft even when awaiting-review count is zero');
  assert.ok(renderer.root.findAllByType('span').some(node=>String(node.props.className||'').includes('incoming-bar-scope')));
  assert.ok(renderer.root.findAllByType('p').some(node=>label(node).includes('Saved exclusions remain in your draft')));
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('queue changes preserve in-flight acceptance and older confirmed receipt keeps exact export action',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let renderer,saved,release,attempts=0,prepares=0;
 const root='/protocols/history/workbench/candidates/old-union';
 const context={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'all'},counts:{pending_epochs:2},protocol:null};
 const preview={expected_candidate_scope_revision:'scope',expected_draft_version:1,mode:'all',preview_sha256:'preview',expected_binding_version:1,expected_query_revision:'main',selected_epoch_count:2,accepted_epoch_count:2,already_present_epoch_count:0,retained_epoch_count:1,next_epoch_count:3,accepted_cell_count:1};
 const prepared={contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-old',candidate_revision_uuid:'old-union',root,candidate_scope_revision:'scope',context:{...context,candidate_revision_uuid:'old-union',protocol:{protocol_uuid:'history'}},queue_revision:'old-queue'};
 const makeQueue=token=>({data:{queue_revision:token,pending_epoch_count:2,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}},loading:false});
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body?JSON.parse(options.body):null;let value,status=200;
  if(endpoint.endsWith('/context'))value=context;
  else if(endpoint===`${root}/accept`){if(attempts++===0){await new Promise(resolve=>{release=resolve;});status=503;value={error:'Reply lost'};}else value={operation_uuid:body.operation_uuid,candidate_revision_uuid:'old-union',event_uuid:'accepted-old',binding:{revision_uuid:'new-main',version:2}};}
  else if(endpoint.endsWith('/prepare')){prepares++;value={...prepared,candidate_revision_uuid:'new-union',root:root.replace('old-union','new-union'),context:{...prepared.context,candidate_revision_uuid:'new-union'},queue_revision:body.expected_queue_revision};}
  else assert.fail(`Unexpected ${endpoint}`);
  return {ok:status===200,status,json:async()=>value};
 };
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
  const props={protocolId:'history',queue:makeQueue('old-queue'),session:{prepared,drafts:{'old-union':{preview,operation:'same-operation'}}},onSession:value=>{saved=value;}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,props));});
  let accepting;
  await act(async()=>{accepting=renderer.root.findAllByType('button').find(node=>label(node)==='Add these additions to main').props.onClick();});
  assert.equal(saved.drafts['old-union'].acceptPending,true);
  await act(async()=>renderer.update(React.createElement(Review,{...props,queue:makeQueue('new-queue')})));
  assert.equal(prepares,0,'scope cannot switch during pending acceptance');
  await act(async()=>{release();await accepting;});assert.equal(saved.drafts['old-union'].unconfirmed,true);assert.equal(prepares,0);
  await act(async()=>renderer.root.findAllByType('button').find(node=>label(node)==='Recover acceptance receipt').props.onClick());
  assert.equal(prepares,1);assert.equal(saved.prepared.candidate_revision_uuid,'new-union');
  const exportButton=renderer.root.findAllByType('button').find(node=>label(node)==='Export accepted additions');assert.ok(exportButton,'old accepted subset remains exportable');
  await act(async()=>exportButton.props.onClick());
  assert.ok(renderer.root.findAllByType('p').some(node=>label(node).includes('accepted-old')));assert.equal(attempts,2,'opening old receipt export does not accept again');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('prepared cumulative scope refuses mismatched candidate, protocol, root or queue identity',async()=>{
 const server=await create();
 try{
  const {requirePreparedWorkbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
  const protocol='7d76b76a-4c43-42c6-ac54-881ff2fc108a',candidate='b411db17-0ab4-42aa-872a-e6e614106041';
  const value={contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-operation',candidate_revision_uuid:candidate,root:`/protocols/${protocol}/workbench/candidates/${candidate}`,queue_revision:'queue',candidate_scope_revision:'scope',context:{candidate_revision_uuid:candidate,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:'scope',draft:{draft_version:1}}};
  assert.equal(requirePreparedWorkbench(protocol,value,'queue').candidate_revision_uuid,candidate);
  assert.throws(()=>requirePreparedWorkbench(protocol,{...value,context:{...value.context,candidate_revision_uuid:protocol}},'queue'),/another candidate/);
  assert.throws(()=>requirePreparedWorkbench(protocol,{...value,context:{...value.context,protocol:{definition:{protocol_uuid:candidate}}}},'queue'),/another candidate/);
  assert.throws(()=>requirePreparedWorkbench(protocol,{...value,root:'/explore'},'queue'),/frozen destination/);
  assert.throws(()=>requirePreparedWorkbench(protocol,{...value,queue_revision:'other'},'queue'),/scope changed/);
 }finally{await server.close();}
});

test('new queue preparation preserves the mounted Inspector and fences an open export dialog until replacement is ready',async()=>{

 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer,release,prepares=0,contexts=0;
 const protocol='history',root='/protocols/history/workbench';
 let draftVersion=1;
 const context=id=>({candidate_revision_uuid:id,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:`scope-${id}`,draft:{draft_version:id==='old-union'?draftVersion:1,selection_mode:'selected',decisions:[{epoch_uuid:'epoch',selected:true,reviewed:true,excluded:false}],decisions_total:1,decisions_truncated:false},counts:{pending_epochs:2}});
 const prepared=(id,token)=>({contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:`prepare-${token}`,candidate_revision_uuid:id,root:`${root}/candidates/${id}`,candidate_scope_revision:`scope-${id}`,queue_revision:token,context:context(id)});
 const queue=token=>({data:{queue_revision:token,pending_epoch_count:2,total_candidate_count:2,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}},loading:false});
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');let value;
  if(endpoint===`${root}/prepare`){prepares++;await new Promise(resolve=>{release=resolve;});value=prepared('new-union','new-queue');}
  else if(endpoint.endsWith('/draft')){const body=JSON.parse(options.body);assert.deepEqual(body.decisions,[{epoch_uuid:'epoch',selected:true}]);draftVersion++;value=context('old-union');}
  else if(endpoint.endsWith('/preview'))value={preview_sha256:'sealed',expected_binding_version:1,expected_query_revision:'query',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:10,next_epoch_count:11,accepted_cell_count:1};
  else if(endpoint.endsWith('/context')){contexts++;value=context(endpoint.includes('old-union')?'old-union':'new-union');}
  else assert.fail(`Preparation must fence old-scope writes: ${endpoint}`);
  return {ok:true,status:200,json:async()=>value};
 };
 try{
  const {default:Cumulative}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
  const {default:Frozen}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const props={protocolId:protocol,queue:queue('old-queue'),session:{prepared:prepared('old-union','old-queue'),drafts:{'old-union':{selected:['epoch'],filters:{date:'2026-10-01'}}}}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Cumulative,props));});
  const original=renderer.root.findByType(Frozen);
  const inspector=renderer.root.findAll(node=>node.type?.name==='Inspector')[0];assert.ok(inspector);
  await act(async()=>renderer.root.findAllByType('button').find(node=>label(node)==='Export').props.onClick());
  const openDialog=renderer.root.findByType('dialog');
  assert.equal(contexts,1,'the selected preview requires no duplicate context load');
  await act(async()=>renderer.update(React.createElement(Cumulative,{...props,revision:1,queue:queue('new-queue')})));
  assert.equal(renderer.root.findAll(node=>node.type?.name==='Inspector')[0],inspector,'revision refresh cannot unmount the visible frozen tree during prepare');
  assert.equal(inspector.props.readContext.candidate_scope_revision,'scope-old-union');assert.equal(inspector.props.revision,'undefined:2');
  assert.equal(renderer.root.findByType('dialog'),openDialog);
  assert.equal(openDialog.findAllByType('button').find(node=>node.props.className==='primary').props.disabled,true);
  await act(async()=>openDialog.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.equal(renderer.root.findByType(Frozen),original,'old browser is preserved while preparing');
  assert.equal(contexts,2,'revision refresh obtains fresh context without remounting the visible frozen tree');
  assert.equal(original.props.externalBusy,true);
  const compare=inspector.props.draftSelection;
  assert.equal(compare.disabled,true);
  await act(async()=>compare.onMerge(['epoch']));assert.equal(prepares,1);
  await act(async()=>release());
  const replacement=renderer.root.findByType(Frozen);
  assert.notEqual(replacement,original);assert.equal(replacement.props.item.candidate_revision_uuid,'new-union');
  assert.equal(replacement.props.externalBusy,false);assert.equal(contexts,3);
  await act(async()=>renderer.update(React.createElement(Cumulative,{...props,queue:queue('new-queue')})));
  assert.equal(renderer.root.findByType(Frozen),replacement);assert.equal(prepares,1,'stable paired queue echo does not prepare again');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});


test('actual queue hook retains Inspector through old-token loading, delayed queue and delayed preparation',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer,releaseQueue,releasePrepare,reads=0,prepares=0;
 const protocol='history',root='/protocols/history/workbench';
 const queue=token=>({contract_version:1,queue_revision:token,pending_epoch_count:2,pending_cell_count:1,total_candidate_count:1,candidates:[{protocol_uuid:protocol,candidate_revision_uuid:'original',status:'pending',pending_epoch_count:2}],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}});
 const context=id=>({candidate_revision_uuid:id,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:`scope-${id}`,draft:{draft_version:1,selection_mode:'selected'},counts:{pending_epochs:2}});
 const prepared=(id,token)=>({contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:`prepare-${token}`,candidate_revision_uuid:id,root:`${root}/candidates/${id}`,candidate_scope_revision:`scope-${id}`,queue_revision:token,context:context(id)});
 globalThis.fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');let value;
  if(endpoint===`${root}?limit=20`){if(reads++===0)value=queue('old-queue');else{await new Promise(resolve=>{releaseQueue=resolve;});value=queue('new-queue');}}
  else if(endpoint===`${root}/prepare`){if(prepares++===0)value=prepared('old-union','old-queue');else{await new Promise(resolve=>{releasePrepare=resolve;});value=prepared('new-union','new-queue');}}
  else if(endpoint.endsWith('/context'))value=context(endpoint.includes('old-union')?'old-union':'new-union');
  else assert.fail(`Old-scope actions must stay fenced during queue refresh: ${endpoint}`);
  return {ok:true,status:200,json:async()=>value};
 };
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
  const props={protocolId:protocol,revision:0};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,props));});
  const inspector=renderer.root.findAll(node=>node.type?.name==='Inspector')[0];assert.ok(inspector);assert.equal(prepares,1);
  await act(async()=>renderer.update(React.createElement(Workbench,{...props,revision:1})));
  assert.equal(reads,2);assert.equal(prepares,1,'old token is retained while queue GET is pending');
  assert.equal(renderer.root.findAll(node=>node.type?.name==='Inspector')[0],inspector);
  assert.equal(inspector.props.readContext.candidate_scope_revision,'scope-old-union');assert.equal(inspector.props.revision,'0:1');
  let compare=inspector.props.draftSelection;assert.equal(compare.disabled,true);
  await act(async()=>compare.onMerge(['epoch']));
  await act(async()=>releaseQueue());
  assert.equal(prepares,2);assert.equal(renderer.root.findAll(node=>node.type?.name==='Inspector')[0],inspector);
  compare=inspector.props.draftSelection;assert.equal(compare.disabled,true);
  await act(async()=>releasePrepare());
  const replacement=renderer.root.findAll(node=>node.type?.name==='Inspector')[0];assert.notEqual(replacement,inspector);
  assert.equal(replacement.props.readContext.candidate_scope_revision,'scope-new-union');assert.equal(replacement.props.revision,'1:1');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('candidate cohort identity survives draft saves while authority tokens refresh and membership changes reset it',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer;
 const root='/protocols/history/workbench/candidates/proposal',bodies=[];
 let context={candidate_revision_uuid:'proposal',candidate_recipe_sha256:'a'.repeat(64),expected_binding_version:3,candidate_scope_revision:'scope-one',protocol:{definition:{protocol_uuid:'history'}},draft:{draft_version:1,selection_mode:'selected'},counts:{pending_epochs:1}};
 globalThis.fetch=async(path,options={})=>{
  if(options.method==='PATCH'){assert.equal(path,`/api${root}/draft`);bodies.push(JSON.parse(options.body));context={...context,candidate_scope_revision:'scope-two',draft:{...context.draft,draft_version:2}};}
  else assert.equal(path,`/api${root}/context`);
  return {ok:true,status:200,json:async()=>context};
 };
 try{
  const {default:Frozen}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const props={protocolId:'history',item:{candidate_revision_uuid:'proposal'},revision:0,preserveBrowser:true,capabilities:{frozen_browse:true,drafts:true,additive_accept:true}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Frozen,props));});
  const inspector=()=>renderer.root.findAll(node=>node.type?.name==='Inspector')[0];
  const original=inspector().props.readContext.cohort_key;assert.equal(original,JSON.stringify([root,'a'.repeat(64),3]));
  await act(async()=>inspector().props.onReviewDecision({epoch_uuids:['epoch'],changes:{reviewed:true}}));
  assert.equal(inspector().props.readContext.cohort_key,original);assert.equal(inspector().props.readContext.candidate_scope_revision,'scope-two');
  assert.equal(bodies[0].expected_candidate_scope_revision,'scope-one');assert.equal(bodies[0].expected_version,1);assert.equal(bodies[0].cohort_key,undefined,'intent identity never becomes mutation authority');
  context={...context,expected_binding_version:4,candidate_scope_revision:'scope-three'};
  await act(async()=>renderer.update(React.createElement(Frozen,{...props,revision:1})));
  assert.notEqual(inspector().props.readContext.cohort_key,original);
  context={...context,candidate_recipe_sha256:undefined,candidate_scope_revision:'scope-four'};
  await act(async()=>renderer.update(React.createElement(Frozen,{...props,revision:2})));
  assert.equal(inspector().props.readContext.cohort_key,undefined,'missing immutable evidence must not manufacture a stable cohort');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('compact action bar keeps authoritative positive, zero and unavailable counts and Cancel only leaves review',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch,calls=[];let renderer,left=0;
 const context={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'selected',decisions:[],decisions_truncated:false},counts:{pending_epochs:0,pending_cells:0},protocol:null};
 globalThis.fetch=async(path,options={})=>{calls.push({path:String(path),method:options.method||'GET'});return {ok:true,status:200,json:async()=>context};};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const props={protocolId:'history',item:{candidate_revision_uuid:'proposal'},scopeKind:'cumulative_pending',capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true},onDefer:()=>left++};
  const mount=async counts=>{await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{...props,pendingCounts:counts}));});};
  const metrics=()=>renderer.root.findByProps({'aria-label':'Distinct pending incoming counts'}).findAll(node=>node.type==='strong'&&node.parent.type==='span'&&!node.parent.props.className).map(label);
  const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  await mount({pending_cell_count:2,pending_epoch_count:30});assert.deepEqual(metrics(),['+2','+30']);
  await act(async()=>renderer.update(React.createElement(Review,{...props,pendingCounts:{pending_cell_count:null,pending_epoch_count:30}})));assert.deepEqual(metrics(),['Unavailable','+30']);
  await act(async()=>renderer.update(React.createElement(Review,{...props,pendingCounts:{}})));assert.deepEqual(metrics(),['Unavailable','Unavailable']);
  await act(async()=>renderer.update(React.createElement(Review,{...props,pendingCounts:{pending_cell_count:0,pending_epoch_count:0}})));assert.deepEqual(metrics(),['0','0']);
  assert.equal(button('Merge all'),undefined);assert.equal(button('Export').props.disabled,true,'zero selected IDs disables export');
  const disclosure=renderer.root.findAllByType('details').find(node=>label(node).includes('Review details'));assert.equal(disclosure.props.open,undefined);
  assert.ok(label(disclosure).includes('Shared tags publish immediately'));
  await act(async()=>button('Cancel').props.onClick());assert.equal(left,1);assert.equal(calls.length,1);assert.equal(calls[0].method,'GET');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('incoming pill never calls reviewed or incomplete actor drafts unreviewed',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer;
 let context={candidate_scope_revision:'scope',draft:{draft_version:1,selection_mode:'selected',decisions:[],decisions_total:0,decisions_truncated:false},counts:{pending_epochs:2,pending_cells:1},protocol:null};
 globalThis.fetch=async()=>({ok:true,status:200,json:async()=>context});
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
  const props={protocolId:'history',item:{candidate_revision_uuid:'proposal'},pendingCounts:{pending_cell_count:1,pending_epoch_count:2}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{...props,revision:0}));});
  const pill=()=>renderer.root.findAllByType('span').find(node=>String(node.props.className||'').includes('incoming-bar-scope'));
  assert.equal(label(pill()),'Not reviewed');
  context={...context,draft:{...context.draft,decisions:[{epoch_uuid:'reviewed',reviewed:true}],decisions_total:1}};
  await act(async()=>renderer.update(React.createElement(Review,{...props,revision:1})));assert.equal(label(pill()),'Pending merge');
  context={...context,draft:{...context.draft,decisions:[],decisions_total:251,decisions_truncated:true}};
  await act(async()=>renderer.update(React.createElement(Review,{...props,revision:2})));assert.equal(label(pill()),'Pending merge');
  context={...context,draft:{...context.draft,decisions:[],decisions_total:0,decisions_truncated:false}};
  await act(async()=>renderer.update(React.createElement(Review,{...props,revision:3,externalBusy:true})));assert.equal(label(pill()),'Pending merge');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('selected-only export cannot retry against a changed saved draft after its preview is rejected',async()=>{
 const server=await create(),oldFetch=globalThis.fetch,calls=[];let renderer,saved={phase:'rejected',preview:null,error:'Scope changed'};
 globalThis.fetch=async(path,options={})=>{calls.push({path,method:options.method||'GET'});assert.equal(options.method,undefined,'fresh selection must return through the parent; no automatic draft preview');return {ok:true,status:200,json:async()=>({candidate_scope_revision:'changed',draft:{draft_version:99,selection_mode:'selected'}})};};
 try{
  const {default:Dialog}=await server.ssrLoadModule('/src/components/WorkbenchExportDialog.jsx');
  function Probe(){const [state,setState]=React.useState(saved);return React.createElement(Dialog,{selectedOnly:true,protocolId:'history',item:{candidate_revision_uuid:'proposal'},state,onState:value=>{saved=value;setState(value);}});}
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Probe));});
  assert.equal(renderer.root.findAllByType('button').find(n=>n.props.className==='primary').props.disabled,true);
  await act(async()=>renderer.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.match(saved.error,/choose Export again/);assert.equal(calls.length,1);assert.equal(calls[0].method,'GET');
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});

test('single-proposal refresh holds the same inert Inspector until fresh authority arrives',async()=>{
 const server=await create([frozenBrowserProbe]),oldFetch=globalThis.fetch;let renderer,release,reads=0;
 const context={candidate_scope_revision:'scope',candidate_recipe_sha256:'recipe',expected_binding_version:1,protocol:{definition:{protocol_uuid:'history'}},draft:{draft_version:1,selection_mode:'selected',decisions:[],decisions_total:0,decisions_truncated:false},counts:{pending_epochs:2}};
 globalThis.fetch=async(path,options={})=>{assert.equal(options.method,undefined);if(reads++>0)await new Promise(resolve=>{release=resolve;});return {ok:true,status:200,json:async()=>context};};
 try{
  const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');const props={protocolId:'history',item:{candidate_revision_uuid:'candidate'},capabilities:{drafts:true,frozen_browse:true,additive_accept:true}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Review,{...props,revision:0}));});const inspector=renderer.root.find(node=>node.type?.name==='Inspector');
  await act(async()=>renderer.update(React.createElement(Review,{...props,revision:1})));assert.equal(renderer.root.find(node=>node.type?.name==='Inspector'),inspector);assert.equal(inspector.props.readPaused,true);assert.equal(inspector.props.draftSelection.disabled,true);
  await act(async()=>inspector.props.draftSelection.onMerge(['epoch']));assert.equal(reads,2);
  await act(async()=>release());assert.equal(renderer.root.find(node=>node.type?.name==='Inspector'),inspector);assert.equal(inspector.props.readPaused,false);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
