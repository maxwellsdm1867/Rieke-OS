import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {createRequire} from 'node:module';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createWorkspacePresentationSessions,AUTHORED_DRAFT_LIMITS} from './presentation/workspacePresentationSessions.js';
import {createDesktopDraftSession} from './renderer-drafts/desktopDraftSession.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const {DraftStore}=createRequire(import.meta.url)('../../desktop/drafts/draft-store.cjs');
const projectId='00000000-0000-0000-0000-000000000001';
const route={page:'cell-qc',cell_uuid:'cell-0',key:'qc'};

test('bounded authored checkpoints preserve exact identities and refuse unsaved overflow instead of eviction',()=>{
 const owner=createWorkspacePresentationSessions(),key=['tag','epoch-A','text'];
 owner.rememberDraft(route,key,'keep');owner.remember(route,{selected:'epoch-A'});
 assert.equal(owner.readDraft(route,key),'keep');assert.equal(owner.readDraft({...route,cell_uuid:'same-label-other-cell'},key),undefined);
 assert.throws(()=>owner.rememberDraft(route,key,'x'.repeat(AUTHORED_DRAFT_LIMITS.textBytes+1)),/limit/);
 assert.equal(owner.readDraft(route,key),'keep');assert.throws(()=>owner.checkpoint(route),/limit/);
 owner.rememberDraft(route,key,'recovered');const restored=createWorkspacePresentationSessions();restored.restore(JSON.parse(JSON.stringify(owner.checkpoint(route))));
 assert.equal(restored.readDraft(route,key),'recovered');assert.throws(()=>restored.rememberDraft(route,['bad'],{confirmed:true}),/Only authored/);
 assert.throws(()=>restored.checkpoint(route),/Only authored/);restored.rememberDraft(route,['bad'],undefined);
 restored.pruneDeleted({removedEpochs:['epoch-A']});assert.equal(restored.readDraft(route,key),undefined);
 const invalidKey=['too-long','x'.repeat(AUTHORED_DRAFT_LIMITS.keyBytes)];assert.throws(()=>restored.rememberDraft(route,invalidKey,'retain locally'),/identity exceeds/);assert.throws(()=>restored.checkpoint(route),/identity exceeds/);restored.rememberDraft(route,invalidKey,undefined);assert.doesNotThrow(()=>restored.checkpoint(route));
 const firstProtocol={page:'protocol',protocol:'protocol-A',key:'visit-1'};assert.throws(()=>restored.rememberDraft(firstProtocol,invalidKey,'unfinished'),/identity exceeds/);
 restored.rememberDraft({...firstProtocol,protocol:'protocol-B'},invalidKey,undefined);assert.throws(()=>restored.checkpoint(route),/identity exceeds/);
 restored.rememberDraft({...firstProtocol,key:'visit-2'},invalidKey,undefined);assert.doesNotThrow(()=>restored.checkpoint(route));
});
test('authored checkpoint budget never silently evicts earlier unfinished fields',()=>{
 const owner=createWorkspacePresentationSessions();for(let i=0;i<AUTHORED_DRAFT_LIMITS.entries;i++)owner.rememberDraft(route,['input',String(i)],'text');
 assert.throws(()=>owner.rememberDraft(route,['overflow'],'new text'),/Too many/);assert.equal(owner.readDraft(route,['input','0']),'text');assert.throws(()=>owner.checkpoint(route),/Too many/);
 owner.rememberDraft(route,['overflow'],undefined);assert.equal(owner.checkpoint(route).authoredDrafts.length,AUTHORED_DRAFT_LIMITS.entries);
});
async function setup(t,options={}){
 const directory=await mkdtemp(path.join(os.tmpdir(),'disco-authored-drafts-')),store=new DraftStore(directory),h=await createWorkflowHarness(options);
 const {RetainedWorkspaceViews}=await h.module('retainedWorkspaceViews.js');let owner=createWorkspacePresentationSessions(),draft;
 const bridge={loadDraft:id=>store.load(id),saveDraft:payload=>store.save(payload)};
 const makeSession=currentRoute=>createDesktopDraftSession({projectId,bridge,isBusy:()=>false,snapshot:()=>owner.checkpoint(currentRoute),restore:value=>owner.restore(value)});
 function Screen({Component,props={},currentRoute=route}){return React.createElement(RetainedWorkspaceViews,{projectId,projectPath:'/owned/fixture',presentation:owner,route:currentRoute,render:(ownRoute,{remember})=>React.createElement(Component,{...props,session:owner.read(ownRoute).session,onSession:remember})});}
 t.after(async()=>{draft?.close();await h.close();await rm(directory,{recursive:true,force:true});});
 return {h,store,get owner(){return owner;},async update(Component,props={},currentRoute=route){await h.render(Screen,{Component,props,currentRoute});},async mount(Component,props={},currentRoute=route){draft=makeSession(currentRoute);await draft.flush();await h.mount(Screen,{Component,props,currentRoute});},async restart(Component,props={},currentRoute=route){await draft.flush();const saved=await store.load(projectId);draft.close();await h.render(()=>null,{});owner=createWorkspacePresentationSessions();draft=makeSession(currentRoute);await draft.flush();await h.render(Screen,{Component,props,currentRoute});return saved;}};
}
test('CellQC unfinished tag survives actual DraftStore save and new renderer lifetime without submitting annotations',async t=>{
 const s=await setup(t),{h}=s;
 h.fixture.respond=(url,options,fallback)=>{const pathname=url.pathname.replace('/api','');
  if(pathname==='/cells/cell-0/qc')return {cell:{cell_uuid:'cell-0',label:'same label'},counts:{epochs:1},families:[{id:'a',label:'A',epoch_count:1}]};
  if(pathname==='/cells/cell-0/qc/epochs')return {epochs:[{epoch_uuid:'epoch-0',epoch_number:1}],total:1};
  if(pathname==='/cells/cell-0/qc/response')return {cell_uuid:'cell-0',epoch_uuid:'epoch-0',statistics:{pre:{mean:1},stim:{mean:2},delta_mean:1,units:'mV'}};
  if(pathname==='/explore/predicate-fields')return {fields:[]};return fallback();};
 const CellQC=await h.component('CellQC');s.owner.remember(route,{family:'a',selected:'epoch-0',showMetadata:true});const input=()=>h.root.findByProps({'aria-label':'Tag this epoch'});
 await s.mount(CellQC,{cellUuid:'cell-0',revision:0});await h.waitFor(()=>h.root.findAllByProps({'aria-label':'Tag this epoch'}).length===1);
 await h.act(()=>input().props.onChange({target:{value:'Unfinished scientific note'}}));
 const saved=await s.restart(CellQC,{cellUuid:'cell-0',revision:0});await h.waitFor(()=>h.root.findAllByProps({'aria-label':'Tag this epoch'}).length===1);
 assert.equal(input().props.value,'Unfinished scientific note');assert.ok(saved.value.authoredDrafts.length);assert.equal(h.fixture.requests.filter(request=>request.path==='/annotations'&&request.method==='POST').length,0);
});
test('candidate export fields restore by candidate identity, never label or restored mutation state',async t=>{
 const s=await setup(t),{h}=s,Component=await h.component('CandidateExportPanel');const candidate=id=>({revision_uuid:id,recipe:{full_recipe_sha256:'hash',epoch_count:1}}),props={candidate:candidate('candidate-A'),defaultName:'Same name'};
 const name=()=>h.root.findByProps({className:'candidate-export-name'}).findByType('input');await s.mount(Component,props,{page:'explore',key:'search'});await h.act(()=>name().props.onChange({target:{value:'My unfinished export'}}));
 await h.act(()=>h.root.findAllByType('input').find(input=>input.props.value==='matlab-mat').props.onChange());
 const saved=await s.restart(Component,props,{page:'explore',key:'search'});assert.equal(name().props.value,'My unfinished export');assert.equal(h.root.findAllByType('input').find(input=>input.props.value==='matlab-mat').props.checked,true);
 assert.equal(JSON.stringify(saved).includes('confirmed'),false);assert.equal(h.fixture.requests.filter(request=>request.method==='POST').length,0);
 await s.restart(Component,{...props,candidate:candidate('candidate-B')},{page:'explore',key:'search'});assert.equal(name().props.value,'Same name');
});
test('saved-search name and description survive restart and fresh resolve does not overwrite authored text',async t=>{
 const s=await setup(t),{h}=s,Component=await h.component('QueryPresetDialog');const predicate={field:'protocol',operator:'contains',value:'noise'},preset={preset_uuid:'preset-A',name:'Same name',description:'Server description',pinned:false,version:1,predicate,splits:'date,cell'};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/search-presets/resolve'?{preset}:fallback();const props={predicate,splits:'date,cell',preset,onClose(){},onSaved(){}};
 await s.mount(Component,props,{page:'explore',key:'search'});await h.settle(30);const name=()=>h.root.findAllByType('input').find(input=>input.props.placeholder==='e.g. History noise · NBQX');
 await h.act(()=>name().props.onChange({target:{value:'My unfinished name'}}));await h.act(()=>h.root.findByType('textarea').props.onChange({target:{value:'My unpublished explanation'}}));
 await s.restart(Component,props,{page:'explore',key:'search'});await h.settle(30);assert.equal(name().props.value,'My unfinished name');assert.equal(h.root.findByType('textarea').props.value,'My unpublished explanation');assert.equal(h.fixture.requests.some(request=>request.method==='PUT'||request.path==='/search-presets'),false);
});
test('predicate editor unsubmitted AST survives disk roundtrip without rerunning search or preview',async t=>{
 const s=await setup(t),{h}=s,Component=await h.component('PredicateDialog');const {newGroup,newCondition}=await h.module('typed-query/ui/predicateState.js');const initial={...newGroup(),children:[{...newCondition(),field:'protocol',operator:'contains',valueText:'initial'}]};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/project-preferences'?{format:'rieke-project-preferences',version:1,project_uuid:projectId,state:{protocol_shortcuts:{}},revisions:{protocol_shortcuts:0}}:fallback();let searches=0;const props={draft:initial,catalog:{data:{fields:[{id:'protocol',label:'Protocol',types:['string'],operators:['contains']}]},loading:false},projectId,onSearch(){searches++;},onClose(){}};
 await s.mount(Component,props,{page:'explore',key:'search'});const builder=()=>h.root.find(node=>typeof node.type==='function'&&node.type.name==='PredicateBuilder');const edited={...initial,children:[{...initial.children[0],valueText:'unfinished changed value'}]};await h.act(()=>builder().props.onChange(edited));
 await s.restart(Component,props,{page:'explore',key:'search'});assert.equal(builder().props.draft.children[0].valueText,'unfinished changed value');assert.equal(searches,0);assert.equal(h.fixture.requests.some(request=>request.path==='/explore/preview'),false);
});
test('canonical search hydration creates no authored entry; failed saves retain drafts and repeated successful saves retire them',async t=>{
 const s=await setup(t),{h}=s,Component=await h.component('QueryPresetDialog');const predicate={field:'protocol',operator:'contains',value:'noise'};
 let preset={preset_uuid:'preset-A',version:1,name:'Canonical existing name',description:'Canonical description',pinned:true,predicate,splits:'date,cell'},fail=true;
 h.fixture.respond=(url,options,fallback)=>{
  if(url.pathname==='/api/search-presets/resolve')return {preset};
  if(url.pathname==='/api/search-presets/preset-A'&&options.method==='PUT'){
   if(fail)return {failure:503,error:'Save unavailable'};
   const body=JSON.parse(options.body);preset={...preset,...body,version:preset.version+1};return preset;
  }
  return fallback();
 };
 const currentRoute={page:'explore',key:'search'},props={predicate,splits:'date,cell',defaults:{name:'Suggested new name'},onClose(){},onSaved(){}};
 await s.mount(Component,props,currentRoute);await h.settle(30);
 const name=()=>h.root.findAllByType('input').find(input=>input.props.placeholder==='e.g. History noise · NBQX');
 assert.equal(name().props.value,'Canonical existing name');assert.equal(s.owner.checkpoint(currentRoute).authoredDrafts,undefined);
 await h.act(()=>name().props.onChange({target:{value:'Keep after failure'}}));await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));
 assert.equal(s.owner.checkpoint(currentRoute).authoredDrafts.length,1);assert.equal(name().props.value,'Keep after failure');
 fail=false;await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));assert.equal(s.owner.checkpoint(currentRoute).authoredDrafts,undefined);
 for(let index=0;index<3;index++){
  await s.restart(Component,props,currentRoute);await h.settle(20);await h.act(()=>name().props.onChange({target:{value:`Successful edit ${index}`}}));
  await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));assert.equal(s.owner.checkpoint(currentRoute).authoredDrafts,undefined);
 }
});
test('group-tag individual epoch drafts never leak to a sibling epoch in the same cell',async t=>{
 const s=await setup(t,{portals:true}),{h}=s,{useTreeGroupTags}=await h.module('annotations/ui/TreeGroupTags.jsx');
 const epoch=uuid=>({epoch_uuid:uuid,cell_uuid:'cell-0',epoch_number:1,annotations:{epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}});
 function Editor(){const tags=useTreeGroupTags({protocolId:'protocol-A',revision:0,filters:{},splits:'cell'});return React.createElement('div',null,
  React.createElement('button',{onClick:()=>tags.openEpoch(epoch('epoch-0'))},'First epoch'),React.createElement('button',{onClick:()=>tags.openEpoch(epoch('epoch-1'))},'Sibling epoch'),tags.dialog);}
 const button=label=>h.root.findAllByType('button').find(node=>node.children.includes(label));
 await s.mount(Editor,{}, {page:'protocol',protocol:'protocol-A',key:'protocol'});
 await h.act(()=>button('First epoch').props.onClick());const input=()=>h.root.findByProps({'aria-label':'Tag this epoch'});
 await h.act(()=>input().props.onChange({target:{value:'Only the first epoch'}}));await h.act(()=>h.root.findByProps({'aria-label':'Close group tags'}).props.onClick());
 await h.act(()=>button('Sibling epoch').props.onClick());assert.equal(input().props.value,'');await h.act(()=>h.root.findByProps({'aria-label':'Close group tags'}).props.onClick());
 await h.act(()=>button('First epoch').props.onClick());assert.equal(input().props.value,'Only the first epoch');
 const before=h.fixture.requests.filter(request=>request.path==='/annotations').length;
 await s.restart(Editor,{}, {page:'protocol',protocol:'protocol-A',key:'protocol'});await h.act(()=>button('First epoch').props.onClick());
 assert.equal(input().props.value,'Only the first epoch');assert.equal(h.fixture.requests.filter(request=>request.path==='/annotations').length,before);
});
test('held authored completion clears only its captured entity; stale adopt and change never edit the new entity',async t=>{
 const s=await setup(t),{h}=s,{useAuthoredDraft}=await h.module('presentation/useAuthoredDraft.js');let controls;
 function Field({entity}){const [value,change,draft]=useAuthoredDraft(['candidate',entity,'name'],'default');controls={value,change,...draft};return React.createElement('input',{value,onChange:event=>change(event.target.value)});}
 await s.mount(Field,{entity:'A'});await h.act(()=>controls.change('unfinished A'));const heldA=controls;
 await s.update(Field,{entity:'B'});await h.act(()=>controls.change('unfinished B'));
 await h.act(()=>{heldA.clear();heldA.adopt('stale canonical A');heldA.change('late A edit');});
 assert.equal(controls.value,'unfinished B');assert.equal(s.owner.readDraft(route,['candidate','A','name']),undefined);assert.equal(s.owner.readDraft(route,['candidate','B','name']),'unfinished B');
 await s.update(Field,{entity:'C'});await h.act(()=>heldA.adopt('stale A into pristine C'));assert.equal(controls.value,'default');
});
test('typing before held DraftStore load wins over saved presentation while operation recovery still hydrates',async t=>{
 const s=await setup(t),{h}=s,{AuthoredDraftScope,useAuthoredDraft}=await h.module('presentation/useAuthoredDraft.js');
 const old=createWorkspacePresentationSessions(),shellRoute={page:'project-shell',key:'project-shell'},key=['project-creation','name'];old.rememberDraft(shellRoute,key,'Old disk text');
 await s.store.save({projectId,value:{format:'rieke-renderer-draft',version:1,projectId,value:{...old.checkpoint({page:'stores',key:'old'}),sourceMerge:{operation_uuid:'retained-operation'}}}});
 let release,restores=0,recovery=null;const gate=new Promise(resolve=>{release=resolve;});
 const draft=createDesktopDraftSession({projectId,isBusy:()=>false,navigationIdentity:()=>JSON.stringify([0,s.owner.authoredIntent()]),bridge:{loadDraft:async id=>{const value=await s.store.load(id);await gate;return value;},saveDraft:payload=>s.store.save(payload)},
  snapshot:()=>({...s.owner.checkpoint({page:'overview',key:'current'}),sourceMerge:recovery}),restore:value=>{restores++;s.owner.restore(value);},restoreRecovery:value=>{recovery=value.sourceMerge;}});
 t.after(()=>draft.close());
 function Field(){const [value,change]=useAuthoredDraft(key,'');return React.createElement('input',{value,onChange:event=>change(event.target.value)});}
 function Screen(){return React.createElement(AuthoredDraftScope,{presentation:s.owner},React.createElement(Field));}
 await h.mount(Screen);await h.act(()=>h.root.findByType('input').props.onChange({target:{value:'New user text'}}));release();await draft.flush();
 assert.equal(restores,0);assert.equal(h.root.findByType('input').props.value,'New user text');assert.deepEqual(recovery,{operation_uuid:'retained-operation'});
 const saved=await s.store.load(projectId),restored=createWorkspacePresentationSessions();restored.restore(saved.value);assert.equal(restored.readDraft(shellRoute,key),'New user text');assert.equal(saved.value.route.key,'current');
 const after=s.owner.authoredIntent();s.owner.readDraft(shellRoute,key);s.owner.restore(s.owner.checkpoint(route));assert.equal(s.owner.authoredIntent(),after);
});
