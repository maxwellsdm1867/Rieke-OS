import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React,{act,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {createServer} from './test-support/isolatedVite.js';
const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');
const root=fileURLToPath(new URL('..',import.meta.url));
const protocol='strict-protocol',base=`/protocols/${protocol}/workbench`;
const context=id=>({candidate_revision_uuid:id,protocol:{definition:{protocol_uuid:protocol}},candidate_scope_revision:`scope-${id}`,draft:{draft_version:1,selection_mode:'selected'},counts:{pending_epochs:2}});
const prepared=token=>({contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:`prepare-${token}`,candidate_revision_uuid:`union-${token}`,root:`${base}/candidates/union-${token}`,candidate_scope_revision:`scope-union-${token}`,queue_revision:token,context:context(`union-${token}`)});
const queue=token=>({data:{queue_revision:token,pending_epoch_count:2,total_candidate_count:1,capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}},loading:false});
const deferred=()=>{let resolve;const promise=new Promise(value=>{resolve=value;});return {promise,resolve};};
const response=(value,status=200,headers)=>({ok:status>=200&&status<300,status,headers:headers?new Headers(headers):undefined,json:async()=>value});
const probes={name:'strict-frozen-browser-probe',enforce:'pre',resolveId(source,importer){if(importer?.endsWith('/FrozenIncomingReview.jsx')&&['../../epoch-browser/ui/Inspector.jsx','../../typed-query/ui/ProtocolViewFilter.jsx'].includes(source))return `\0strict-${source}`;},load(id){if(id==='\0strict-../../epoch-browser/ui/Inspector.jsx')return `import React from 'react';export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=true;export default function Inspector({readContext,readPaused,draftSelection,onReviewDecision,initialPageRead}){return React.createElement('div',{'data-inspector-scope':readContext.candidate_scope_revision,'data-paused':String(!!readPaused),'data-page-offer':String(!!initialPageRead)},React.createElement('button',{'data-draft-action':true,disabled:draftSelection.disabled,onClick:()=>onReviewDecision({epoch_uuids:['epoch-one'],changes:{reviewed:true}})},'Draft action'),React.createElement('button',{'data-preview-action':true,disabled:draftSelection.disabled,onClick:()=>draftSelection.onMerge(['epoch-one'])},'Preview action'));}`;if(id==='\0strict-../../typed-query/ui/ProtocolViewFilter.jsx')return 'export default function Filter(){return null;}';}};
async function harness(fetch,{withProfile=false}={}){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost/'});
 const lifetimeKey=`__incomingLifetime${Math.random().toString(36).slice(2)}`,lifetime={visible:true};globalThis[lifetimeKey]=lifetime;
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch};
 const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
 for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
 const lifetimeProbe={...probes,resolveId(source,importer){if(withProfile&&importer?.endsWith('/CumulativeIncomingReview.jsx')&&source==='./FrozenIncomingReview.jsx')return '\0strict-child-lifetime';return probes.resolveId(source,importer);},load(id){if(id==='\0strict-child-lifetime')return `import React from 'react';import Frozen from '/src/incoming-workbench/ui/FrozenIncomingReview.jsx';export default function Child(props){return globalThis[${JSON.stringify(lifetimeKey)}].visible?React.createElement(Frozen,props):null;}`;return probes.load(id);}};
 const server=await createServer({root,configFile:false,plugins:[lifetimeProbe],optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/CumulativeIncomingReview.jsx');
 const {AnnotationProfileProvider,useAnnotationProfile}=await server.ssrLoadModule('/src/annotations/annotationProfile.js');
 const container=dom.window.document.getElementById('root');let mounted=createRoot(container),setups=0,cleanups=0,saved,profile;
 function ProfileProbe({children}){profile=useAnnotationProfile();return children;}
 function Proof(props){useEffect(()=>{setups++;return()=>{cleanups++;};},[]);return props.hidden?null:React.createElement(Review,{protocolId:protocol,onSession:value=>{saved=value;},...props});}
 return {container,get saved(){return saved;},get setups(){return setups;},get cleanups(){return cleanups;},
  get profile(){return profile;},
  set childVisible(value){lifetime.visible=value;},
  async render(props){const actual={...(withProfile?{projectId:'profile-project',revision:0}:{}),...props};const child=React.createElement(Proof,actual);await act(async()=>mounted.render(React.createElement(React.StrictMode,null,withProfile?React.createElement(AnnotationProfileProvider,{projectId:actual.projectId},React.createElement(ProfileProbe,null,child)):child)));},
  async unmount(){if(mounted){await act(async()=>mounted.unmount());mounted=null;}},
  remount(){assert.equal(mounted,null);mounted=createRoot(container);},
  async close(){if(mounted)await act(async()=>mounted.unmount());await server.close();dom.window.close();delete globalThis[lifetimeKey];for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];}
 };
}
function contextResponse(endpoint){assert.ok(endpoint.endsWith('/context'),`No global fallback: ${endpoint}`);return response(context(endpoint.split('/').at(-2)));}

const authorProfiles=selected=>({selected_profile_uuid:selected,profiles:['actor-one','actor-two'].map(profile_uuid=>({profile_uuid,display_name:profile_uuid}))});
function livePrepared(token,actor='actor-one',project='profile-project'){
 const value=prepared(token);
 return {...value,actor,context:{...value.context,protocol:{definition:{protocol_uuid:protocol,project_uuid:project}}}};
}

for(const status of [200,201])test(`fresh prepare HTTP ${status} seeds one StrictMode child lifetime without persisting freshness`,async()=>{
 const value={...livePrepared('one'),reused:status===200},calls=[];
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');calls.push(endpoint);
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare')return response(value,status,{'X-Disco-Workbench-Context':'fresh-v1'});
  return contextResponse(endpoint);
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});assert.equal(view.profile.profileUuid,'actor-one');
  await view.render({queue:queue('one')});
  assert.equal(calls.filter(path=>path===base+'/prepare').length,1);
  assert.equal(calls.filter(path=>path.endsWith('/context')).length,0,'the freshly closed response supplies initial context');
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,value.candidate_scope_revision);
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,false);
  assert.deepEqual(view.saved.prepared,value);
  assert.doesNotMatch(JSON.stringify(view.saved),/fresh-v1|preparedContextToken|responseFresh|claimed/);
  await view.render({queue:queue('one')});assert.equal(calls.filter(path=>path.endsWith('/context')).length,0);
  // Keep the cumulative parent mounted while truly removing/recreating its
  // frozen child. The old header cannot grant a second initial context.
  view.childVisible=false;await view.render({queue:queue('one')});
  view.childVisible=true;await view.render({queue:queue('one')});
  assert.ok(calls.some(path=>path.endsWith('/context')));
  const beforeRefresh=calls.filter(path=>path.endsWith('/context')).length;
  await view.render({queue:queue('one'),revision:1});
  assert.ok(calls.filter(path=>path.endsWith('/context')).length>beforeRefresh,'revision refresh must GET');
  const saved=view.saved;await view.unmount();view.remount();await view.render({queue:queue('one'),session:saved});
  assert.ok(calls.filter(path=>path.endsWith('/context')).length>beforeRefresh+1,'saved-session mount must GET');
  assert.equal(calls.filter(path=>path===base+'/prepare').length,1);
 }finally{await view.close();}
});

for(const variant of ['receipt replay','unknown header','wrong actor','wrong project','unresolved profile'])test(`${variant} cannot seed a frozen context`,async()=>{
 const value=livePrepared('one',variant==='wrong actor'?'actor-two':'actor-one',variant==='wrong project'?'another-project':'profile-project');
 const calls=[],headers=variant==='receipt replay'?undefined:{'X-Disco-Workbench-Context':variant==='unknown header'?'fresh-v2':'fresh-v1'};
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');calls.push(endpoint);
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare')return response(value,200,headers);
  return contextResponse(endpoint);
 },{withProfile:variant!=='unresolved profile'});
 try{
  await view.render({hidden:true,projectId:'profile-project',queue:queue('one')});await view.render({projectId:'profile-project',queue:queue('one')});
  assert.ok(calls.some(path=>path.endsWith('/context')));
  assert.ok(view.container.querySelector('[data-inspector-scope]'));
 }finally{await view.close();}
});

test('an existing uncertain workflow uses GET even when preparation returns a fresh response',async()=>{
 const value=livePrepared('one'),calls=[];
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');calls.push(endpoint);
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare')return response(value,201,{'X-Disco-Workbench-Context':'fresh-v1'});
  return contextResponse(endpoint);
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});
  await view.render({queue:queue('one'),session:{drafts:{[value.candidate_revision_uuid]:{unconfirmed:true,operation:'saved-operation'}}}});
  assert.ok(calls.some(path=>path.endsWith('/context')));
  assert.equal(view.saved.drafts[value.candidate_revision_uuid].operation,'saved-operation');
  assert.equal(view.saved.drafts[value.candidate_revision_uuid].unconfirmed,true);
 }finally{await view.close();}
});

test('profile A-B-A retires a seeded context before effects and rejects late old reads',async()=>{
 let selected='actor-one';const reads=[];
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles(selected));
  if(endpoint==='/annotation-profiles/selected'){selected=JSON.parse(options.body).profile_uuid;return response({selected_profile_uuid:selected,profile:{profile_uuid:selected}});}
  if(endpoint===base+'/prepare')return response(livePrepared('one'),201,{'X-Disco-Workbench-Context':'fresh-v1'});
  assert.ok(endpoint.endsWith('/context'));const pending=deferred(),actor=selected;reads.push({pending,actor});await pending.promise;
  return response({...context('union-one'),candidate_scope_revision:`current-${actor}`});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});assert.equal(reads.length,0);
  await act(async()=>view.profile.selectProfile('actor-two'));
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.paused,'true');
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,true);
  assert.ok(reads.some(read=>read.actor==='actor-two'));
  await act(async()=>view.profile.selectProfile('actor-one'));
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,true);
  const current=reads.at(-1);assert.equal(current.actor,'actor-one');
  await act(async()=>current.pending.resolve());
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-actor-one');
  await act(async()=>{for(const read of reads)read.pending.resolve();});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-actor-one');
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,false);
 }finally{await act(async()=>{for(const read of reads)read.pending.resolve();});await view.close();}
});

test('profile loading and error retire the old seed while replacement GET is pending',async()=>{
 let profileGate=null;const reads=[];
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return profileGate?await profileGate.promise:response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare')return response(livePrepared('one'),201,{'X-Disco-Workbench-Context':'fresh-v1'});
  assert.ok(endpoint.endsWith('/context'));const pending=deferred();reads.push(pending);await pending.promise;return contextResponse(endpoint);
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});assert.equal(reads.length,0);
  profileGate=deferred();await act(async()=>view.profile.reload());
  assert.equal(view.profile.loading,true);assert.equal(view.container.querySelector('[data-draft-action]').disabled,true);
  const loadingReads=reads.length;assert.ok(loadingReads>0);
  await act(async()=>profileGate.resolve(response({error:'Profiles unavailable'},503)));
  assert.match(view.profile.error,/Profiles unavailable/);
  assert.ok(reads.length>loadingReads);assert.equal(view.container.querySelector('[data-draft-action]').disabled,true);
  await act(async()=>reads.at(-1).resolve());
  assert.ok(view.container.querySelector('[data-inspector-scope]'),'fresh GET retains existing server-context fallback');
 }finally{profileGate?.resolve(response(authorProfiles('actor-one')));await act(async()=>{for(const read of reads)read.resolve();});await view.close();}
});

test('profile A-B-A while preparation is pending cannot revive the old fresh response',async()=>{
 let selected='actor-one';const prepares=[],reads=[];
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles(selected));
  if(endpoint==='/annotation-profiles/selected'){selected=JSON.parse(options.body).profile_uuid;return response({selected_profile_uuid:selected,profile:{profile_uuid:selected}});}
  if(endpoint===base+'/prepare'){const pending=deferred();prepares.push({pending,actor:selected});return pending.promise;}
  reads.push(endpoint);return contextResponse(endpoint);
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});const old=prepares[0];
  await act(async()=>view.profile.selectProfile('actor-two'));await act(async()=>view.profile.selectProfile('actor-one'));
  assert.ok(prepares.length>=3);const current=prepares.at(-1);assert.notEqual(current,old);assert.equal(current.actor,'actor-one');
  await act(async()=>old.pending.resolve(response(livePrepared('one'),201,{'X-Disco-Workbench-Context':'fresh-v1'})));
  assert.equal(view.saved?.prepared||null,null);assert.equal(view.container.querySelector('[data-inspector-scope]'),null);
  await act(async()=>current.pending.resolve(response(livePrepared('one'))));
  assert.ok(reads.some(path=>path.endsWith('/context')),'current attempt replays durable receipt, so GET is required');
  await act(async()=>{for(const attempt of prepares)attempt.pending.resolve(response(livePrepared('one',attempt.actor),201,{'X-Disco-Workbench-Context':'fresh-v1'}));});
  assert.equal(view.saved.prepared.actor,'actor-one');
 }finally{await act(async()=>{for(const attempt of prepares)attempt.pending.resolve(response(livePrepared('one',attempt.actor)));});await view.close();}
});

for(const failed of [false,true])test(`a late ${failed?'failed':'committed'} draft reply cannot replace a new profile context`,async()=>{
 let selected='actor-one',writes=0;const pending=deferred();
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles(selected));
  if(endpoint==='/annotation-profiles/selected'){selected=JSON.parse(options.body).profile_uuid;return response({selected_profile_uuid:selected,profile:{profile_uuid:selected}});}
  if(endpoint===base+'/prepare')return response(livePrepared('one'),201,{'X-Disco-Workbench-Context':'fresh-v1'});
  if(endpoint.endsWith('/draft')){writes++;return pending.promise;}
  assert.ok(endpoint.endsWith('/context'));return response({...context('union-one'),candidate_scope_revision:`current-${selected}`});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});
  await act(async()=>view.container.querySelector('[data-draft-action]').click());assert.equal(writes,1);
  await act(async()=>view.profile.selectProfile('actor-two'));
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,true,'old write remains pending');
  await act(async()=>pending.resolve(failed?response({error:'Old draft response failed'},503):response({...context('union-one'),candidate_scope_revision:'old-actor-committed-draft'})));
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-actor-two');
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,false);
  assert.doesNotMatch(view.container.textContent,/Old draft response failed/);
  assert.equal(writes,1,'old completion is not replayed or rolled back');
 }finally{pending.resolve(response(context('union-one')));await view.close();}
});

test('a held old-profile preview keeps committed draft work but cannot publish a new preview',async()=>{
 let selected='actor-one',drafts=0,previews=0;const pending=deferred(),value=livePrepared('one');
 value.context.draft={draft_version:1,selection_mode:'selected',decisions:[{epoch_uuid:'epoch-one',selected:false,reviewed:true,excluded:false}],decisions_total:1,decisions_truncated:false};
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles(selected));
  if(endpoint==='/annotation-profiles/selected'){selected=JSON.parse(options.body).profile_uuid;return response({selected_profile_uuid:selected,profile:{profile_uuid:selected}});}
  if(endpoint===base+'/prepare')return response(value,201,{'X-Disco-Workbench-Context':'fresh-v1'});
  if(endpoint.endsWith('/draft')){drafts++;return response({...value.context,candidate_scope_revision:'old-draft-saved',draft:{...value.context.draft,draft_version:2}});}
  if(endpoint.endsWith('/preview')){previews++;return pending.promise;}
  assert.ok(endpoint.endsWith('/context'));return response({...context('union-one'),candidate_scope_revision:`current-${selected}`});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});
  await act(async()=>view.container.querySelector('[data-preview-action]').click());assert.equal(drafts,1);assert.equal(previews,1);
  await act(async()=>view.profile.selectProfile('actor-two'));
  await act(async()=>pending.resolve(response({preview_sha256:'old-preview',expected_binding_version:1,expected_query_revision:'old-query',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:2,next_epoch_count:3,accepted_cell_count:1})));
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-actor-two');
  assert.equal(view.container.querySelector('[aria-label="Additive acceptance preview"]'),null);
  assert.equal(view.saved.drafts['union-one'].preview,null);assert.equal(view.saved.drafts['union-one'].operation,null);
  assert.equal(drafts,1);assert.equal(previews,1,'no retry or acceptance follows old preview completion');
 }finally{pending.resolve(response({error:'Cancelled test'},409));await view.close();}
});

test('one-action merge stops after a held draft when its profile owner changes',async()=>{
 let selected='actor-one',drafts=0,previews=0;const pending=deferred(),value=livePrepared('one');
 value.context.draft={draft_version:1,selection_mode:'selected',decisions:[{epoch_uuid:'epoch-one',selected:false,reviewed:true,excluded:false}],decisions_total:1,decisions_truncated:false};
 const view=await harness(async(path,options={})=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles(selected));
  if(endpoint==='/annotation-profiles/selected'){selected=JSON.parse(options.body).profile_uuid;return response({selected_profile_uuid:selected,profile:{profile_uuid:selected}});}
  if(endpoint===base+'/prepare')return response(value,201,{'X-Disco-Workbench-Context':'fresh-v1'});
  if(endpoint.endsWith('/draft')){drafts++;return pending.promise;}
  if(endpoint.endsWith('/preview')||endpoint.endsWith('/accept')){previews++;throw Error('Retired consent must not submit another command');}
  assert.ok(endpoint.endsWith('/context'));return response({...context('union-one'),candidate_scope_revision:`current-${selected}`});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:queue('one')});await view.render({queue:queue('one')});
  await act(async()=>view.container.querySelector('[data-preview-action]').click());assert.equal(drafts,1);assert.equal(previews,0);
  await act(async()=>view.profile.selectProfile('actor-two'));
  await act(async()=>pending.resolve(response({...value.context,candidate_scope_revision:'old-draft-saved',draft:{...value.context.draft,draft_version:2}})));
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-actor-two');
  assert.equal(view.container.querySelector('[aria-label="Additive acceptance preview"]'),null);
  assert.equal(view.saved.drafts['union-one'].preview,null);assert.equal(view.saved.drafts['union-one'].operation,null);
  assert.equal(drafts,1);assert.equal(previews,0,'no preview or acceptance follows old draft completion');
 }finally{pending.resolve(response({error:'Cancelled test'},409));await view.close();}
});

test('ReactDOM StrictMode first entry rejoins one preparation and opens Inspector without Retry',async()=>{
 const gate=deferred(),bodies=[];
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);await gate.promise;return response(prepared('one'));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});assert.equal(view.setups,2);assert.equal(view.cleanups,1,'ReactDOM really replayed effects');assert.equal(bodies.length,1);
  assert.doesNotMatch(view.container.textContent,/interrupted|Retry cumulative/);
  await act(async()=>gate.resolve());
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'scope-union-one');assert.equal(bodies.length,1);assert.doesNotMatch(view.container.textContent,/Retry cumulative/);
 }finally{await view.close();}
});

test('changed authority supersedes pending display and ignores a late old completion',async()=>{
 const gates={old:deferred(),new:deferred()},bodies=[];
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){const token=JSON.parse(options.body).expected_queue_revision;bodies.push(options.body);await gates[token].promise;return response(prepared(token));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('old')});await view.render({queue:queue('new')});assert.equal(bodies.length,2);
  await act(async()=>gates.new.resolve());assert.equal(view.saved.prepared.queue_revision,'new');
  await act(async()=>gates.old.resolve());assert.equal(view.saved.prepared.queue_revision,'new');assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'scope-union-new');
 }finally{await view.close();}
});

test('genuine unmount detaches late response and remount retries the identical server-idempotent body',async()=>{
 const first=deferred(),bodies=[],receipts=new Map();let writes=0;
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);if(!receipts.has(options.body)){writes++;receipts.set(options.body,prepared('one'));}if(bodies.length===1)await first.promise;return response(receipts.get(options.body));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});const saved=view.saved;await view.unmount();
  await act(async()=>first.resolve());assert.equal(view.container.childNodes.length,0);assert.equal(view.saved,saved,'unmounted subscriber cannot publish a result');
  view.remount();await view.render({queue:queue('one'),session:saved});
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.equal(writes,1,'server receipt identity derives from the unchanged request');assert.equal(view.saved.prepared.queue_revision,'one');
 }finally{await view.close();}
});

test('lost preparation response requires explicit retry with identical body and recovers one receipt',async()=>{
 const bodies=[],receipt=prepared('one');let writes=0;
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===base+'/prepare'){bodies.push(options.body);if(bodies.length===1){writes++;return response({error:'Reply lost after commit'},503);}return response(receipt);}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('one')});assert.equal(bodies.length,1);assert.match(view.container.textContent,/Reply lost/);
  await view.render({queue:{...queue('one')}});assert.equal(bodies.length,1,'ordinary rerender does not repeat failed mutations');
  const retry=[...view.container.querySelectorAll('button')].find(button=>button.textContent==='Retry cumulative preparation');assert.ok(retry);
  await act(async()=>retry.dispatchEvent(new window.MouseEvent('click',{bubbles:true})));
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.equal(writes,1);assert.equal(view.saved.prepared.prepare_operation_uuid,receipt.prepare_operation_uuid);
 }finally{await view.close();}
});

test('StrictMode preserves an uncertain acceptance body before preparing newer authority',async()=>{
 const old=prepared('old'),acceptBodies=[];let prepares=0;
 const preview={expected_candidate_scope_revision:old.candidate_scope_revision,expected_draft_version:1,mode:'selected',preview_sha256:'sealed-preview',expected_binding_version:1,expected_query_revision:'main-old',selected_epoch_count:1,accepted_epoch_count:1,already_present_epoch_count:0,retained_epoch_count:1,next_epoch_count:2,accepted_cell_count:1};
 const view=await harness(async(path,options={})=>{const endpoint=String(path).replace(/^\/api/,'');if(endpoint===old.root+'/accept'){acceptBodies.push(JSON.parse(options.body));return response({operation_uuid:'same-operation',candidate_revision_uuid:old.candidate_revision_uuid,event_uuid:'accepted',binding:{revision_uuid:'main-new',version:2}});}if(endpoint===base+'/prepare'){prepares++;return response(prepared('new'));}return contextResponse(endpoint);});
 try{
  await view.render({queue:queue('new'),session:{prepared:old,drafts:{[old.candidate_revision_uuid]:{unconfirmed:true,operation:'same-operation',preview}}}});
  assert.equal(prepares,0);assert.deepEqual(view.saved.drafts[old.candidate_revision_uuid].preview,preview);
  const retry=[...view.container.querySelectorAll('button')].find(button=>button.textContent==='Recover acceptance receipt');assert.ok(retry);
  await act(async()=>retry.dispatchEvent(new window.MouseEvent('click',{bubbles:true})));
  assert.equal(acceptBodies.length,1);assert.equal(acceptBodies[0].operation_uuid,'same-operation');for(const [key,value] of Object.entries(preview))if(key.startsWith('expected_')||key==='mode'||key==='preview_sha256')assert.equal(acceptBodies[0][key],value);
  assert.equal(prepares,1);assert.equal(view.saved.prepared.queue_revision,'new');
 }finally{await view.close();}
});


function bootstrapPrepared(project='profile-project',scope='fresh-scope'){
 const value=livePrepared('one','actor-one',project);
 const fresh={...value.context,candidate_scope_revision:scope,expected_binding_version:1,generation:{metadata:'fixture'},
   protocol:{...value.context.protocol,query_revision:scope,expected_binding_version:1}};
 return {...value,bootstrap:{contract_version:1,kind:'workbench_initial_page',root:value.root,project_uuid:project,protocol_uuid:protocol,
   candidate_revision_uuid:value.candidate_revision_uuid,actor:'actor-one',context:fresh,
   request:{filters:{},offset:0,limit:60,include_cells:true},page:{candidate_scope_revision:scope,query_revision:scope,expected_binding_version:1,
     generation:fresh.generation,total:0,offset:0,limit:60,epochs:[],cells:[]}}};
}
const bootstrapQueue=()=>{const value=queue('one');return {...value,data:{...value.data,capabilities:{...value.data.capabilities,initial_page:true}}};};
test('fresh replay bootstrap owns display while durable receipt and saved session stay unchanged',async()=>{
 const value=bootstrapPrepared(),calls=[];
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');calls.push(endpoint);
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare?include_initial_page=true')return response(value);
  assert.fail(`Unexpected bootstrap fallback ${endpoint}`);
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:bootstrapQueue()});await view.render({queue:bootstrapQueue()});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'fresh-scope');
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.pageOffer,'true');
  const {bootstrap,...receipt}=value;assert.deepEqual(view.saved.prepared,receipt);
  assert.doesNotMatch(JSON.stringify(view.saved),/bootstrap|fresh-scope|workbench_initial_page/);
  assert.equal(calls.filter(path=>path.endsWith('/context')).length,0);
 }finally{await view.close();}
});
test('retained bootstrap stays inert across a held project A-B-A transition',async()=>{
 const reads=[];let currentProject='profile-project';
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  if(endpoint===base+'/prepare?include_initial_page=true')return response(bootstrapPrepared(currentProject));
  assert.equal(endpoint,base+'/candidates/union-one/context?include_initial_page=true');
  const pending=deferred(),project=currentProject;reads.push({pending,project});await pending.promise;
  const value=bootstrapPrepared(project,`current-${project}`);return response({...value.bootstrap.context,bootstrap:value.bootstrap});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:bootstrapQueue()});await view.render({queue:bootstrapQueue()});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.pageOffer,'true');
  currentProject='other-project';await view.render({projectId:currentProject,queue:bootstrapQueue()});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.pageOffer,'false');
  assert.equal(view.container.querySelector('[data-draft-action]').disabled,true);
  currentProject='profile-project';await view.render({projectId:currentProject,queue:bootstrapQueue()});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.pageOffer,'false');
  await act(async()=>reads.at(-1).pending.resolve());
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-profile-project');
  await act(async()=>{for(const read of reads)read.pending.resolve();});
  assert.equal(view.container.querySelector('[data-inspector-scope]').dataset.inspectorScope,'current-profile-project');
 }finally{await act(async()=>{for(const read of reads)read.pending.resolve();});await view.close();}
});

test('fresh GET bootstrap for another resolved actor never enables the frozen view',async()=>{
 const view=await harness(async(path)=>{
  const endpoint=String(path).replace(/^\/api/,'');
  if(endpoint==='/annotation-profiles')return response(authorProfiles('actor-one'));
  const value=bootstrapPrepared();value.actor='actor-two';value.bootstrap.actor='actor-two';
  if(endpoint===base+'/prepare?include_initial_page=true')return response(value);
  assert.equal(endpoint,base+'/candidates/union-one/context?include_initial_page=true');
  return response({...value.bootstrap.context,bootstrap:value.bootstrap});
 },{withProfile:true});
 try{
  await view.render({hidden:true,queue:bootstrapQueue()});await view.render({queue:bootstrapQueue()});
  assert.match(view.container.textContent,/different actor/);
  assert.equal(view.container.querySelector('[data-inspector-scope]'),null);
 }finally{await view.close();}
});
