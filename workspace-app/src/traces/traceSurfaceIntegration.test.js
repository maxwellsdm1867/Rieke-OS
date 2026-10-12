import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useState} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {JSDOM} from 'jsdom';
const text=n=>typeof n==='string'?n:Array.isArray(n)?n.map(text).join(''):n?.children?text(n.children):'';
const epoch={epoch_uuid:'epoch-1',cell_uuid:'cell-1',date:'2026-10-01',streams:[{uuid:'stream-1',kind:'responses',device:'Amp1',sample_count:67500,sample_rate:10000,units:'pA'}],curation:{included:true,tags:[]}};
const cells=[{cell_uuid:'cell-1',epochs:1,label:'Cell one',date:'2026-10-01'}];
const protocol={definition:{protocol_uuid:'p'},query_revision:'scope',expected_binding_version:1,cells};
async function harness({epochCount=1}={}){
 const epochs=Array.from({length:epochCount},(_,index)=>({...epoch,epoch_uuid:`epoch-${index+1}`,streams:epoch.streams.map(stream=>({...stream,uuid:`stream-${index+1}`}))}));
 // Match the bounded /explore/epochs projection; full detail is a separate read.
 const predicateKeys=['epoch_uuid','cell_uuid','cell_label','cell_type','date','start_time','block_uuid','epoch_number','protocol_name','duration_seconds','streams'];
 const predicateRows=epochs.map(row=>Object.fromEntries(predicateKeys.map(key=>[key,row[key]??null])));
 const dom=new JSDOM('<!doctype html><body></body>',{url:'http://localhost/'}),calls=[];
 let previewSerial=0;
 const preferences={format:'rieke-project-preferences',version:1,project_uuid:'project',state:{recent_searches:[],protocol_shortcuts:{}},revisions:{recent_searches:0,protocol_shortcuts:0}};
 const context={candidate_revision_uuid:'candidate',candidate_scope_revision:'scope',candidate_recipe_sha256:'recipe',expected_binding_version:1,protocol,draft:{draft_version:1,selection_mode:'selected',decisions:[],decisions_total:0,decisions_truncated:false},counts:{pending_epochs:1,pending_cells:1}};
 const globals={window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,ResizeObserver:class{observe(){}disconnect(){}},getComputedStyle:()=>({getPropertyValue:()=> '#555'}),requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},fetch:async(input,options={})=>{
  const url=new URL(input,'http://localhost'),path=url.pathname.replace(/^\/api/,'');calls.push({path,query:url.searchParams,method:options.method||'GET'});let value;
  if(path.endsWith('/trace')){const start=+url.searchParams.get('start'),count=+url.searchParams.get('count');value={epoch_uuid:path.split('/').at(-2),stream_uuid:url.searchParams.get('stream_uuid'),start,count,total_samples:67500,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array(count).fill(1)};}
  else if(path.endsWith('/context'))value=context;
  else if(path.endsWith('/epochs'))value={epochs:path==='/explore/epochs'?predicateRows:epochs,cells,total:epochCount,offset:0,limit:60,query_revision:'scope',expected_binding_version:1,revision:'search-two'};
  else if(path.includes('/epochs/'))value=epochs.find(row=>row.epoch_uuid===path.split('/').at(-1));
  else if(path==='/metadata/fields'||path==='/explore/field-registry')value={fields:[]};
  else if(path==='/search-presets'||path==='/explore/revisions')value={items:[],total:0};
  else if(path==='/project-preferences'){if(options.method==='PUT'){const body=JSON.parse(options.body);preferences.state[body.field]=body.value;preferences.revisions[body.field]++;}value=preferences;}
  else if(path==='/explore/preview'||path==='/explore/run')value={tree_revision:`preview-${++previewSerial}`,matched_count:1,catalog:{fields:[]},last_run:{cell_count:1,ran_at:'2026-10-10T12:00:00Z'}};
  else throw Error(`Unexpected fixture read: ${path}`);
  return {ok:true,status:200,json:async()=>value};
 }};
 const old=new Map(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:v});
 localStorage.setItem('workspace.inspector.metadata','false');
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',plugins:[{name:'unrelated-surface-children',enforce:'pre',transform(_code,id){
  // Keep actual adapters, EpochViewer, Trace and requests; omit unrelated panes.
  if(id.endsWith('/tree-browser/ui/PagedTree.jsx'))return 'export default function Tree({trailingPane}){return trailingPane??null;}';
  if(id.endsWith('/epoch-browser/ui/EpochTreePane.jsx'))return `import React from 'react';export default function Tree({listProps}){return React.createElement('button',{'data-fixture-focus':true,onClick:()=>listProps.onFocus('epoch-1',${JSON.stringify(epoch)})},'Focus fixture epoch');}`;
  if(['/epoch-browser/ui/MetadataPanel.jsx','/annotations/ui/AnnotationTags.jsx','/annotations/ui/TagExchangeControls.jsx','/annotations/ui/EpochTags.jsx','/epoch-browser/ui/EpochConnections.jsx','/incoming-workbench/ui/IncomingEpochReview.jsx','/typed-query/ui/ProtocolViewFilter.jsx','/typed-query/ui/PredicateDialog.jsx'].some(p=>id.endsWith(p)))return 'export default function FixturePane(){return null;}';
 }}]});
 const {default:EpochViewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');
 const {default:Inspector}=await server.ssrLoadModule('/src/epoch-browser/ui/Inspector.jsx');
 const {default:Review}=await server.ssrLoadModule('/src/incoming-workbench/ui/FrozenIncomingReview.jsx');
 const {default:Viewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');
 const {default:Matching}=await server.ssrLoadModule('/src/epoch-browser/ui/MatchingEpochs.jsx');
 const {TraceViewPreferenceProvider,normalizeTraceViewPreference}=await server.ssrLoadModule('/src/traces/traceViewPreference.jsx');
 const {default:Explorer}=await server.ssrLoadModule('/src/metadata-explorer/ui/MetadataExplorer.jsx');
 const {default:PredicateDialog}=await server.ssrLoadModule('/src/typed-query/ui/PredicateDialog.jsx');
 const {predicateToDraft}=await server.ssrLoadModule('/src/typed-query/ui/predicateState.js');
 let renderer,savedSearch=null,savedExplorer=null;
 const rememberExplorer=value=>{savedExplorer=value;};
 function Shell({surface,revision='search-one',saved,shared=true,openRequest=0,pageKey='explorer'}){
  const [preference,setPreference]=useState(()=>normalizeTraceViewPreference());
  const element=surface==='overview'?React.createElement(EpochViewer,{epoch,designMode:true,columnTree:{selected:epoch.epoch_uuid},layout:{treeOpen:false,metadataOpen:false,sizes:{columns:'1fr',tree:200,treeMax:400,metadata:300,metadataMax:500}}}):surface==='explorer'?React.createElement(Explorer,{key:pageKey,projectId:'project',openRequest,session:saved??{step:'results',draft:predicateToDraft({all:[]}),resultsFromDraft:true},onSession:rememberExplorer}):surface==='main'?React.createElement(Inspector,{protocol,projectId:'project',filters:{},revision:0,initialEpochUuid:'epoch-1',initialNavigation:{treeOpen:false}}):surface==='workbench'?React.createElement(Review,{protocolId:'p',projectId:'project',item:{candidate_revision_uuid:'candidate'},revision:0,capabilities:{frozen_browse:true,drafts:true},session:{viewer:{focused:'epoch-1',treeOpen:false}}}):React.createElement(Matching,{key:revision,predicate:{all:[]},splits:['date','cell'],preview:{tree_revision:revision,catalog:{fields:[]}},session:saved??{revision,focused:'epoch-1',treeOpen:true},onSession:v=>{savedSearch=v;}});
  return shared?React.createElement(TraceViewPreferenceProvider,{value:preference,onChange:setPreference},element):element;
 }
 async function render(props){await act(async()=>{const e=React.createElement(Shell,props);if(renderer)renderer.update(e);else renderer=TestRenderer.create(e,{createNodeMock:node=>{if(node.type!=='canvas')return node.props.className?.startsWith('tv-plot ')?{focus(){}}:null;const el={getBoundingClientRect:()=>({left:0,top:0,width:603,height:300})};el.getContext=()=>new Proxy({canvas:el},{get:(o,k)=>k in o?o[k]:()=>{}});return el;}});});}
 const view=()=>renderer.root.findByProps({'aria-label':'Recorded response viewer'});
 const button=label=>view().findAllByType('button').find(n=>text(n.props.children).trim()===label);
 function assertWhole(){
  assert.equal(button('Whole epoch').props['aria-pressed'],true);assert.match(text(renderer.toJSON()),/67,500 \/ 67,500 samples/);assert.match(text(renderer.toJSON()),/0–6.7499 s/);
  assert(calls.some(c=>c.path.endsWith('/trace')&&c.query.get('start')==='60000'&&c.query.get('count')==='7500'),'complete mode reads through the final recorded sample');
  assert.equal(view().findAllByType('details').length,0);assert.equal(view().findAllByType('select').length,0);
  for(const label of ['Start sample','Sample count','Previous window','Next window'])assert.equal(view().findAllByProps({'aria-label':label}).length,0);
  assert.equal(view().findAllByType('form').length,0);
  assert.equal(view().findByProps({'aria-label':'Zoom in'}).props.disabled,false);
  assert.equal(view().findByProps({'aria-label':'Zoom out'}).props.disabled,true);
  assert.equal(button('Pan').props.disabled,true);
 }
 function assertSample(){assert.equal(button('Sample').props['aria-pressed'],true);assert.equal(view().findByProps({'aria-label':'Start sample'}).props.value,'30000');assert.equal(view().findByProps({'aria-label':'Sample count'}).props.value,'1000');assert.match(text(renderer.toJSON()),/1,000 \/ 67,500 samples/);}
 async function sample(){
  await act(async()=>button('Sample').props.onClick());
  await act(async()=>{view().findByProps({'aria-label':'Start sample'}).props.onChange({target:{value:'30000'}});view().findByProps({'aria-label':'Sample count'}).props.onChange({target:{value:'1000'}});});
  await act(async()=>view().findByType('form').props.onSubmit({preventDefault(){}}));assertSample();
  const last=calls.filter(c=>c.path.endsWith('/trace')).at(-1);return last;
 }
 async function zoomWhole(){
  const readsBefore=calls.filter(c=>c.path.endsWith('/trace')).length;
  await act(async()=>button('Zoom').props.onClick());assertWhole();
  await act(async()=>view().findByProps({'aria-label':'Zoom in'}).props.onClick());assertWhole();
  await act(async()=>view().findAllByProps({role:'group'}).find(n=>n.props.onKeyDown).props.onKeyDown({key:'+',preventDefault(){}}));
  assert.equal(button('Whole epoch').props['aria-pressed'],false);
  assert.equal(button('Sample').props['aria-pressed'],true);
  assert.match(text(renderer.toJSON()),/33,750 \/ 67,500 samples/);
  assert.equal(view().findByProps({'aria-label':'Start sample'}).props.value,'16875');
  assert.equal(view().findByProps({'aria-label':'Sample count'}).props.value,'33750');
  assert.equal(view().findByProps({'aria-label':'Previous window'}).props.disabled,false);
  assert.equal(view().findByProps({'aria-label':'Next window'}).props.disabled,false);
  assert.equal(button('Pan').props.disabled,false);
  await act(async()=>button('Pan').props.onClick());
  const plot=view().findAllByProps({role:'group'}).find(n=>n.props.onKeyDown);
  await act(async()=>plot.props.onKeyDown({key:'ArrowRight',shiftKey:true,preventDefault(){}}));
  assert.match(text(renderer.toJSON()),/3.375–6.7499 s/);
  await act(async()=>view().findByProps({'aria-label':'Zoom in'}).props.onClick());
  assert.equal(view().findByProps({'aria-label':'Zoom out'}).props.disabled,false);
  await act(async()=>view().findByProps({'aria-label':'Zoom out'}).props.onClick());
  assert.match(text(renderer.toJSON()),/33,750 \/ 67,500 samples/);
  await act(async()=>button('Whole epoch').props.onClick());assertWhole();
  await act(async()=>plot.props.onKeyDown({key:'-',preventDefault(){}}));assertWhole();
  await act(async()=>plot.props.onKeyDown({key:'+',preventDefault(){}}));
  assert.equal(button('Sample').props['aria-pressed'],true);
  await act(async()=>plot.props.onKeyDown({key:'Home',preventDefault(){}}));assertWhole();
  assert.equal(calls.filter(c=>c.path.endsWith('/trace')).length,readsBefore,'zoom, pan and Whole reuse the loaded full trace');
  assert(calls.filter(c=>c.path.endsWith('/trace')).every(c=>Number(c.query.get('count'))<=20000),'all transport reads retain the full-rate request bound');
 }
 async function rectangleAndPan(surface){
  const reads=calls.filter(c=>c.path.endsWith('/trace')).length;
  const pointer=()=>view().findByProps({className:'tv-overlay'}).props;
  const target={setPointerCapture(){},hasPointerCapture(){return true;},releasePointerCapture(){}};
  const event=(x,y)=>({button:0,pointerId:1,clientX:82+x,clientY:y,currentTarget:target});
  const input=name=>view().findByProps({'aria-label':name}).props.value;
  await act(async()=>view().findByProps({'aria-label':'Zoom in'}).props.onClick());assertWhole();
  await act(async()=>{pointer().onPointerDown(event(100,65));pointer().onPointerMove(event(400,195));});assertWhole();
  await act(async()=>pointer().onPointerUp(event(400,195)));
  assert.equal(input('Start sample'),'13500');assert.equal(input('Sample count'),'40500');
  assert.equal(view().findAllByProps({'aria-label':'Selected response bounds'}).length,1);
  assert.match(text(view().findByProps({'aria-label':'Selected sample bounds'})),/Start 13,500 · Stop 53,999/);
  await act(async()=>button('Pan').props.onClick());
  await act(async()=>{pointer().onPointerDown(event(200,100));pointer().onPointerMove(event(250,115));});
  assert.equal(input('Start sample'),'9450','Pan moves before release through the actual adapter');
  await act(async()=>pointer().onPointerMove(event(300,130)));assert.equal(input('Start sample'),'5400');
  await act(async()=>pointer().onPointerUp(event(300,130)));assert.equal(input('Start sample'),'5400');assert.equal(input('Sample count'),'40500');
  if(process.env.TRACE_TIMING){
   const times=[];await act(async()=>pointer().onPointerDown(event(200,100)));
   for(let i=1;i<=25;i++){const started=performance.now();await act(async()=>pointer().onPointerMove(event(200-i*2,100+i*.25)));times.push(performance.now()-started);}
   await act(async()=>pointer().onPointerUp(event(150,106.25)));times.sort((a,b)=>a-b);
   console.log('TRACE_PAN_TIMING '+JSON.stringify({surface,samples:40500,moves:25,median_ms:times[12],p95_ms:times[23],trace_reads_added:calls.filter(c=>c.path.endsWith('/trace')).length-reads,fixture:'React adapters with canvas double; not native paint'}));
  }
  await act(async()=>button('Whole epoch').props.onClick());assertWhole();
  assert.equal(calls.filter(c=>c.path.endsWith('/trace')).length,reads,'rectangle zoom, live pan and Whole add no reads');
 }
 return {calls,render,rectangleAndPan,assertWhole,sample,assertSample,zoomWhole,get viewer(){return renderer.root.findByType(Viewer).props;},async live(value){await act(async()=>renderer.root.findByType(Viewer).props.metadata.loadingPolicy.onLiveChange(value));},async move(direction){await act(async()=>renderer.root.findByType(Viewer).props.navigation.onMove(direction));},get savedSearch(){return savedSearch;},get savedExplorer(){return savedExplorer;},
 async filter(){await act(async()=>renderer.root.findByType(Matching).props.onViewFilters({tag:'qc'}));},
 async applySearch(){await act(async()=>renderer.root.findByType(PredicateDialog).props.onSearch(predicateToDraft({all:[]}),{all:[]},new AbortController().signal));},async focus(){await act(async()=>renderer.root.findByProps({'data-fixture-focus':true}).props.onClick());},async close(){await act(async()=>renderer?.unmount());await server.close();dom.window.close();for(const[k,v]of old)v?Object.defineProperty(globalThis,k,v):delete globalThis[k];}};
}
for(const surface of ['main','workbench','search'])test(`${surface} real adapter hides window inputs in Whole and switches zoom to Sample and Whole back to full extent`,async()=>{
 const h=await harness();try{await h.render({surface,shared:surface!=='search'});h.assertWhole();await h.zoomWhole();const last=await h.sample();if(surface==='workbench'){assert.equal(last.path,'/protocols/p/workbench/candidates/candidate/epochs/epoch-1/trace');assert.equal(last.query.get('candidate_scope_revision'),'scope');}}finally{await h.close();}
});
test('main and Workbench inherit one preference across adapter remounts',async()=>{
 const h=await harness();try{await h.render({surface:'main'});await h.sample();await h.render({surface:'workbench'});h.assertSample();await h.render({surface:'main'});h.assertSample();}finally{await h.close();}
});
test('Search restores preference across changed preview revision and remount',async()=>{
 const h=await harness();try{await h.render({surface:'search',shared:false});await h.sample();const saved=h.savedSearch;assert.deepEqual(saved.tracePreference,{kind:'sample',start:30000,count:1000});await h.render({surface:'search',shared:false,revision:'search-two',saved});await h.focus();h.assertSample();}finally{await h.close();}
});

test('actual MetadataExplorer retains Sample through filter/navigation reset and new popup search',async()=>{
 const h=await harness();try{
  await h.render({surface:'explorer',shared:false});await h.focus();h.assertWhole();await h.sample();
  const preference={kind:'sample',start:30000,count:1000};
  assert.deepEqual(h.savedExplorer.tracePreference,preference);
  await h.filter();assert.equal(h.savedExplorer.matchingNavigation.focused,null,'changing filters resets epoch navigation');
  assert.deepEqual(h.savedExplorer.tracePreference,preference);await h.focus();h.assertSample();
  await h.render({surface:'explorer',shared:false,openRequest:1});await h.applySearch();
  assert.deepEqual(h.savedExplorer.viewFilters,{});assert.equal(h.savedExplorer.matchingNavigation.focused,null,'a new query resets navigation');
  assert.deepEqual(h.savedExplorer.tracePreference,preference);await h.focus();h.assertSample();
  const saved=h.savedExplorer;
  await h.render({surface:'explorer',shared:false,saved,pageKey:'restored-explorer'});await h.focus();h.assertSample();
  assert.deepEqual(h.savedExplorer.tracePreference,preference);
  assert(h.calls.some(call=>call.path==='/explore/run'),'the real search callback ran through the API');
 }finally{await h.close();}
});

for(const surface of ['main','workbench','search','explorer','overview'])test(`${surface} shares rectangle zoom, live pan, exact bounds and loaded-trace reuse`,async()=>{
 const h=await harness();try{await h.render({surface,shared:!['search','explorer'].includes(surface)});if(surface==='explorer')await h.focus();h.assertWhole();await h.rectangleAndPan(surface);}finally{await h.close();}
});

for(const surface of ['main','workbench','search'])test(`${surface} shared traces follow epoch navigation with Live metadata off, including after toggling it`,async()=>{
 const h=await harness({epochCount:2});
 const detailReads=()=>h.calls.filter(call=>/\/epochs\/[^/]+$/.test(call.path));
 const assertEpoch=id=>{
  assert.equal(h.viewer.epoch.epoch_uuid,`epoch-${id}`);
  assert.equal(h.viewer.epoch.streams[0].uuid,`stream-${id}`);
  assert(h.calls.some(call=>call.path.endsWith(`/epochs/epoch-${id}/trace`)&&call.query.get('stream_uuid')===`stream-${id}`));
  h.assertWhole();
 };
 try{
  await h.render({surface,shared:surface!=='search'});
  assert.equal(h.viewer.metadata.loadingPolicy.live,false);assertEpoch(1);
  await h.move(1);assertEpoch(2);
  assert.equal(detailReads().length,0,'trace navigation must not load full metadata');
  await h.live(true);assertEpoch(2);assert.equal(detailReads().length,1);
  await h.live(false);const reads=detailReads().length;
  await h.move(-1);assertEpoch(1);
  await h.move(1);assertEpoch(2);
  assert.equal(detailReads().length,reads,'turning metadata off keeps traces independent');
 }finally{await h.close();}
});
