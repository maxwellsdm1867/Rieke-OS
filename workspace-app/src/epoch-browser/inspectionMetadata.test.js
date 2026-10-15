import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';

const row=id=>({epoch_uuid:id,cell_uuid:'cell',cell_label:'Cell',export_count:6,date:'2026-10-05',streams:[{kind:'responses',uuid:`stream-${id}`,sample_count:3,sample_rate:10000,units:'mV'}]});
async function harness({trace=false,viewer=false,fieldCatalog,live=false}={}){
 const old={fetch:globalThis.fetch,localStorage:globalThis.localStorage},memory=new Map();
 globalThis.localStorage={getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,value)};
 if(live)memory.set('workspace.inspector.liveMetadata','true');
 const calls=[];globalThis.fetch=(url,options)=>{
  const path=url.replace(/^\/api/,'');
  if(path.includes('/trace?')){const id=path.split('/')[2];calls.push({path,...options});return Promise.resolve(new Response(JSON.stringify({epoch_uuid:id,stream_uuid:`stream-${id}`,start:0,count:3,sample_rate:10000,units:'mV',values:[1,2,3]})));}
  return new Promise(resolve=>calls.push({path,...options,finish:(data,status=200)=>resolve(new Response(JSON.stringify(data),{status}))}));
 };
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {useEpochInspection}=await server.ssrLoadModule('/src/epoch-browser/useEpochInspection.js');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const {default:Trace}=await server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx');
 const {default:Panel}=await server.ssrLoadModule('/src/epoch-browser/ui/MetadataPanel.jsx');
 const {default:Viewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');
 let renderer,current;const renders=[];
 function Probe({id='a',scope='scope-A',record=row(id),paused=false,readContext=null}){
  current=useEpochInspection({focused:id,path:`/epochs/${id}`,row:record,scope,revision:0,paused,readContext});renders.push(current);
  if(viewer)return React.createElement(Viewer,{epoch:current.resource.data,resource:current.resource,layout:{treeOpen:false,metadataOpen:true,sizes:{tree:270,treeMax:560,metadata:320,metadataMax:560,columns:'1fr 7px 320px'},onResize(){}},treePane:{},metadata:{loadingPolicy:current.metadata,catalog:{data:{fields:[]}},onClose(){}}});
  return React.createElement(React.Fragment,null,trace&&current.resource.data&&React.createElement(Trace,{epoch:current.resource.data}),React.createElement(Panel,{epoch:current.resource.data,loadingPolicy:current.metadata,catalog:fieldCatalog??{data:{fields:[{id:'metadata/cell/a~1b',label:'Field with slash',category:'Cell',type:'number'}]}},onClose(){}}));
 }
 return {calls,memory,renders,get current(){return current;},get root(){return renderer.root;},
  async render(props={},port){await act(async()=>{const probe=React.createElement(Probe,props),element=port?React.createElement(WorkspaceRequestProvider,{port},probe):probe;if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});},
  async close(){await act(async()=>renderer?.unmount());await server.close();for(const [key,value] of Object.entries(old)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}},
 };
}

test('trace-only inspection never requests values until asked; late values cannot follow focus or replace trace identity',async()=>{
 const h=await harness({trace:true});
 try{
  await h.render();assert.equal(h.current.live,false,'new profiles default to values off');assert.equal(h.root.findByProps({role:'switch'}).props.checked,false);assert.equal(h.root.findByProps({className:'metadata-switch-status'}).children.join(''),'Off');assert.deepEqual(h.calls.map(c=>c.path),['/epochs/a/trace?stream_uuid=stream-a&start=0&count=3']);
  const traceIdentity=h.current.resource.data;
  await act(async()=>h.current.metadata.load());const pending=h.calls.at(-1);assert.equal(pending.path,'/epochs/a');assert.deepEqual(h.current.resource.data,traceIdentity);assert.equal(h.current.resource.loading,false);
  await h.render({id:'b'});assert.equal(pending.signal.aborted,true);assert.equal(h.current.metadata.requested,false);assert.equal(h.current.metadata.values.data,null);
  await act(async()=>pending.finish({...row('a'),parameters:{secret:'old'}}));assert.equal(h.current.metadata.values.data,null);
  await act(async()=>h.current.metadata.load());await act(async()=>h.calls.at(-1).finish({error:'Unavailable'},503));
  assert.equal(h.current.resource.data.epoch_uuid,'b');assert.equal(h.current.resource.error,null);assert.match(h.current.metadata.values.error,/Unavailable/);
  await act(async()=>h.current.metadata.load());await act(async()=>h.calls.at(-1).finish({...row('b'),parameters:{answer:42}}));
  assert.equal(h.current.metadata.values.data.parameters.answer,42);assert.equal(h.current.resource.data.parameters,undefined,'optional values never replace the trace row');
  await h.render({id:'a'});assert.equal(h.current.metadata.requested,false,'returning does not revive an old one-shot request');
  await act(async()=>h.current.metadata.onLiveChange(true));assert.equal(h.memory.get('workspace.inspector.liveMetadata'),'true');
  await act(async()=>h.current.metadata.onLiveChange(false));assert.equal(h.memory.get('workspace.inspector.liveMetadata'),'false');
 }finally{await h.close();}
});

test('field-only sidebar copies exact registered IDs without requesting values or asserting missing values',async()=>{
 const h=await harness();const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator');let copied;
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async text=>{copied=text;}}}});
 try{
  await h.render();await act(async()=>h.root.findByProps({'aria-label':'Search metadata fields'}).props.onChange({target:{value:'a~1b'}}));await act(async()=>h.root.findByProps({'aria-label':'Copy field ID metadata/cell/a~1b'}).props.onClick());
  assert.equal(copied,'metadata/cell/a~1b');assert.equal(h.calls.length,0);
  const text=JSON.stringify(h.root.toJSON?.()??h.root.findByProps({'aria-label':'Available metadata fields'}).findAllByType('p').map(n=>n.children));
  assert.doesNotMatch(text,/No protocol settings were recorded|Not recorded/);
  await h.render({record:{epoch_uuid:'a'}});assert.match(h.current.resource.error,/Trace information is unavailable/);assert.equal(h.calls.length,0);
 }finally{if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor);else delete globalThis.navigator;await h.close();}
});

test('on-demand metadata and selected descriptors are fenced by scope and supplied owner',async()=>{
 const h=await harness(),requests=[];
 const owner=name=>({identity:name,request:(path,options)=>new Promise(resolve=>requests.push({name,path,...options,resolve}))});
 const a=owner('A'),b=owner('B');
 try{
  await h.render({},a);await act(async()=>h.current.metadata.load());assert.equal(requests.length,1);
  await h.render({scope:'scope-B'},b);assert.equal(requests[0].signal.aborted,true);assert.equal(h.current.metadata.requested,false);
  await act(async()=>requests[0].resolve({...row('a'),parameters:{wrong:true}}));assert.equal(h.current.metadata.values.data,null);
  await act(async()=>h.current.selectRow(row('a')));await h.render({scope:'scope-C',record:null},b);assert.equal(h.current.resource.data,null);
  assert.equal(h.calls.length,0,'no scoped read escapes to global fetch');
 }finally{await h.close();}
});

test('actual Inspector uses admitted page annotations without relocking tags on epoch navigation with metadata off',async t=>{
 const h=await createWorkflowHarness({total:40});localStorage.setItem('workspace.inspector.liveMetadata','false');
 const input=()=>h.root.findAllByType('input').find(n=>n.props['aria-label']?.startsWith('Tag ')&&!n.props['aria-label'].startsWith('Tag to add'));
 const commits=[];let tracking=false;
 function ProfiledApp(){return React.createElement(React.Profiler,{id:'tag-navigation',onRender:()=>{if(tracking){const editor=input(),add=h.root.findAllByType('button').find(node=>node.props['aria-label']==='Add epoch tag');commits.push({epoch:h.viewer.epoch?.epoch_uuid,inputDisabled:editor?.props.disabled,addDisabled:add?.props.disabled,missing:!editor||!add,pending:h.viewer.navigation.loading,treeDisabled:h.viewer.treePane.listProps.disabled});}}},React.createElement(h.App));}
 try{
  await h.mount(ProfiledApp);await h.waitFor(()=>!!input()&&!input().props.disabled);
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-0');assert.equal(h.fixture.requests.filter(r=>r.path.includes('/annotations')).length,0,'the admitted row already contains exact annotation revisions');
  assert.equal(h.fixture.requests.filter(r=>/^\/epochs\/[^/?]+(?:\?|$)/.test(r.path)).length,0);
  await h.act(()=>input().props.onChange({target:{value:'trace inspection'}}));await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>!!input()&&!input().props.disabled);assert.deepEqual(h.fixture.annotations.get('epoch-0'),['trace inspection']);
  await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
  const originalInput=h.fixture.nodes.get('Tag this epoch');
  tracking=true;
  await h.act(()=>h.viewer.navigation.onMove(1));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-1'&&!!input()&&!input().props.disabled);
  assert.equal(h.fixture.requests.filter(r=>r.method==='GET'&&r.path.includes('/annotations')).length,0,'navigation does not start a duplicate annotation loading cycle');
  assert.equal(h.fixture.nodes.get('Tag this epoch'),originalInput,'tag editor input remains mounted');
  assert.equal(h.fixture.requests.filter(r=>/^\/epochs\/[^/?]+(?:\?|$)/.test(r.path)).length,0);
  assert.equal(input().props.disabled,false);
  tracking=false;assert(commits.length>=2,'profile captures navigation and its follow-up effect commits');
  assert(commits.some(commit=>commit.epoch==='epoch-1'));
  assert(commits.every(commit=>!commit.missing&&!commit.inputDisabled&&!commit.addDisabled&&!commit.pending&&!commit.treeDisabled),JSON.stringify(commits));
  t.diagnostic(`All ${commits.length} same-page navigation commits retain enabled tag and tree controls.`);
 }finally{tracking=false;await h.close();}
});


test('actual shared viewer keeps metadata policy usable through errors and uses loaded values for scientific context',async()=>{
 const h=await harness({viewer:true});
 const toggle=()=>h.root.findAllByType('input').find(n=>n.props.type==='checkbox');
 function enabled(){for(let node=toggle();node;node=node.parent)assert(!node.props.inert,'metadata policy must never be inert with optional values');}
 try{
  await h.render();assert.match(h.root.findByProps({className:'epoch-heading'}).findAll(()=>true).flatMap(n=>n.children.filter(c=>typeof c==='string')).join(' '),/6 saved exports/);await act(async()=>h.current.metadata.onLiveChange(true));enabled();
  await act(async()=>h.calls.findLast(c=>c.path==='/epochs/a').finish({error:'Values failed'},503));enabled();
  await act(async()=>toggle().props.onChange({target:{checked:false}}));assert.equal(h.current.resource.data.epoch_uuid,'a');
  await act(async()=>h.current.metadata.load());await act(async()=>h.calls.findLast(c=>c.path==='/epochs/a').finish({...row('a'),source_filename:'context-file.h5',metadata:{group:{properties:{externalSolutionAdditions:'solution present'}}}}));
  await act(async()=>h.root.findAllByType('button').find(n=>n.props.children==='Summary').props.onClick());
  const text=h.root.findByProps({'aria-label':'Recording and condition context'}).findAll(()=>true).flatMap(n=>n.children.filter(c=>typeof c==='string')).join(' ');
  assert.match(text,/context-file.h5/);assert.match(text,/solution present/);assert.doesNotMatch(text,/Source not recorded/);
  assert.equal(h.current.resource.data.source_filename,undefined,'Trace still uses its admitted lightweight row');
 }finally{await h.close();}
});


test('paused same-scope reads hide retained metadata without disabling policy or catalog',async()=>{
 const h=await harness({viewer:true});
 try{
  await h.render();await act(async()=>h.current.metadata.load());await act(async()=>h.calls.findLast(c=>c.path==='/epochs/a').finish({...row('a'),parameters:{answer:42}}));assert.equal(h.current.metadata.values.data.parameters.answer,42);
  await h.render({paused:true});assert.equal(h.current.metadata.values.data,null);assert.equal(h.current.resource.data,null);assert.equal(h.current.metadata.canLoad,false);
  const input=h.root.findAllByType('input').find(n=>n.props.type==='checkbox');for(let n=input;n;n=n.parent)assert(!n.props.inert);assert(h.root.findByProps({'aria-label':'Available metadata fields'}));
  await h.render();assert.equal(h.current.metadata.requested,false,'a one-shot demand does not survive retirement');assert.equal(h.current.metadata.values.data,null);
  await act(async()=>h.current.metadata.onLiveChange(true));assert.equal(h.current.metadata.values.data.parameters.answer,42);await h.render({paused:true});assert.equal(h.current.metadata.values.data,null,'live mode also hides retained values while paused');
 }finally{await h.close();}
});

test('scoped trace-only browsing retains required detail admission and never falls back to a global trace',async()=>{
 const h=await harness({trace:true}),requests=[];
 const id='00000000-0000-0000-0000-000000000001',stream='00000000-0000-0000-0000-000000000002';
 const context={kind:'imported_snapshot',project_uuid:id,publication_revision:id,scope_data_revision:id,protocol_uuid:id,source_sha256:'a'.repeat(64),processing_version:'test'};
 const record={...row(id),streams:[{kind:'responses',uuid:stream,sample_count:3,sample_rate:10000,units:'mV'}]};
 const port={identity:'imported',request:(path,options)=>new Promise(resolve=>requests.push({path,...options,resolve}))};
 try{
  await h.render({id,record},port);assert.equal(requests.length,1);assert.equal(requests[0].path,`/epochs/${id}`);assert.equal(h.current.resource.data,null);
  await act(async()=>requests[0].resolve({...record,trace_read_context:context,parameters:{value:7}}));
  assert.equal(requests.length,2);assert.ok(requests[1].path.startsWith(`/snapshot/protocols/${id}/epochs/${id}/trace?`));
  assert.equal(h.current.metadata.values.data,null,'required descriptor acquisition does not display optional values');assert.equal(h.current.resource.data.parameters,undefined);
  await act(async()=>requests[1].resolve({epoch_uuid:id,stream_uuid:stream,start:0,count:3,sample_rate:10000,units:'mV',values:[1,2,3],read_context:context}));
  assert.equal(h.calls.length,0,'all reads remain with the supplied owner');
  await act(async()=>h.current.metadata.load());assert.equal(h.current.metadata.values.data.parameters.value,7);
  await h.render({id,record,scope:'new'}, {...port,identity:'other'});await act(async()=>requests.at(-1).resolve(record));
  assert.match(h.current.resource.error,/Trace information is unavailable/);assert.equal(h.current.resource.data,null);assert.equal(h.calls.length,0);
 }finally{await h.close();}
});


test('explicit frozen trace authority does not trigger imported descriptor discovery',async()=>{
 const h=await harness(),requests=[],readContext={root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'candidate-1'};
 const owner={identity:'frozen',request:(path)=>{requests.push(path);return Promise.reject(Error('Unexpected detail read'));}};
 try{await h.render({readContext},owner);assert.equal(h.current.resource.data.epoch_uuid,'a');assert.equal(h.current.metadata.requested,false);assert.deepEqual(requests,[]);assert.deepEqual(h.calls,[]);}finally{await h.close();}
});


test('field-only catalog keeps scoped definition demand explicit and cancellable',async()=>{
 let loads=0,cancels=0;const h=await harness({fieldCatalog:{scoped:true,data:null,loading:false,load:()=>loads++}});
 try{await h.render();const load=h.root.findAllByType('button').find(n=>n.props.children==='Load field names');assert.ok(load);await act(async()=>load.props.onClick());assert.equal(loads,1);assert.equal(h.calls.length,0);const text=h.root.findByProps({'aria-label':'Available metadata fields'}).findAll(()=>true).flatMap(n=>n.children.filter(c=>typeof c==='string')).join(' ');assert.doesNotMatch(text,/No registered fields/);}finally{await h.close();}
 const pending=await harness({fieldCatalog:{scoped:true,data:null,loading:true,cancel:()=>cancels++}});
 try{await pending.render();await act(async()=>pending.root.findAllByType('button').find(n=>n.props.children==='Cancel fields').props.onClick());assert.equal(cancels,1);}finally{await pending.close();}
});


test('live metadata never gates admitted trace reads or replaces their identity across focus and metadata failure',async()=>{
 const h=await harness({trace:true,live:true});
 try{
  await h.render();
  const first=h.calls.find(c=>c.path==='/epochs/a');
  assert.ok(first,'live values still load automatically');
  assert.ok(h.calls.some(c=>c.path==='/epochs/a/trace?stream_uuid=stream-a&start=0&count=3'),'trace starts while metadata is held');
  assert.equal(h.current.resource.loading,false);
  assert.equal(h.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false,'trace samples are ready while metadata remains unresolved');
  assert.equal(h.current.resource.data.streams[0].uuid,'stream-a');
  await h.render({id:'b'});
  assert.equal(first.signal.aborted,true);
  assert.ok(h.calls.some(c=>c.path==='/epochs/b/trace?stream_uuid=stream-b&start=0&count=3'));
  await act(async()=>first.finish({...row('a'),parameters:{stale:true}}));
  assert.equal(h.current.resource.data.epoch_uuid,'b');
  assert.equal(h.current.metadata.values.data,null);
  await act(async()=>h.calls.find(c=>c.path==='/epochs/b').finish({error:'Live values unavailable'},503));
  assert.equal(h.current.resource.error,null);
  assert.equal(h.current.resource.data.streams[0].uuid,'stream-b');
  assert.match(h.current.metadata.values.error,/Live values unavailable/);
  await act(async()=>h.current.metadata.load());
  await act(async()=>h.calls.findLast(c=>c.path==='/epochs/b').finish({...row('b'),streams:[{...row('b').streams[0],uuid:'unadmitted-stream'}],parameters:{answer:42}}));
  assert.equal(h.current.metadata.values.data.parameters.answer,42);
  assert.equal(h.current.resource.data.streams[0].uuid,'stream-b');
  assert.equal(h.calls.filter(c=>c.path.includes('unadmitted-stream')).length,0);
 }finally{await h.close();}
});

test('live scoped inspection still requires descriptor admission and keeps failures scoped',async()=>{
 const h=await harness({trace:true,live:true}),requests=[];
 const port={identity:'scoped-live',request:(path,options)=>new Promise(resolve=>requests.push({path,...options,resolve}))};
 try{
  await h.render({},port);
  assert.deepEqual(requests.map(c=>c.path),['/epochs/a']);
  assert.equal(h.current.resource.data,null);
  await act(async()=>requests[0].resolve(row('a')));
  assert.match(h.current.resource.error,/Trace information is unavailable/);
  assert.equal(h.current.resource.data,null);
  assert.equal(requests.length,1,'missing attestation never starts a trace');
  assert.equal(h.calls.length,0,'scoped live reads never escape through global transport');
 }finally{await h.close();}
});


test('live frozen inspection requests its trace before optional metadata completes and survives metadata error',async()=>{
 const h=await harness({trace:true,live:true}),requests=[];
 const readContext={root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'candidate-1'};
 const port={identity:'frozen-live',traceReadContext:readContext,request:(path,options)=>new Promise((resolve,reject)=>requests.push({path,...options,resolve,reject}))};
 try{
  await h.render({readContext},port);
  const metadata=requests.find(c=>c.path==='/epochs/a'),trace=requests.find(c=>c.path.includes('/trace?'));
  assert.ok(metadata);assert.ok(trace,'trace starts without waiting for optional values');
  assert.ok(trace.path.startsWith(readContext.root+'/epochs/a/trace?'));
  assert.ok(trace.path.includes('candidate_scope_revision=candidate-1'));
  await act(async()=>trace.resolve({epoch_uuid:'a',stream_uuid:'stream-a',start:0,count:3,sample_rate:10000,units:'mV',values:[1,2,3]}));
  assert.equal(h.root.findByProps({'aria-label':'Exact sample index for cursor'}).props.disabled,false);
  await act(async()=>metadata.reject(Error('Frozen metadata unavailable')));
  assert.equal(h.current.resource.error,null);
  assert.match(h.current.metadata.values.error,/Frozen metadata unavailable/);
  assert.equal(h.calls.length,0);
 }finally{await h.close();}
});


test('live legacy detail fallback retries its failed read when no page descriptor exists',async()=>{
 const h=await harness({live:true});
 try{
  await h.render({record:{epoch_uuid:'a'}});
  await act(async()=>h.calls.find(c=>c.path==='/epochs/a').finish({error:'Detail unavailable'},503));
  assert.match(h.current.resource.error,/Detail unavailable/);
  await act(async()=>h.current.resource.reload());
  assert.equal(h.calls.filter(c=>c.path==='/epochs/a').length,2);
  await act(async()=>h.calls.at(-1).finish(row('a')));
  assert.equal(h.current.resource.data.epoch_uuid,'a');
  assert.equal(h.current.resource.error,null);
 }finally{await h.close();}
});


test('Inspector still locks tags and reads authoritative annotations when the admitted row has none',async()=>{
 const h=await createWorkflowHarness({total:3});localStorage.setItem('workspace.inspector.liveMetadata','false');let release;
 const input=()=>h.root.findAllByType('input').find(n=>n.props['aria-label']==='Tag this epoch');
 h.fixture.respond=(url,options,fallback)=>{
  if(url.pathname==='/api/protocols/protocol-A/epochs'){const page=fallback();return {...page,epochs:page.epochs.map(({annotations,...row})=>row)};}
  if(url.pathname==='/api/epochs/epoch-0/annotations')return new Promise(resolve=>{release=()=>resolve(fallback());});
  return fallback();
 };
 try{
  await h.mount();await h.waitFor(()=>!!release&&!!input());
  assert.equal(input().props.disabled,true);assert(h.root.findAllByProps({role:'status'}).some(node=>node.children.includes('Loading annotations…')));
  await h.act(()=>release());await h.waitFor(()=>!input().props.disabled);
  assert.equal(h.fixture.requests.filter(r=>r.path==='/epochs/epoch-0/annotations?include_cell_epoch_count=false').length,1);
 }finally{await h.close();}
});

test('page annotation revision conflicts remain visible and cannot commit or navigate with stale author state',async()=>{
 const h=await createWorkflowHarness({total:3});localStorage.setItem('workspace.inspector.liveMetadata','false');
 const input=()=>h.root.findAllByType('input').find(n=>n.props['aria-label']==='Tag this epoch');
 try{
  await h.mount();await h.waitFor(()=>!!input()&&!input().props.disabled);
  h.fixture.annotationVersions.set('epoch:epoch-0',1);h.fixture.annotations.set('epoch-0',['external author revision']);
  await h.act(()=>input().props.onChange({target:{value:'must not overwrite'}}));
  await h.act(()=>h.root.findByProps({'aria-label':'Shared cell and epoch tags'}).props.onKeyDown({key:'Tab',target:h.fixture.nodes.get('Tag this epoch'),preventDefault(){},stopPropagation(){}}));
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-0');assert.equal(input().props.value,'must not overwrite');
  assert.deepEqual(h.fixture.annotations.get('epoch-0'),['external author revision']);
  const write=h.fixture.requests.find(r=>r.path==='/annotations');assert.equal(write.status,409);assert.deepEqual(write.body.expected_revisions,{'epoch-0':0});
  assert(h.root.findAllByProps({role:'alert'}).some(node=>node.children.includes('Annotation revision conflict')));
 }finally{await h.close();}
});


test('frozen Inspector has no disabled tag or tree-control commit during ordinary same-page epoch navigation',async t=>{
 const h=await createWorkflowHarness({total:3});localStorage.setItem('workspace.inspector.liveMetadata','false');
 const root='/protocols/protocol-A/workbench/candidates/candidate-A';
 const cells=[{cell_uuid:'cell-0',label:'Cell0',date:'2026-10-01',epochs:3}];
 const epochs=Array.from({length:3},(_,i)=>({epoch_uuid:`epoch-${i}`,cell_uuid:'cell-0',date:'2026-10-01',cell_label:'Cell0',streams:[],curation:{included:true,tags:[]},annotations:{epoch_uuid:`epoch-${i}`,cell_uuid:'cell-0',epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}}));
 h.fixture.respond=(url,options,fallback)=>url.pathname===`/api${root}/epochs`?{epochs,cells,total:3,offset:0,query_revision:'scope-A',candidate_scope_revision:'scope-A',expected_binding_version:2}:fallback();
 const Inspector=await h.component('Inspector'),commits=[];let tracking=false;
 function ProfiledInspector(){return React.createElement(React.Profiler,{id:'frozen-tag-navigation',onRender:()=>{if(tracking){const input=h.root.findAllByProps({'aria-label':'Tag this epoch'})[0],add=h.root.findAllByProps({'aria-label':'Add epoch tag'})[0];commits.push({epoch:h.viewer.epoch?.epoch_uuid,inputDisabled:input?.props.disabled,addDisabled:add?.props.disabled,missing:!input||!add,pending:h.viewer.navigation.loading,treeDisabled:h.viewer.treePane.listProps.disabled});}}},React.createElement(Inspector,{projectId:'project',protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'scope-A',expected_binding_version:2,cells},readContext:{root,candidate_scope_revision:'scope-A',cohort_key:'cohort-A'},filters:{},revision:0,initialEpochUuid:'epoch-0'}));}
 try{
  await h.mount(ProfiledInspector);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-0'&&!h.viewer.treePane.listProps.disabled);
  const before=h.fixture.requests.length;tracking=true;
  for(const direction of [1,1,-1])await h.act(()=>h.viewer.navigation.onMove(direction));
  tracking=false;assert.equal(h.viewer.epoch.epoch_uuid,'epoch-1');assert(commits.length>=6,'each navigation includes follow-up effect commits');
  assert(commits.some(commit=>commit.epoch==='epoch-2'));
  assert(commits.every(commit=>!commit.missing&&!commit.inputDisabled&&!commit.addDisabled&&!commit.pending&&!commit.treeDisabled),JSON.stringify(commits));
  assert.equal(h.fixture.requests.slice(before).filter(read=>read.path.includes('/annotations')||read.path.startsWith(root+'/epochs?')).length,0);
  t.diagnostic(`All ${commits.length} frozen same-page navigation commits retain enabled tag and tree controls.`);
 }finally{tracking=false;await h.close();}
});

test('Inspector keeps captured trace descriptor independent of held tag-page refresh and fences a new publication',async()=>{
 const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
 const capability={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
 const root=`/protocols/${uid(4)}/workbench/candidates/${uid(5)}`,epoch={...row(uid(6)),source_sha256:'b'.repeat(64),streams:[{kind:'responses',uuid:uid(7),sample_count:3,sample_rate:10000,units:'mV'}],annotations:{epoch_uuid:uid(6),cell_uuid:'cell',epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}};
 const cells=[{cell_uuid:'cell',label:'Cell',epochs:1}],h=await createWorkflowHarness({total:1});let hold=false,release;
 const page=()=>({epochs:[epoch],cells,total:1,offset:0,query_revision:'scope-A',candidate_scope_revision:'scope-A',expected_binding_version:2,trace_read_context:capability});
 h.fixture.respond=(url,options,fallback)=>url.pathname===`/api${root}/epochs`?hold?new Promise(resolve=>{release=()=>resolve(page());}):page():fallback();
 const Inspector=await h.component('Inspector'),props={projectId:uid(2),protocol:{definition:{protocol_uuid:uid(4)},query_revision:'scope-A',expected_binding_version:2,cells},readContext:{root,candidate_scope_revision:'scope-A',cohort_key:'cohort-A'},traceReadContext:capability,filters:{},revision:0,initialEpochUuid:epoch.epoch_uuid};
 try{
  await h.mount(Inspector,props);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===epoch.epoch_uuid);
  assert.equal(h.viewer.traceEpoch,epoch);assert.deepEqual(h.viewer.traceReadContext,capability);assert.equal(h.viewer.readContext.trace_read_context,undefined);
  hold=true;await h.render(Inspector,{...props,revision:1});await h.waitFor(()=>!!release);
  assert.equal(h.viewer.epoch,null,'tag authority is waiting for its refreshed page');assert.equal(h.viewer.traceEpoch.epoch_uuid,epoch.epoch_uuid);assert.deepEqual(h.viewer.traceReadContext,capability);assert.equal(h.viewer.treePane.listProps.disabled,true,'display capability cannot grant mutation authority');
  const refreshed={...capability,token:uid(9),publication_revision:uid(10)};await h.render(Inspector,{...props,revision:1,traceReadContext:refreshed});
  assert.equal(h.viewer.traceReadContext.token,refreshed.token);assert.equal(h.viewer.traceEpoch,null,'old source publication cannot supply a descriptor');
  await h.act(()=>release());
 }finally{await h.close();}
});


async function offPageDisplayHarness({selected=false,focusCell=null}={}){
 const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
 const capability={kind:'prepared_display',token:uid(1),project_uuid:uid(2),publication_revision:uid(3),view_kind:'workbench_pending',protocol_uuid:uid(4),candidate_revision_uuid:uid(5),membership_sha256:'a'.repeat(64)};
 const pageCapability=selected?{...capability,token:uid(11),view_kind:'workbench_selected'}:capability;
 const root=`/protocols/${uid(4)}/workbench/candidates/${uid(5)}`;
 const make=(n,cell,streams)=>({...row(uid(n)),cell_uuid:cell,source_sha256:'b'.repeat(64),streams,annotations:{epoch_uuid:uid(n),cell_uuid:cell,epoch_tags:[],cell_tags:[],effective_tags:[],revisions:{epoch:{},cell:{}}}});
 const a=make(6,'cell-a',[]),b=make(8,'cell-b',[{kind:'responses',uuid:uid(7),sample_count:10000,sample_rate:10000,units:'mV'}]);
 const cells=[{cell_uuid:'cell-a',label:'A',date:'2026-10-05',epochs:1},{cell_uuid:'cell-b',label:'B',date:'2026-10-05',epochs:1}];
 const h=await createWorkflowHarness({total:2,liveMetadata:false});
 const names=['ResizeObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame'],old=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
 globalThis.ResizeObserver=class{observe(){}disconnect(){}};globalThis.getComputedStyle=()=>({getPropertyValue:()=>''});globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
 const canvas={getBoundingClientRect:()=>({width:603,height:300}),getContext:()=>new Proxy({},{get:()=>()=>{}})};
 h.fixture.createNodeMock=element=>element.type==='canvas'?canvas:undefined;
 h.fixture.traceComponent=await h.component('TraceViewer');
 const page=(epochs,extra={})=>({epochs,cells,total:2,offset:0,query_revision:'scope-A',candidate_scope_revision:'scope-A',expected_binding_version:2,trace_read_context:pageCapability,...extra});
 const clickedPage=page([b],{total:1});let releaseAnchor;
 h.fixture.respond=(url,options,fallback)=>{
  if(url.pathname===`/api${root}/epochs`){
   if(url.searchParams.has('anchor_uuid'))return new Promise(resolve=>{releaseAnchor=()=>resolve(page([a,b]));});
   if(url.searchParams.get('cell_uuid')==='cell-b')return clickedPage;
   if(url.searchParams.get('cell_uuid')==='cell-a')return page([a],{total:1});
   return page([a]);
  }
  if(url.pathname.endsWith('/display'))return new Promise(()=>{});
  return fallback();
 };
 const Inspector=await h.component('Inspector'),props={projectId:uid(2),protocol:{definition:{protocol_uuid:uid(4)},query_revision:'scope-A',expected_binding_version:2,cells},readContext:{root,candidate_scope_revision:'scope-A',cohort_key:'cohort-A',...(selected?{selection_token:uid(12)}:{})},traceReadContext:capability,filters:{},revision:0,initialEpochUuid:a.epoch_uuid,...(focusCell?{initialNavigation:{focusCell}}:{})};
 await h.mount(Inspector,props);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===a.epoch_uuid);
 return {h,Inspector,props,a,b,page:clickedPage,capability,pageCapability,release:()=>releaseAnchor?.(),get pending(){return !!releaseAnchor;},async close(){await h.close();for(const name of names){if(old[name]===undefined)delete globalThis[name];else globalThis[name]=old[name];}}};
}

test('off-central-page native list click starts prepared geometry before held anchor grants curation',async()=>{
 const f=await offPageDisplayHarness(),{h,b}=f;
 try{
  const date=h.root.findAllByType('details').find(n=>n.props.className==='cell-tree-date');await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
  const cell=h.root.findAllByType('details').find(n=>n.props.className?.includes('cell-tree-cell')&&n.findByType('summary').props['aria-label']?.includes('B'));
  await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
  await h.waitFor(()=>h.root.findAllByType('button').some(n=>n.props['aria-label']?.includes('B epoch 1')));
  const button=h.root.findAllByType('button').find(n=>n.props['aria-label']?.includes('B epoch 1'));
  await h.act(()=>button.props.onClick({shiftKey:false,metaKey:false,ctrlKey:false}));
  await h.waitFor(()=>f.pending&&h.fixture.requests.some(r=>r.path.includes(`/epochs/${b.epoch_uuid}/display?`)));
  assert.equal(h.viewer.traceEpoch,b);assert.equal(h.viewer.epoch,null);assert.equal(h.viewer.navigation.loading,true);assert.equal(h.viewer.inclusion.disabled,true);
  assert.equal(h.fixture.requests.filter(r=>r.path.includes('/display?')).length,1);
  assert.equal(h.fixture.requests.some(r=>r.path.includes('/trace?')),false,'no raw/background fallback');
  const oldClick=h.viewer.treePane.listProps.onFocus;
  await h.render(f.Inspector,{...f.props,revision:1});
  assert.equal(h.viewer.traceEpoch,null,'unconfirmed click descriptor cannot survive navigation revision change');
  await h.act(()=>oldClick(b.epoch_uuid,b,f.page));assert.equal(h.viewer.traceEpoch,null,'retired callback cannot re-admit an old row');
  await h.render(f.Inspector,f.props);assert.equal(h.viewer.traceEpoch,null,'returning to the same navigation key does not resurrect its retired clicked offer');
 }finally{await f.close();}
});

test('off-page trace admission rejects stale revision, wrong capability and arbitrary row hints',async()=>{
 for(const variant of ['query','binding','capability','row']){
  const f=await offPageDisplayHarness(),{h,b}=f;
  try{
   const page={...f.page,...(variant==='query'?{query_revision:'stale'}:variant==='binding'?{expected_binding_version:99}:variant==='capability'?{trace_read_context:{...f.capability,token:'00000000-0000-4000-8000-000000000099'}}:{})};
   await h.act(()=>h.viewer.treePane.listProps.onFocus(b.epoch_uuid,variant==='row'?{...b}:b,page));
   await h.waitFor(()=>f.pending);
   assert.equal(h.viewer.traceEpoch,null,variant);assert.equal(h.fixture.requests.some(r=>r.path.includes('/display?')),false,variant);
  }finally{await f.close();}
 }
});

test('off-page clicked display and callbacks retire when the workspace request owner changes',async()=>{
 const f=await offPageDisplayHarness(),{h,b}=f;
 const {WorkspaceRequestProvider}=await h.module('workspaceRequest.js');
 const request=async(path,options)=>{const response=await fetch('/api'+path,options);return response.json();};
 const a={identity:'actor-A',request},other={identity:'actor-B',request};
 function Owned({port}){return React.createElement(WorkspaceRequestProvider,{port},React.createElement(f.Inspector,f.props));}
 try{
  await h.render(Owned,{port:a});await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===f.a.epoch_uuid);
  const stale=h.viewer.treePane.listProps.onFocus;
  await h.act(()=>stale(b.epoch_uuid,b,f.page));await h.waitFor(()=>h.viewer.traceEpoch===b);
  await h.render(Owned,{port:other});await h.waitFor(()=>h.viewer.epoch?.epoch_uuid===f.a.epoch_uuid);
  assert.notEqual(h.viewer.traceEpoch,b);
  const before=h.fixture.requests.filter(r=>r.path.includes('/display?')).length;
  await h.act(()=>stale(b.epoch_uuid,b,f.page));
  assert.notEqual(h.viewer.traceEpoch,b);assert.equal(h.fixture.requests.filter(r=>r.path.includes('/display?')).length,before);
 }finally{await f.close();}
});


test('selected off-page offers never borrow parent capabilities and cell-focus changes retire offers',async()=>{
 const selected=await offPageDisplayHarness({selected:true});
 try{
  const {h,b}=selected;
  assert.equal(h.viewer.traceReadContext.view_kind,'workbench_selected');
  await h.act(()=>h.viewer.treePane.listProps.onFocus(b.epoch_uuid,b,{...selected.page,trace_read_context:selected.capability}));
  await h.waitFor(()=>selected.pending);
  assert.equal(h.viewer.traceEpoch,null);assert.equal(h.fixture.requests.some(r=>r.path.includes('/display?')),false,'parent pending capability cannot admit a selected-view click');
 }finally{await selected.close();}
 const focused=await offPageDisplayHarness({focusCell:'cell-a'});
 try{
  const {h,b}=focused;
  await h.act(()=>h.viewer.treePane.listProps.onFocus(b.epoch_uuid,b,focused.page));
  await h.waitFor(()=>focused.pending);
  assert.equal(h.viewer.traceEpoch,null,'clearing focused-cell scope needs the new scope receipt');
  assert.equal(h.fixture.requests.some(r=>r.path.includes('/display?')),false);
 }finally{await focused.close();}
});
