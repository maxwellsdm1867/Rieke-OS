import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
import {createIncomingMergeIntents} from './incoming-workbench/incomingMergeIntent.js';
const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');
const root=fileURLToPath(new URL('..',import.meta.url));
const protocol='merge-protocol',project='merge-project',base=`/protocols/${protocol}/workbench`,candidate=base+'/candidates/union';
const suggestion={protocol_uuid:protocol,protocol_name:'SplitFieldCentering',candidate_revision_uuid:'original-proposal',status:'pending',source_filename:'Fixture.h5',created_at:'2026-10-02T10:00:00Z',diff_counts:{added:16,removed:0,changed:0},diff_summary:{current:{cells:9,epochs:36,acquisition_protocols:1,duration_seconds:90},proposed:{cells:11,epochs:52,acquisition_protocols:1,duration_seconds:130},delta:{cells:2,epochs:16,acquisition_protocols:0}}};
const response=(value,status=200)=>({ok:status===200,status,json:async()=>value});
const deferred=()=>{let resolve;return {promise:new Promise(value=>{resolve=value;}),resolve:()=>resolve()};};
async function harness({pending=3,failQueue=false,failPrepare=0,failPreview=false,failAccept=false,prepareGate=null,session=null,restore=null}={}){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost/'});
 const calls=[],receiptBodies=[],receipts=new Map();let generation=1,mode='selected',previews=0,accepts=0,lastNavigation,revision=0;
 const caps={cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true};
 let decisions=[{epoch_uuid:'excluded',selected:false,reviewed:false,excluded:true}];
 const chosen=Array.from({length:pending>1?pending-1:pending},(_,i)=>`epoch-${i}`);
 const context=()=>({candidate_revision_uuid:'union',candidate_recipe_sha256:'immutable-recipe',expected_binding_version:7,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:`scope-${generation}`,draft:{draft_version:generation,selection_mode:mode,decisions,decisions_total:decisions.length,decisions_truncated:false},counts:{pending_epochs:pending,pending_cells:2}});
 const queue=()=>({contract_version:1,queue_revision:'queue-one',pending_epoch_count:pending,pending_cell_count:2,total_candidate_count:1,candidates:[{candidate_revision_uuid:'original-proposal',protocol_uuid:protocol}],capabilities:caps});
 const fetch=async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,''),body=options.body&&JSON.parse(options.body);calls.push({endpoint,body,method:options.method||'GET'});
  if(endpoint.startsWith(base+'?'))return failQueue?response({error:'Queue unavailable'},503):response(queue());
  if(endpoint===base+'/prepare'){if(prepareGate)await prepareGate.promise;if(failPrepare-->0)return response({error:'An unmerged original proposal has stale authority or conflicting fingerprints; reconcile it before cumulative preparation'},409);return response({contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-one',candidate_revision_uuid:'union',root:candidate,candidate_scope_revision:context().candidate_scope_revision,queue_revision:body.expected_queue_revision,context:context()});}
  if(endpoint===candidate+'/context')return response(context());
  if(endpoint===candidate+'/draft'){assert.equal(body.expected_version,generation);assert.equal(body.expected_candidate_scope_revision,context().candidate_scope_revision);for(const next of body.decisions){const index=decisions.findIndex(value=>value.epoch_uuid===next.epoch_uuid),value={selected:false,reviewed:false,excluded:false,...decisions[index],...next};if(index<0)decisions.push(value);else decisions[index]=value;}assert.equal(decisions.find(v=>v.epoch_uuid==='excluded').excluded,true);mode=body.selection_mode||mode;generation++;return response(context());}
  if(endpoint===candidate+'/preview'){previews++;if(failPreview)return response({error:'Queue changed: preview again'},409);return response({preview_sha256:'exact-additions',expected_binding_version:7,expected_query_revision:'main-seven',selected_epoch_count:chosen.length,accepted_epoch_count:Math.max(0,pending-1),already_present_epoch_count:0,retained_epoch_count:36,next_epoch_count:36+Math.max(0,pending-1),accepted_cell_count:pending>1?2:0});}
  if(endpoint===candidate+'/accept'){
   receiptBodies.push(options.body);if(!receipts.has(body.operation_uuid)){accepts++;receipts.set(body.operation_uuid,{operation_uuid:body.operation_uuid,candidate_revision_uuid:'union',event_uuid:'acceptance-event',binding:{version:8,revision_uuid:'main-eight'}});}
   if(failAccept&&receiptBodies.length===1)return response({error:'Reply lost after commit'},503);return response(receipts.get(body.operation_uuid));
  }
  throw Error(`Unexpected/global request: ${endpoint}`);
 };
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch};
 const old=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const server=await createServer({root,configFile:false,plugins:[{name:'merge-browser-probes',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/FrozenIncomingReview.jsx')&&['../../epoch-browser/ui/Inspector.jsx','../../typed-query/ui/ProtocolViewFilter.jsx'].includes(id))return '\0merge-'+id;},load(id){if(id==='\0merge-../../epoch-browser/ui/Inspector.jsx')return "import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default props=>React.createElement('div',{'data-frozen-scope':props.readContext.candidate_scope_revision},React.createElement('button',{disabled:props.draftSelection.disabled,onClick:()=>props.onSelectionChange("+JSON.stringify(chosen)+")},'Select fixture epochs'),React.createElement('button',{disabled:props.draftSelection.disabled,onClick:()=>props.draftSelection.onMerge(props.draftSelection.selected)},'Merge selection'));";if(id==='\0merge-../../typed-query/ui/ProtocolViewFilter.jsx')return 'export default ()=>null;';}}],optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const {default:Suggestion}=await server.ssrLoadModule("/src/protocol-overview/ui/ProtocolSuggestion.jsx");
 const {default:Workbench}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingWorkbench.jsx');
 const {default:useNavigation}=await server.ssrLoadModule('/src/workspace-navigation/useWorkspaceNavigation.js');
 if(restore)window.history.replaceState({riekeWorkspace:{route:restore,index:0}},'');
 const container=document.getElementById('root'),mounted=createRoot(container);let saved=session;
 function Demo(){
  const navigation=useNavigation(),ledger=useRef(null);if(!ledger.current)ledger.current=createIncomingMergeIntents();lastNavigation=navigation;
  const route=navigation.route;
  function launch(id){const intent=ledger.current.issue(project,id);navigation.go('protocol',{protocol:id,workbench:{merge_intent:intent}});return true;}
  function claim(intent){const consumed=navigation.consumeMergeIntent(intent.request_uuid);return ledger.current.claim(intent,project,route.protocol)&&consumed;}
  return route.page!=='protocol'?React.createElement(Suggestion,{suggestion,onMerge:launch,onProtocol:id=>navigation.go('protocol',{protocol:id,workbench:{}})}):React.createElement(Workbench,{key:route.key,projectId:project,protocolId:route.protocol,revision,initialMergeIntent:route.workbench?.merge_intent,onClaimMergeIntent:claim,session:saved,onSession:value=>{saved=value;}});
 }
 const render=()=>act(async()=>mounted.render(React.createElement(React.StrictMode,null,React.createElement(Demo))));
 await render();
 return {container,calls,receiptBodies,get accepts(){return accepts;},get previews(){return previews;},get saved(){return saved;},get navigation(){return lastNavigation;},
  button(label){return [...container.querySelectorAll('button')].find(button=>button.textContent.trim()===label);},
  async click(label,twice=false){const button=this.button(label);assert.ok(button,`Missing ${label}: ${container.textContent}`);assert.equal(button.disabled,false,label);await act(async()=>{button.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));if(twice)button.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));});},
  async selectAndPreview(){const inspect=this.container.querySelector('[data-frozen-scope]');assert.ok(inspect);await this.click('Select fixture epochs');await this.click('Merge selection');await this.click('Mark selected reviewed & preview');},
  async rerender(){revision++;await render();},async restore(route){await act(async()=>lastNavigation.restore(route));},
  async close(){await act(async()=>mounted.unmount());await server.close();dom.window.close();for(const [key,value] of old)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
 };
}

test('expanded match visual has one comparison and right-side actions; Inspect only opens cumulative browsing',async()=>{
 const h=await harness();try{
  assert.equal(h.container.querySelectorAll('.protocol-diff').length,1);assert.equal(h.container.querySelectorAll('.protocol-diff-compact').length,0);
  assert.equal(h.container.querySelector('.protocol-match-actions').children[0].textContent.trim(),'Merge matched data');
  assert.doesNotMatch(h.container.textContent,/Approve|Details ·|Existing inspection decisions/);
  await h.click('Inspect in Workbench');assert.ok(h.container.querySelector('[data-frozen-scope]'));assert.equal(h.previews,0);assert.equal(h.accepts,0);
 }finally{await h.close();}
});
test('StrictMode double click prepares once and previews eligible additions once; confirmation uses exact fences',async()=>{
 const h=await harness();try{
  await h.click('Merge matched data',true);assert.equal(h.calls.filter(c=>c.endpoint===base+'/prepare').length,1);assert.equal(h.previews,0,'opening never previews all');await h.selectAndPreview();assert.equal(h.previews,1);assert.equal(h.accepts,0);
  const preview=h.container.querySelector('[aria-label="Additive acceptance preview"]');assert.ok(preview);assert.match(preview.textContent,/New epochs to add2/);assert.match(preview.textContent,/Existing main epochs retained36/);
  assert.equal(h.navigation.route.workbench.merge_intent,undefined);assert.equal(window.history.state.riekeWorkspace.route.workbench.merge_intent,undefined);
  await h.click('Add these additions to main',true);assert.equal(h.accepts,1);assert.equal(h.receiptBodies.length,1);
  const body=JSON.parse(h.receiptBodies[0]);assert.deepEqual({...body,operation_uuid:'operation'},{expected_candidate_scope_revision:'scope-2',expected_draft_version:2,mode:'selected',preview_sha256:'exact-additions',expected_binding_version:7,expected_query_revision:'main-seven',operation_uuid:'operation'});
  assert.ok(h.calls.every(c=>!c.endpoint.includes('/apply-to-protocol')));
 }finally{await h.close();}
});
test('cancel preview preserves exclusions and history restoration does not replay merge intent',async()=>{
 const h=await harness();try{
  await h.click('Merge matched data');await h.selectAndPreview();const route=h.navigation.route;await h.click('Cancel merge preview');assert.equal(h.accepts,0);assert.equal(h.previews,1);
  await h.restore({page:'overview',key:'back'});await h.restore(route);assert.equal(h.previews,1);assert.equal(h.accepts,0);assert.equal(h.container.querySelector('[aria-label="Additive acceptance preview"]'),null);
  assert.ok(h.calls.filter(c=>c.endpoint.endsWith('/draft')).every(c=>c.body.decisions.every(d=>!Object.hasOwn(d,'excluded'))));
 }finally{await h.close();}
});
test('cancel while preparation is pending prevents late completion from previewing or accepting',async()=>{
 const gate=deferred(),h=await harness({prepareGate:gate});try{
  await h.click('Merge matched data');await h.click('Cancel merge request');await act(async()=>gate.resolve());assert.equal(h.previews,0);assert.equal(h.accepts,0);
 }finally{await h.close();}
});
test('blocked preparation ends the merge request and exposes saved proposals without changing a draft',async()=>{
 const h=await harness({failPrepare:1});try{
  await h.click('Merge matched data');
  assert.match(h.container.querySelector('[role="alert"]').textContent,/stale authority or conflicting fingerprints/);
  assert.doesNotMatch(h.container.textContent,/Preparing your merge preview/);
  assert.equal(h.button('Cancel merge request'),undefined);
  await h.rerender();assert.equal(h.calls.filter(c=>c.endpoint===base+'/prepare').length,1,'failure does not retry on rerender');
  await h.click('Review saved proposals');assert.match(h.container.textContent,/Proposal history/);
  assert.equal(h.saved.history,true);assert.equal(h.previews,0);assert.equal(h.accepts,0);
  assert.ok(h.calls.every(c=>c.method==='GET'||c.endpoint===base+'/prepare'),'no draft or scientific mutation');
 }finally{await h.close();}
});
test('explicit preparation retry recovers browsing without replaying the failed merge intent',async()=>{
 const h=await harness({failPrepare:1});try{
  await h.click('Merge matched data');await h.click('Retry cumulative preparation');
  assert.ok(h.container.querySelector('[data-frozen-scope]'));
  assert.equal(h.previews,0,'the failed preview request was consumed');assert.equal(h.accepts,0);
  assert.equal(h.calls.filter(c=>c.endpoint===base+'/prepare').length,2);
  assert.ok(h.calls.every(c=>c.method==='GET'||c.endpoint===base+'/prepare'));
  await h.selectAndPreview();assert.equal(h.previews,1,'a new explicit request can preview');assert.equal(h.accepts,0);
 }finally{await h.close();}
});
for(const [label,options] of [['zero pending',{pending:0}],['unavailable queue',{failQueue:true}],['stale preview',{failPreview:true}],['zero eligible',{pending:1}]])test(`${label} never silently accepts`,async()=>{
 const h=await harness(options);try{
  await h.click('Merge matched data');assert.equal(h.accepts,0);
  if(options.failPreview){await h.selectAndPreview();assert.match(h.container.textContent,/Queue changed/);await h.rerender();assert.equal(h.previews,1,'failure never auto-retries');}
  else if(options.pending===1){await h.selectAndPreview();assert.equal(h.button('Add these additions to main').disabled,true);assert.match(h.container.textContent,/No eligible new epochs/);}
  else assert.equal(h.previews,0);
 }finally{await h.close();}
});
test('lost acceptance response retains the exact operation; repeated click recovers one durable mutation',async()=>{
 const h=await harness({failAccept:true});try{
  await h.click('Merge matched data');await h.selectAndPreview();await h.click('Add these additions to main');assert.equal(h.accepts,1);assert.match(h.container.textContent,/may have committed/);
  assert.equal(h.button('Cancel merge preview'),undefined);await h.rerender();assert.equal(h.previews,1);assert.equal(h.receiptBodies.length,1);
  await h.click('Recover acceptance receipt');assert.equal(h.accepts,1);assert.equal(h.receiptBodies.length,2);assert.equal(h.receiptBodies[0],h.receiptBodies[1]);
 }finally{await h.close();}
});
for(const wrong of ['project','protocol','unissued'])test(`restored ${wrong} intent cannot authorize a preview`,async()=>{
 const intent={kind:'preview_all',request_uuid:'restored',project_uuid:wrong==='project'?'other-project':project,protocol_uuid:wrong==='protocol'?'other-protocol':protocol};
 const h=await harness({restore:{page:'protocol',protocol,key:'restored',workbench:{merge_intent:intent}}});try{
  assert.equal(h.previews,0);assert.equal(h.accepts,0);assert.match(h.container.textContent,/no longer active/);assert.equal(h.navigation.route.workbench.merge_intent,undefined);
 }finally{await h.close();}
});
test('intent ledger verifies both issued and claimed destination and consumes only once',()=>{
 const ledger=createIncomingMergeIntents(),intent=ledger.issue(project,protocol);assert.equal(ledger.issue(project,protocol),intent);
 assert.equal(ledger.claim({...intent,protocol_uuid:'wrong'},project,'wrong'),false);assert.equal(ledger.claim(intent,project,protocol),false);
 const next=ledger.issue(project,protocol);assert.notEqual(next.request_uuid,intent.request_uuid);assert.equal(ledger.claim(next,project,protocol),true);assert.equal(ledger.claim(next,project,protocol),false);
 assert.equal(ledger.issue(null,protocol),null);
});
