import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';

const row=id=>({epoch_uuid:id,cell_uuid:'cell',cell_label:'Cell',export_count:6,date:'2026-10-05',streams:[{kind:'responses',uuid:`stream-${id}`,sample_count:3,sample_rate:10000,units:'mV'}]});
async function harness({trace=false,viewer=false,fieldCatalog}={}){
 const old={fetch:globalThis.fetch,localStorage:globalThis.localStorage},memory=new Map();
 globalThis.localStorage={getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,value)};
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

test('actual Inspector keeps shared tag reads and saves working with automatic metadata off',async()=>{
 const h=await createWorkflowHarness({total:40});localStorage.setItem('workspace.inspector.liveMetadata','false');
 const input=()=>h.root.findAllByType('input').find(n=>n.props['aria-label']?.startsWith('Tag ')&&!n.props['aria-label'].startsWith('Tag to add'));
 try{
  await h.mount();await h.waitFor(()=>!!input()&&!input().props.disabled);
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-0');assert(h.fixture.requests.some(r=>r.path==='/epochs/epoch-0/annotations'));
  assert.equal(h.fixture.requests.filter(r=>/^\/epochs\/[^/?]+(?:\?|$)/.test(r.path)).length,0);
  await h.act(()=>input().props.onChange({target:{value:'trace inspection'}}));await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>!!input()&&!input().props.disabled);assert.deepEqual(h.fixture.annotations.get('epoch-0'),['trace inspection']);
  await h.act(()=>h.viewer.navigation.onMove(1));await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-1'&&!!input()&&!input().props.disabled);
  assert(h.fixture.requests.some(r=>r.path==='/epochs/epoch-1/annotations'));assert.equal(h.fixture.requests.filter(r=>/^\/epochs\/[^/?]+(?:\?|$)/.test(r.path)).length,0);
 }finally{await h.close();}
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
