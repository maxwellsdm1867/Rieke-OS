import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';
import {traceDisplaySegments} from '../traces/ui/traceGeometry.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const pendingCapability={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
const root=`/protocols/${uid(4)}/workbench/candidates/${uid(5)}`;
const values=Float64Array.from({length:10000},(_,i)=>Math.sin(i/13));
const stream={kind:'responses',uuid:uid(7),sample_count:values.length,sample_rate:10000,units:'pA'};
const rows=[6,8].map(n=>({epoch_uuid:uid(n),cell_uuid:uid(20),date:'2026-10-15',cell_label:'Cell',epoch_number:n===6?1:2,source_sha256:'b'.repeat(64),streams:[stream],annotations:{epoch_uuid:uid(n),cell_uuid:uid(20),epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}}));
function geometryBytes(url,capability){
 const width=Number(url.searchParams.get('physical_width')),indices=traceDisplaySegments(values,width)[0];
 const header={representation:'m4_geometry',algorithm:'first-last-extrema-v1',read_context:capability,epoch_uuid:url.pathname.split('/').at(-2),stream_uuid:stream.uuid,source_sha256:'b'.repeat(64),sample_rate:stream.sample_rate,units:stream.units,total_samples:values.length,raw_start:0,raw_count:values.length,physical_width:width,point_count:indices.length,statistics:{min:Math.min(...values),max:Math.max(...values),finiteCount:values.length,missingCount:0}};
 const json=new TextEncoder().encode(JSON.stringify(header)),indexStart=Math.ceil((8+json.length)/8)*8,valueStart=Math.ceil((indexStart+indices.length*4)/8)*8,buffer=new ArrayBuffer(valueStart+indices.length*8),view=new DataView(buffer),bytes=new Uint8Array(buffer);
 bytes.set([68,84,77,49]);view.setUint32(4,json.length,true);bytes.set(json,8);indices.forEach((index,i)=>{view.setUint32(indexStart+i*4,index,true);view.setFloat64(valueStart+i*8,values[index],true);});return buffer;
}
async function fixture(){
 const h=await createWorkflowHarness({total:2,liveMetadata:false,portals:true});
 const names=['ResizeObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const old=Object.fromEntries(names.map(n=>[n,globalThis[n]]));
 Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,ResizeObserver:class{observe(){}disconnect(){}},getComputedStyle:()=>({getPropertyValue:()=>''}),requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{}});
 const state={manifests:[],traceRequests:[],draws:0,selected:new Map(),capabilities:new Map([[pendingCapability.token,pendingCapability]])};
 let points=0;const ctx=new Proxy({beginPath(){points=0;},lineTo(){points++;},stroke(){if(points>10)state.draws++;}},{get:(object,key)=>key in object?object[key]:()=>{}});
 const canvas={getBoundingClientRect:()=>({width:603,height:300}),getContext:()=>ctx};
 h.fixture.createNodeMock=element=>element.type==='canvas'?canvas:undefined;
 h.fixture.traceComponent=await h.component('TraceViewer');
 const cells=[{cell_uuid:uid(20),date:'2026-10-15',label:'Cell',epochs:2}];
 function page(url){
  const selected=state.selected.get(url.searchParams.get('selection_token'));
  const epochs=selected?rows.filter(row=>selected.ids.includes(row.epoch_uuid)):rows;
  return {epochs,cells:[{...cells[0],epochs:epochs.length}],total:epochs.length,offset:0,limit:60,query_revision:url.searchParams.get('candidate_scope_revision'),candidate_scope_revision:url.searchParams.get('candidate_scope_revision'),expected_binding_version:2,trace_read_context:selected?.capability||pendingCapability};
 }
 h.fixture.respond=(url,options,fallback)=>{
  if(url.pathname===`/api${root}/selection-manifest`){
   const body=JSON.parse(options.body);
   return new Promise(resolve=>state.manifests.push({body,resolve:()=>{
    const membership=createHash('sha256').update(JSON.stringify(body.epoch_uuids)).digest('hex');
    const capability={...pendingCapability,token:body.upload_uuid,view_kind:'workbench_selected',membership_sha256:membership};
    state.selected.set(body.upload_uuid,{ids:body.epoch_uuids,capability});state.capabilities.set(capability.token,capability);
    resolve({selection_token:body.upload_uuid,count:body.epoch_uuids.length,total:body.total,complete:true,candidate_scope_revision:body.candidate_scope_revision,query_revision:body.candidate_scope_revision,expected_binding_version:2,selection_sha256:membership});
   }}));
  }
  if(url.pathname===`/api${root}/epochs`)return page(url);
  return fallback();
 };
 const apiFetch=globalThis.fetch;
 globalThis.fetch=async(input,options={})=>{
  const url=new URL(input,'http://fixture');
  if(url.pathname.includes('/trace-views/')&&url.pathname.endsWith('/display')){
   state.traceRequests.push({url:url.pathname+url.search,signal:options.signal});
   const capability=state.capabilities.get(url.pathname.split('/')[3]);assert.ok(capability,'trace capability must be minted by fixture');
   return new Response(geometryBytes(url,capability),{status:200,headers:{'Content-Type':'application/vnd.disco.trace-m4le.v1'}});
  }
  return apiFetch(input,options);
 };
 const Inspector=await h.component('Inspector');
 let props={projectId:uid(2),protocol:{definition:{protocol_uuid:uid(4)},query_revision:'scope-A',expected_binding_version:2,cells},readContext:{root,candidate_scope_revision:'scope-A',cohort_key:'cohort',actor:'author',expected_binding_version:2,selection_manifests:true},traceReadContext:pendingCapability,filters:{},revision:0,structureRevision:0,initialEpochUuid:rows[1].epoch_uuid,draftSelection:{selected:rows.map(r=>r.epoch_uuid),disabled:false},draftSelectionTarget:{}};
 const tools=()=>h.root.findAll(node=>typeof node.props.onViewSelected==='function')[0].props;
 try{await h.mount(Inspector,props);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===rows[1].epoch_uuid&&state.draws>0);}catch(error){await h.close();for(const n of names){if(old[n]===undefined)delete globalThis[n];else globalThis[n]=old[n];}throw error;}
 return {h,state,tools,async toggle(){assert.equal(tools().disabled,false);await h.act(()=>tools().onViewSelected());},async release(index){await h.act(()=>state.manifests[index].resolve());},async render(change){props={...props,...change};await h.render(Inspector,props);},get props(){return props;},async focus(){await h.act(()=>h.viewer.treePane.listProps.onFocus(rows[1].epoch_uuid,rows[1]));},async close(){await h.close();for(const n of names){if(old[n]===undefined)delete globalThis[n];else globalThis[n]=old[n];}}};
}

test('initial selected intent withholds parent trace until its own manifest/page, including membership-change reentry',async()=>{
 const f=await fixture(),{h,state}=f;
 try{
  const before=state.traceRequests.length;await f.toggle();await h.waitFor(()=>state.manifests.length===1);
  assert.equal(h.viewer.traceReadContext,null);assert.equal(h.viewer.traceEpoch,null);assert.equal(h.viewer.treePane.listProps.disabled,true);assert.equal(state.traceRequests.length,before,'actual shared TraceViewer issues no parent or fallback request during initial intent');
  await f.release(0);await h.waitFor(()=>h.viewer.traceReadContext?.view_kind==='workbench_selected'&&!h.viewer.treePane.listProps.disabled);
  const draws=state.draws;await f.focus();await h.waitFor(()=>state.draws>draws);
  assert.ok(state.traceRequests.at(-1).url.includes(state.manifests[0].body.upload_uuid));
  await f.render({draftSelection:{selected:[rows[1].epoch_uuid],disabled:false}});
  await h.waitFor(()=>!f.tools().viewSelected&&!f.tools().disabled);
  const nextBefore=state.traceRequests.length;await f.toggle();await h.waitFor(()=>state.manifests.length===2);
  assert.deepEqual(state.manifests[1].body.epoch_uuids,[rows[1].epoch_uuid]);assert.equal(h.viewer.traceReadContext,null);assert.equal(h.viewer.traceEpoch,null);assert.equal(state.traceRequests.length,nextBefore);
  await f.release(1);await h.waitFor(()=>h.viewer.traceReadContext?.token===state.manifests[1].body.upload_uuid&&!h.viewer.treePane.listProps.disabled);
  const nextDraws=state.draws;await f.focus();await h.waitFor(()=>state.draws>nextDraws);
  assert.equal(h.viewer.traceEpoch.epoch_uuid,rows[1].epoch_uuid);assert.ok(state.traceRequests.at(-1).url.includes(state.manifests[1].body.upload_uuid));
 }finally{await f.close();}
});

test('same selected view renewal retains its own inert trace capability while manifest authority is pending',async()=>{
 const f=await fixture(),{h,state}=f;
 try{
  await f.toggle();await h.waitFor(()=>state.manifests.length===1);await f.release(0);
  await h.waitFor(()=>h.viewer.traceReadContext?.view_kind==='workbench_selected'&&!h.viewer.treePane.listProps.disabled);await f.focus();await h.waitFor(()=>h.viewer.traceEpoch?.epoch_uuid===rows[1].epoch_uuid);
  const capability=h.viewer.traceReadContext,row=h.viewer.traceEpoch,before=state.traceRequests.length;
  await f.render({readContext:{...f.props.readContext,candidate_scope_revision:'scope-B'}});await h.waitFor(()=>state.manifests.length===2);
  assert.equal(h.viewer.traceReadContext,capability);assert.equal(h.viewer.traceEpoch,row);assert.equal(h.viewer.treePane.listProps.disabled,true);assert.equal(h.viewer.inclusion.disabled,true);assert.equal(state.traceRequests.length,before);
  await f.release(1);await h.waitFor(()=>h.viewer.traceReadContext?.token===state.manifests[1].body.upload_uuid);
  assert.equal(h.viewer.traceReadContext.view_kind,'workbench_selected');
 }finally{await f.close();}
});
