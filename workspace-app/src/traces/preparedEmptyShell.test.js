import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {traceDisplaySegments} from './ui/traceGeometry.js';
import {traceSampleStatistics} from './traceStatistics.js';
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const context={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
const epoch={epoch_uuid:uid(6),source_sha256:'b'.repeat(64),cell_label:'Cell',streams:[{kind:'responses',uuid:uid(7),sample_count:10000,sample_rate:10000,units:'pA'}]};
async function harness({sample=false,generic=false,detailOnly=false,trailingOnly=false}={}){
 const names=['window','document','getComputedStyle','ResizeObserver','requestAnimationFrame','cancelAnimationFrame'],previous=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
 globalThis.window={devicePixelRatio:1,addEventListener(){},removeEventListener(){},matchMedia(){return {addEventListener(){},removeEventListener(){}};}};
 globalThis.document={activeElement:null};globalThis.getComputedStyle=()=>({getPropertyValue:name=>name==='--plot-trace'?'trace':name});
 globalThis.ResizeObserver=class{observe(){}disconnect(){}};globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
 const requests=[],bases=[],overlays=[],captures=[],releases=[],strokes=[],clears=[];let renderer,currentEpoch=null,currentContext=context,width=603;
 const values=Float64Array.from({length:10000},(_,i)=>Math.sin(i/13));
 const port={identity:'empty-shell',request:(path,{signal})=>new Promise((resolve,reject)=>requests.push({path,signal,resolve,reject,epoch:currentEpoch,context:currentContext}))};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,plugins:detailOnly||trailingOnly?[{name:'viewer-detail-boundary',enforce:'pre',resolveId(id){if(id.endsWith('/EpochBrowserLayout.jsx'))return '\0viewer-detail-only';if(id.endsWith('/RetainedTreePresentation.jsx'))return '\0viewer-tree-stub';},load(id){if(id==='\0viewer-tree-stub')return trailingOnly?'export default function Tree(props){return props.active?props.tree.trailingPane:null;}':'export default function Tree(){return null;}';if(id==='\0viewer-detail-only')return `import React from 'react';export default function Layout(props){return React.createElement('section',null,props.detail);}`;}}]:[],server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:GenericTrace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {default:Viewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx'),{WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 function nodeMock(node){
  if(node.type!=='canvas')return {textContent:'',focus(){}};
  const captured=new Set();const canvas={getBoundingClientRect:()=>({width,height:300,left:0,top:0}),setPointerCapture(id){captured.add(id);captures.push(id);},hasPointerCapture:id=>captured.has(id),releasePointerCapture(id){captured.delete(id);releases.push(id);}};let path=[];
  const ctx=new Proxy({canvas,clearRect(){clears.push(canvas);},beginPath(){path=[];},moveTo(x,y){path.push([x,y]);},lineTo(x,y){path.push([x,y]);},stroke(){if(node.props.className==='tv-base'&&this.strokeStyle==='trace')strokes.push({canvas,path});}},{get:(o,k)=>k in o?o[k]:()=>{}});
  canvas.getContext=()=>ctx;if(node.props.className==='tv-base')bases.push(canvas);else overlays.push(canvas);return canvas;
 }
 return {requests,bases,overlays,captures,releases,strokes,clears,get root(){return renderer.root;},setWidth(value){width=value;},
  async render(record=null,captured=context,overrides={}){currentEpoch=record;currentContext=captured;await act(async()=>{
   const props={epoch:record,traceEpoch:record,traceReadContext:captured,readContext:{root:`/protocols/${uid(4)}/workbench/candidates/${uid(5)}`},traceRevision:1,
    resource:{data:record,loading:!record},layout:{treeOpen:false,metadataOpen:false,sizes:{columns:'1fr'},onResize(){}},treePane:{},
    tracePreference:sample?{kind:'sample',start:0,count:200}:{kind:'whole'},onTracePreference(){if(sample)throw Error('Clearing must not change global preference');},tags:record?React.createElement('button',{'aria-label':'current mutation','data-source':record.source_sha256},'Tag'):null,...overrides};
   const node=React.createElement(WorkspaceRequestProvider,{port},generic?React.createElement(GenericTrace,{epoch:record,readContext:captured,viewPreference:props.tracePreference,onViewPreference(){throw Error('Clearing must not change global preference');}}):React.createElement(Viewer,props));if(renderer)renderer.update(node);else renderer=TestRenderer.create(node,{createNodeMock:nodeMock});
  });},
  async finish(index){const request=requests[index],physicalWidth=Number(new URL(request.path,'http://fixture').searchParams.get('physical_width')),indices=Uint32Array.from(traceDisplaySegments(values,physicalWidth)[0]);await act(async()=>request.resolve({representation:'m4_geometry',algorithm:'first-last-extrema-v1',epoch_uuid:request.epoch.epoch_uuid,stream_uuid:request.epoch.streams[0].uuid,source_sha256:request.epoch.source_sha256,sample_rate:10000,units:'pA',read_context:request.context,raw_start:0,raw_count:10000,total_samples:10000,physical_width:physicalWidth,point_count:indices.length,indices,point_values:Float64Array.from(indices,i=>values[i]),statistics:traceSampleStatistics(values)}));},
  async close(){await act(async()=>renderer?.unmount());await server.close();for(const name of names){if(previous[name]===undefined)delete globalThis[name];else globalThis[name]=previous[name];}}
 };
}
function emptyBody(h){return h.root.find(node=>node.type==='div'&&String(node.props.className).includes('prepared-trace-empty'));}
function hasInertAncestor(node){for(let parent=node.parent;parent;parent=parent.parent)if(parent.props?.inert===true&&parent.props['aria-hidden']===true)return true;return false;}

test('empty prepared shell makes no read, hides all controls, and retains its canvas through first focus and clear',async()=>{
 const h=await harness();try{
  await h.render();assert.equal(h.requests.length,0);assert.equal(h.bases.length,1);assert.equal(emptyBody(h).props.inert,true);assert.equal(emptyBody(h).props['aria-hidden'],true);
  const controls=h.root.findAll(node=>typeof node.type==='string'&&(['button','input','select'].includes(node.type)||node.props.tabIndex>=0));assert(controls.length>0);for(const node of controls.filter(node=>node.type!=='div'||node.props.className?.startsWith('tv-')))assert(hasInertAncestor(node));
  h.setWidth(703.25);await h.render(epoch);assert.equal(h.requests.length,1);assert.equal(h.bases.length,1);assert.equal(Number(new URL(h.requests[0].path,'http://fixture').searchParams.get('physical_width')),600.25,'first focused commit measures its current width, not empty-shell width');
  await h.finish(0);assert(h.strokes.length);assert.equal(h.root.findAll(node=>node.type==='div'&&String(node.props.className).includes('prepared-trace-empty')).length,0);
  const clears=h.clears.length;await h.render();assert.equal(h.bases.length,1);assert(h.requests[0].signal.aborted);assert(h.clears.length>clears,'clearing focus clears old painted samples');assert.equal(h.requests.length,1);assert.equal(h.root.findAllByProps({'aria-label':'current mutation'}).length,0);assert.equal(emptyBody(h).props.inert,true);
 }finally{await h.close();}
});

test('new source and publication retire late responses while retaining only the empty presentation node',async()=>{
 const h=await harness();try{
  await h.render();await h.render(epoch);const next={...epoch,source_sha256:'c'.repeat(64)},publication={...context,token:uid(8),publication_revision:uid(9)};
  await h.render(next,publication);assert(h.requests[0].signal.aborted);assert.equal(h.bases.length,1);assert.equal(h.requests.length,2);
  await h.finish(0);assert.equal(h.strokes.length,0);await h.finish(1);assert(h.strokes.length);assert.equal(h.root.findByProps({'aria-label':'current mutation'}).props['data-source'],next.source_sha256);
  await h.render(null,publication);const painted=h.strokes.length;await h.render(next,publication);assert.equal(h.requests.length,3,'reselect demands new samples; empty shell is not a sample cache');
  await h.render(null,publication);assert(h.requests[2].signal.aborted);await h.finish(2);assert.equal(h.strokes.length,painted,'retired reply cannot paint hidden empty shell');assert.equal(h.bases.length,1);
 }finally{await h.close();}
});

test('focused prepared trace errors keep the ordinary retry UI and null epoch never exposes it',async()=>{
 const h=await harness();try{
  await h.render(epoch);await act(async()=>h.requests[0].reject(Error('fixture trace failure')));assert(h.root.findAllByProps({role:'alert'}).some(node=>node.children.includes('fixture trace failure')));
  assert(h.root.findAllByType('button').some(node=>node.props.children==='Retry trace'));
  await h.render();assert.equal(h.root.findAllByProps({role:'alert'}).length,0);assert.equal(emptyBody(h).props['aria-hidden'],true);
 }finally{await h.close();}
});

test('prepared capability arriving after the empty view mounts creates one inert shell without requesting samples',async()=>{
 const h=await harness();try{
  await h.render(null,null);assert.equal(h.bases.length,0);assert.equal(h.requests.length,0);
  await h.render(null,context);assert.equal(h.bases.length,1);assert.equal(h.requests.length,0);assert.equal(emptyBody(h).props.inert,true);
  await h.render(epoch,context);assert.equal(h.bases.length,1);assert.equal(h.requests.length,1);await h.finish(0);assert(h.strokes.length);
 }finally{await h.close();}
});

for(const generic of [false,true])test(generic?'generic Trace opt-out preserves its existing Pan interaction through null epoch':'prepared empty shell resets Pan to baseline Zoom while preserving Sample preference',async()=>{
 const h=await harness({sample:true,generic});try{
  const finish=async i=>{const r=h.requests[i];await act(async()=>r.resolve({epoch_uuid:epoch.epoch_uuid,stream_uuid:epoch.streams[0].uuid,start:0,count:200,total_samples:10000,sample_rate:10000,units:'pA',source_sha256:epoch.source_sha256,decimated:false,read_context:context,values:Array.from({length:200},(_,i)=>Math.sin(i/13))}));};
  const button=text=>h.root.findAllByType('button').find(n=>n.children.includes(text));
  await h.render(epoch);await finish(0);assert.equal(button(' Pan').props.disabled,false);await act(async()=>button(' Pan').props.onClick());assert.equal(button(' Pan').props['aria-pressed'],true);
  await h.render(null);await h.render(epoch);await finish(1);assert.equal(button(' Zoom').props['aria-pressed'],!generic);assert.equal(button(' Pan').props['aria-pressed'],generic);assert.equal(button('Sample').props['aria-pressed'],true);assert.equal(h.root.findByProps({'aria-label':'Start sample'}).props.value,'0');assert.equal(h.root.findByProps({'aria-label':'Sample count'}).props.value,'200');
 }finally{await h.close();}
});

test('prepared empty shell releases a held pointer capture and rejects its retired gesture and reply',async()=>{
 const h=await harness();try{
  await h.render(epoch);await h.finish(0);
  const overlay=h.root.findByProps({className:'tv-overlay'}),canvas=h.overlays[0];
  await act(async()=>overlay.props.onPointerDown({button:0,pointerId:7,clientX:150,clientY:80,currentTarget:canvas}));assert(canvas.hasPointerCapture(7));
  await act(async()=>overlay.props.onPointerDown({button:0,pointerId:8,clientX:180,clientY:90,currentTarget:canvas}));assert(canvas.hasPointerCapture(8));const readsAfterPointerDown=h.requests.length;
  await h.render(null);assert.equal(canvas.hasPointerCapture(7),false);assert.equal(canvas.hasPointerCapture(8),false);assert.deepEqual(h.releases,[7,8]);const painted=h.strokes.length;
  await act(async()=>overlay.props.onPointerUp({pointerId:7,clientX:400,clientY:180,currentTarget:canvas}));assert.equal(h.requests.length,readsAfterPointerDown);assert.equal(h.strokes.length,painted);
  await h.render(epoch);assert.equal(h.requests.length,readsAfterPointerDown+1);await h.render(null);await h.finish(readsAfterPointerDown);assert.equal(h.strokes.length,painted);assert.deepEqual(h.releases,[7,8]);
 }finally{await h.close();}
});

test('actual prepared Viewer keeps its loading placeholder when metadata settles without a trace epoch',async()=>{
 const h=await harness();try{
  await h.render(null,context,{resource:{data:null,loading:false},traceEpoch:null});assert.equal(h.requests.length,0);
  const detail=h.root.findByProps({className:'inspection-detail'});assert(detail.findAll(node=>node.type==='div'&&node.props['aria-busy']===true).length>0);assert.equal(detail.findAll(node=>node.children?.includes('Choose an epoch')).length,0);
 }finally{await h.close();}
});
test('actual Viewer preserves SelectionOverview precedence with prepared capability and no scientific read context',async()=>{
 const h=await harness();try{
  await h.render(epoch,context,{readContext:null,targets:[uid(20),uid(21)],resource:{data:epoch,loading:false}});assert.equal(h.requests.length,0);assert.equal(h.bases.length,0);assert.equal(h.root.findByProps({className:'selection-overview'}).findByType('h2').children.join(''),'2 epochs');
 }finally{await h.close();}
});


test('Edit Tree display heading survives tag authority renewal with a retained prepared trace epoch',async()=>{
 const h=await harness({detailOnly:true});try{
  const shown={...epoch,epoch_number:2,start_time:'2026-01-01T00:00:02',cell_label:'Retained cell'};
  const view={designMode:true,columnTree:{selected:shown.epoch_uuid,actionsDisabled:true}};
  await h.render(shown,context,view);
  // A committed tag retires scientific metadata authority while the immutable
  // display capability still owns this exact focused recording.
  await h.render(null,context,{...view,traceEpoch:shown,resource:{data:null,loading:true,scope:'renewing-tags'}});
  assert.equal(h.root.findAllByProps({'aria-label':'current mutation'}).length,0);
  await h.render(null,context,{...view,designMode:false,traceEpoch:shown,
   resource:{data:null,loading:true,scope:'renewing-tags'},
   tags:React.createElement('button',{'aria-label':'current mutation'},'Stale mutation')});
  for(const control of h.root.findAllByProps({'aria-label':'current mutation'}))assert(hasInertAncestor(control),'Retained display must not enable stale curation');
  await h.render(shown,context,view);
  await h.render(shown,context,{...view,designMode:false});
  const fresh=h.root.findByProps({'aria-label':'current mutation'});
  assert.equal(hasInertAncestor(fresh),false);assert.notEqual(fresh.props.disabled,true);
 }finally{await h.close();}
});


test('shared Viewer keeps the frozen raw-preview section inert through authority refresh without new trace demand',async()=>{
 const h=await harness({trailingOnly:true});try{
  const readContext={root:`/protocols/${uid(4)}/workbench/candidates/${uid(5)}`,cohort_key:'same-cohort',actor:'author',candidate_scope_revision:'scope-1'};
  const tree={projectId:uid(2),protocolId:uid(4),readContext,selected:epoch.epoch_uuid,actionsDisabled:false,splits:'date,cell'};
  await h.render(epoch,context,{designMode:true,columnTree:tree,readContext});
  const pane=h.root.findByProps({className:'tree-trace-pane'}),reads=h.requests.length;
  assert.equal(pane.type,'section');
  await h.render(null,context,{designMode:true,columnTree:{...tree,actionsDisabled:true},readContext,traceEpoch:epoch,resource:{data:null,loading:true}});
  assert.equal(h.root.findByProps({className:'tree-trace-pane'}),pane);
  assert.equal(pane.props.inert,true);assert.equal(pane.props['aria-hidden'],true);
  assert.equal(h.requests.length,reads,'Retaining geometry must not remount the trace or demand another recording');
  await h.render(epoch,context,{designMode:true,columnTree:tree,readContext});
  assert.equal(h.root.findByProps({className:'tree-trace-pane'}),pane);assert.notEqual(pane.props.inert,true);assert.equal(h.requests.length,reads);
  await h.render(epoch,undefined,{designMode:true,columnTree:{...tree,readContext:null,actionsDisabled:true},readContext:null,traceReadContext:undefined});
  assert.equal(h.root.findAllByProps({className:'tree-trace-pane'}).length,0,'Live blocked preview retains its previous hide behavior');
 }finally{await h.close();}
});
