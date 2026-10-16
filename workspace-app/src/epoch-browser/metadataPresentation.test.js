import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';
const data={fields:[{id:'cell/type',category:'Cell',label:'Recorded type'}]};
const epoch={epoch_uuid:'epoch-a',cell_uuid:'cell-a',date:'2026-01-01',cell_label:'A'};
async function harness(){
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:Panel}=await server.ssrLoadModule('/src/epoch-browser/ui/MetadataPanel.jsx');
 const prior=globalThis.ResizeObserver,observers=[];let height=329.625,mounts=0,unmounts=0,renderer;
 globalThis.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}};
 function Tags(){useEffect(()=>{mounts++;return()=>unmounts++;},[]);return React.createElement('section',{className:'annotation-tags'},React.createElement('button',null,'Save authoritative tag'));}
 const base={epoch,presentation:{key:'cohort/focus/structure-A',blocked:false},catalog:{data,loading:false},loadingPolicy:{live:false,values:{data:null},canLoad:true},tags:React.createElement(Tags),onClose(){}};
 return {base,get root(){return renderer.root;},get mounts(){return mounts;},get unmounts(){return unmounts;},
  async render(p={}){await act(async()=>{const element=React.createElement(Panel,{...base,...p});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element,{createNodeMock:el=>el.type==='aside'?{querySelector:()=>({getBoundingClientRect:()=>({height})})}:null});});},
  resize(value){height=value;for(const o of observers)if(!o.disconnected)o.callback();},
  async close(){await act(async()=>renderer?.unmount());await server.close();if(prior===undefined)delete globalThis.ResizeObserver;else globalThis.ResizeObserver=prior;},
 };
}
const groups=h=>h.root.findAllByProps({className:'metadata-field-group'}).length;
const slots=h=>h.root.findAllByProps({className:'metadata-tag-slot'});
test('shared sidebar reserves measured tag geometry, removes tag component, and retains only inert catalog through pause/error',async()=>{
 const h=await harness();try{
  await h.render();assert.equal(groups(h),1);assert.equal(slots(h).length,0);assert.equal(h.mounts,1);
  await h.render({epoch:null,tags:null,presentation:{...h.base.presentation,blocked:true},catalog:{data:null,loading:true}});
  assert.equal(slots(h)[0].props.style.height,329.625);assert.equal(slots(h)[0].props.inert,true);assert.equal(h.unmounts,1);
  assert.equal(h.root.findAllByType('button').some(n=>n.children.includes('Save authoritative tag')),false);
  assert.equal(groups(h),1);assert.equal(h.root.findByProps({'aria-label':'Available metadata fields'}).props.inert,true);
  await h.render({epoch:null,tags:null,presentation:{...h.base.presentation,blocked:true},catalog:{data:null,error:'renewal failed'}});
  assert.equal(slots(h)[0].props.style.height,329.625);assert.equal(groups(h),1);assert.equal(h.mounts,1);
  await h.render();assert.equal(slots(h).length,0);assert.equal(h.mounts,2);assert.equal(h.root.findByProps({'aria-label':'Available metadata fields'}).props.inert,false);
  h.resize(287.25);await h.render({epoch:null,tags:null,presentation:{...h.base.presentation,blocked:true}});
  assert.equal(slots(h)[0].props.style.height,287.25);
 }finally{await h.close();}
});
test('fresh empty catalog retires old display; loading empty retains it without reactivating copy',async()=>{
 const h=await harness();const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator');let copies=0;
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async()=>copies++}}});
 try{
  await h.render();await act(()=>h.root.findByProps({'aria-label':'Search metadata fields'}).props.onChange({target:{value:'type'}}));
  await h.render({catalog:{data:{fields:[]},loading:true}});assert.equal(groups(h),1);
  await act(()=>h.root.findByProps({'aria-label':'Copy field ID cell/type'}).props.onClick());assert.equal(copies,0);
  await h.render({catalog:{data:{fields:[]},loading:false}});assert.equal(groups(h),0);
  await h.render({catalog:{data:null,loading:true}});assert.equal(groups(h),0);
 }finally{if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor);else delete globalThis.navigator;await h.close();}
});
test('changed semantic keys discard display immediately and never resurrect A after B',async()=>{
 for(const other of ['actor','project','cohort','selection-view','filter','focus','cell','structure',null]){
  const h=await harness();try{
   await h.render();await h.render({epoch:null,tags:null,catalog:{data:null,loading:true},presentation:other?{key:other,blocked:true}:null});
   assert.equal(groups(h),0,other);assert.equal(slots(h).length,0,other);
   await h.render({epoch:null,tags:null,catalog:{data:null,loading:true},presentation:{...h.base.presentation,blocked:true}});
   assert.equal(groups(h),0);assert.equal(slots(h).length,0);
  }finally{await h.close();}
 }
});
test('Inspector supplies frozen identity independent of read revision and excludes live/annotation scopes',async()=>{
 const h=await createWorkflowHarness({total:2,liveMetadata:false}),Inspector=await h.component('Inspector');
 const root='/protocols/protocol/workbench/candidates/candidate';
 const props={projectId:'project',protocol:{definition:{protocol_uuid:'protocol'}},readContext:{root,candidate_scope_revision:'r1',cohort_key:'cohort',actor:'actor'},filters:{},revision:0,structureRevision:0,initialEpochUuid:'epoch-1'};
 try{
  await h.mount(Inspector,props);const key=h.viewer.metadata.presentation?.key;assert.ok(key);
  await h.render(Inspector,{...props,revision:1,readPaused:true});assert.equal(h.viewer.metadata.presentation.key,key);assert.equal(h.viewer.metadata.presentation.blocked,true);
  for(const changed of [{structureRevision:1},{projectId:'other'},{readContext:{...props.readContext,actor:'other'}},{readContext:{...props.readContext,cohort_key:'other'}}]){
   await h.render(Inspector,{...props,...changed,readPaused:true});assert.notEqual(h.viewer.metadata.presentation?.key,key);
  }
  await h.render(Inspector,{...props,readPaused:true,readContext:{...props.readContext,selection_token:'token'}});assert.equal(h.viewer.metadata.presentation,null);
  await h.render(Inspector,{...props,filters:{tags:['dependent']}});assert.equal(h.viewer.metadata.presentation,null);
  await h.render(Inspector,{...props,readPaused:true});
  await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-0'));
  assert.notEqual(h.viewer.metadata.presentation?.key,key,'focused UUID changes the actual Inspector display boundary');
  await h.render(Inspector,{...props,readContext:null});assert.equal(h.viewer.metadata.presentation,null);
 }finally{await h.close();}
});

test('catalog failure keeps current retry outside inert fields and blocks retry only while authority is blocked',async()=>{
 const h=await harness();let retries=0;
 try{
  await h.render();const catalog={data:null,error:'current failure',reload:()=>retries++};
  await h.render({catalog});assert.equal(groups(h),1);
  let retry=h.root.findAllByType('button').find(n=>n.children.includes('Retry fields'));
  assert.equal(retry.props.disabled,false);assert.equal(retry.parent.props.role,'alert');assert.equal(retry.parent.props.className,'metadata-catalog-notice');assert.equal(retry.parent.parent.type,'aside','current error lives outside retained scroll content');
  await act(()=>retry.props.onClick());assert.equal(retries,1);
  await h.render({catalog,presentation:{...h.base.presentation,blocked:true},epoch:null,tags:null});
  retry=h.root.findAllByType('button').find(n=>n.children.includes('Retry fields'));assert.equal(retry.props.disabled,true);
  await h.render({catalog:{data:null,loading:true}});assert.equal(groups(h),1);
  const announcement=h.root.findByProps({className:'metadata-catalog-announcement'});assert.equal(announcement.parent.type,'aside');assert.equal(announcement.props.role,'status');
  assert.equal(h.root.findByProps({className:'metadata-panel-scroll'}).findAllByProps({role:'status'}).length,0,'routine loading adds no scroll-flow status');
  await h.render({catalog:{data:{fields:[{id:'new',category:'Fresh'}]},loading:false}});
  assert.equal(h.root.findAllByType('button').some(n=>n.children.includes('Retry fields')),false);
  assert.equal(h.root.findByProps({'aria-label':'Available metadata fields'}).props.inert,false);
 }finally{await h.close();}
});

test('Live metadata and loaded value mode retire field-only snapshots',async()=>{
 for(const policy of [{live:true,values:{data:null}},{live:false,values:{data:epoch}}]){
  const h=await harness();try{
   await h.render();await h.render({loadingPolicy:policy,catalog:{data:null,loading:true},tags:null,epoch:null});
   assert.equal(slots(h).length,0);assert.equal(groups(h),0);
   await h.render({catalog:{data:null,loading:true},tags:null,epoch:null,presentation:{...h.base.presentation,blocked:true}});
   assert.equal(slots(h).length,0);assert.equal(groups(h),0);
  }finally{await h.close();}
 }
});

test('Inspector selected-view presentation survives only renewal of the same explicit selection view',async()=>{
 const h=await createWorkflowHarness({total:2,liveMetadata:false}),Inspector=await h.component('Inspector');
 const context={root:'/protocols/protocol/workbench/candidates/candidate',candidate_scope_revision:'r1',cohort_key:'cohort',actor:'actor',selection_token:'token',selection_view_key:'selected-A'};
 const props={projectId:'project',protocol:{definition:{protocol_uuid:'protocol'}},readContext:context,filters:{},revision:0,structureRevision:0,initialEpochUuid:'epoch-1',readPaused:true};
 try{
  await h.mount(Inspector,props);const key=h.viewer.metadata.presentation?.key;assert.ok(key);
  await h.render(Inspector,{...props,readContext:{...context,selection_token:'renewed'}});assert.equal(h.viewer.metadata.presentation?.key,key);
  await h.render(Inspector,{...props,readContext:{...context,selection_view_key:'selected-B'}});assert.notEqual(h.viewer.metadata.presentation?.key,key);
 }finally{await h.close();}
});
