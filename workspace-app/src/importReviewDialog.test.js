import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

// Review imported data shows the Overview pending card (import view) per
// protocol from /workbench/summary; its hold sends one merge_all for the row's
// queue revision; confirmed actions close review to expose the shared Undo.
const row=(protocol_uuid,epochs,revision)=>({protocol_uuid,pending_epoch_count:epochs,pending_cell_count:epochs?2:0,eligible_pending_epoch_count:epochs,eligible_pending_cell_count:epochs?2:0,pending_new_cell_count:epochs?1:0,
 pending_recordings:epochs?[{source_sha256:'s1',filename:'2026-10-16_A.h5',epoch_count:epochs}]:[],left_out_epoch_count:0,main_blocked_reason:null,queue_revision:revision,
 capabilities:{cumulative_pending_browse:true,additive_accept:true,merge_all:true}});
const summary=(...rows)=>({loading:false,error:null,data:{contract_version:1,workbench_counts:rows}});

test('import review shares pending cards and closes on confirmed actions or an empty queue',async t=>{
 const old=globalThis.window;globalThis.window={...(old||{}),addEventListener(){},removeEventListener(){}};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {ImportSuggestions}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 let renderer,merges=[],inspected=[],reloads=0;
 const reload=()=>{reloads++;};
 const protocols=[{protocol_uuid:'protocol-A',name:'flash_family',counts:{cells:3,epochs:40}},{protocol_uuid:'protocol-B',name:'noise',counts:{cells:1,epochs:5}}];
 let props={autoOpenJobUuid:'job',jobs:[{job_uuid:'job',status:'complete',filename:'2026-10-16_A.h5',finished_at:'2026-10-16T10:00:00Z'}],protocols,
  workbenchSummary:{...summary(row('protocol-A',12,'q1'),row('protocol-B',0,'qb')),reload},onMerge:async(...args)=>{merges.push(args);return true;},onProtocol:(...args)=>inspected.push(args)};
 const render=async()=>act(()=>{const node=React.createElement(ImportSuggestions,props);if(renderer)renderer.update(node);else renderer=TestRenderer.create(node);});
 const open=()=>renderer.root.findAllByProps({className:'import-readiness'}).length===1;
 const cards=()=>renderer.root.findAll(node=>node.type==='section'&&String(node.props.className).includes('import-ready-protocol'));
 const hold=()=>renderer.root.findAllByType('button').find(node=>node.props['aria-label']==='Hold to merge all');
 const text=()=>JSON.stringify(renderer.toJSON());
 const event={button:0,preventDefault(){}},tick=ms=>act(async()=>{t.mock.timers.tick(ms);await Promise.resolve();});
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();globalThis.window=old;});
 await render();t.mock.timers.enable({apis:['setTimeout']});
 try{
  assert.ok(open(),'a finished import opens the review');
  assert.equal(reloads,1,'opening review renews the cached queue authority');
  assert.equal(cards().length,1,'one card per protocol with pending data; none at zero');
  assert.equal(cards()[0].props['aria-label'],'flash_family','titled by the protocol name');
  assert.match(text(),/12 new epochs from 2 cells not yet in Main/,'same subtitle as the Overview card');
  assert.match(text(),/2026-10-16_A\.h5/);assert.doesNotMatch(text(),/Applied dataset updates/);
  assert.match(text(),/Hold to merge all new data for a protocol into Main, or inspect it in Workbench to pick individual epochs/);
  await act(()=>renderer.root.findAllByType('button').find(node=>node.props.className==='primary').props.onClick());
  assert.deepEqual(inspected,[['protocol-A',{}]],'Inspect opens the protocol Workbench');assert.equal(open(),false,'inspecting closes the review');
  props={...props,autoOpenJobUuid:'job-2',jobs:[...props.jobs,{job_uuid:'job-2',status:'complete',filename:'next.h5'}]};await render();assert.ok(open());
  assert.equal(reloads,2,'reopening review renews its authority again');
  props={...props,workbenchSummary:{...props.workbenchSummary,loading:true}};await render();
  assert.equal(hold().props.disabled,true,'stale queue cannot be accepted while renewal is pending');
  props={...props,workbenchSummary:{...summary(row('protocol-A',12,'fresh-q2'),row('protocol-B',0,'qb')),reload}};await render();
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(async()=>{});
  assert.deepEqual(merges,[['protocol-A',{kind:'merge_all',queue_revision:'fresh-q2',origin:'protocol-overview'}]],'one hold sends one merge_all with the row queue revision');
  assert.equal(cards().length,0);assert.equal(open(),false,'confirmed merge closes the dialog to expose shared Undo');
  props={...props,workbenchSummary:{...props.workbenchSummary,loading:true}};await render();assert.equal(open(),false);
  props={...props,workbenchSummary:summary(row('protocol-A',0,'q2'),row('protocol-B',0,'qb'))};await render();
  assert.equal(open(),false,'the review closes once nothing remains pending');
  props={...props,autoOpenJobUuid:'finish-job',jobs:[...props.jobs,{job_uuid:'finish-job',status:'complete',filename:'finish.h5'}],workbenchSummary:summary(row('protocol-A',12,'finish-q')),onMerge:async()=>false};await render();
  const button=name=>renderer.root.findAllByType('button').find(node=>node.children.join('')===name);
  await act(()=>button('Finish reviewing').props.onClick());
  await act(()=>button('Leave out & finish').props.onClick());assert.ok(open(),'unconfirmed Finish keeps review open');
  props={...props,onMerge:async(...args)=>{merges.push(args);return true;}};await render();
  await act(()=>button('Finish reviewing').props.onClick());await act(()=>button('Leave out & finish').props.onClick());
  assert.equal(open(),false,'confirmed Finish exposes the same global Undo');
  assert.deepEqual(merges.at(-1),['protocol-A',{kind:'finish_review',queue_revision:'finish-q'}]);
  props={...props,workbenchSummary:summary(row('protocol-A',0,'finished'))};await render();

  props={...props,autoOpenJobUuid:'job-3',jobs:[...props.jobs,{job_uuid:'job-3',status:'complete',filename:'later.h5'}]};await render();
  assert.ok(open());assert.match(text(),/No pending protocol updates\./,'nothing pending shows the empty text');
  await act(()=>renderer.root.findByProps({'aria-label':'Close import review'}).props.onClick());assert.equal(open(),false,'the review can always be closed');
 }finally{t.mock.timers.reset();}
});

test('import review releases native modal state on departure even while a retained operation stays mounted',async()=>{
 const old=globalThis.window;globalThis.window={...(old||{}),addEventListener(){},removeEventListener(){}};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {ImportSuggestions}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 const {RetainedWorkspaceViews,useRetainedViewProtection}=await server.ssrLoadModule('/src/retainedWorkspaceViews.js');
 let renderer,shows=0,closes=0,modal=false;
 const presentation={remember(){}},props={autoOpenJobUuid:'job',jobs:[{job_uuid:'job',status:'complete',filename:'a.h5'}],workbenchSummary:summary(row('protocol-A',12,'q1')),protocols:[{protocol_uuid:'protocol-A',name:'Test',counts:{cells:1,epochs:3}}],onMerge:async()=>true,onProtocol(){}};
 function Import(){useRetainedViewProtection({busy:true});return React.createElement(ImportSuggestions,props);}
 const render=async key=>act(()=>{const element=React.createElement(RetainedWorkspaceViews,{route:{key,page:key},projectId:'p',projectPath:'/p',presentation,render:route=>route.page==='import'?React.createElement(Import):React.createElement('button',null,'Undo')});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element,{createNodeMock:node=>node.type==='dialog'?{showModal(){modal=true;shows++;},close(){modal=false;closes++;}}:null});});
 try{
  await render('import');assert.equal(modal,true);assert.equal(shows,1);
  await render('protocol');assert.equal(modal,false,'hidden import dialog must not block Overview or its Undo button');assert.equal(closes,1);
  await render('import');assert.equal(modal,true,'returning to the retained import view restores its open dialog');
  await act(()=>renderer.root.findByProps({'aria-label':'Close import review'}).props.onClick());assert.equal(modal,false);
  await act(()=>renderer.root.findAllByType('button').find(n=>n.props['aria-haspopup']==='dialog').props.onClick());assert.equal(modal,true);
  await act(()=>renderer.unmount());renderer=null;assert.equal(modal,false,'unmount releases the top layer too');
 }finally{await act(()=>renderer?.unmount());await server.close();globalThis.window=old;}
});
