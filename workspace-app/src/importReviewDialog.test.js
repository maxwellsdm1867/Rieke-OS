import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

// Review imported data shows the Overview pending card (import view) per
// protocol from /workbench/summary; its hold sends one merge_all for the row's
// queue revision, and the dialog closes once a refreshed summary is empty.
const row=(protocol_uuid,epochs,revision)=>({protocol_uuid,pending_epoch_count:epochs,pending_cell_count:epochs?2:0,eligible_pending_epoch_count:epochs,eligible_pending_cell_count:epochs?2:0,pending_new_cell_count:epochs?1:0,
 pending_recordings:epochs?[{source_sha256:'s1',filename:'2026-10-16_A.h5',epoch_count:epochs}]:[],left_out_epoch_count:0,main_blocked_reason:null,queue_revision:revision,
 capabilities:{cumulative_pending_browse:true,additive_accept:true,merge_all:true}});
const summary=(...rows)=>({loading:false,error:null,data:{contract_version:1,workbench_counts:rows}});

test('import review dialog shows per-protocol pending cards, holds to merge all, and closes once nothing is pending',async t=>{
 const old=globalThis.window;globalThis.window={...(old||{}),addEventListener(){},removeEventListener(){}};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {ImportSuggestions}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 let renderer,merges=[],inspected=[];
 const protocols=[{protocol_uuid:'protocol-A',name:'flash_family',counts:{cells:3,epochs:40}},{protocol_uuid:'protocol-B',name:'noise',counts:{cells:1,epochs:5}}];
 let props={autoOpenJobUuid:'job',jobs:[{job_uuid:'job',status:'complete',filename:'2026-10-16_A.h5',finished_at:'2026-10-16T10:00:00Z'}],protocols,
  workbenchSummary:summary(row('protocol-A',12,'q1'),row('protocol-B',0,'qb')),onMerge:async(...args)=>{merges.push(args);return true;},onProtocol:(...args)=>inspected.push(args)};
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
  assert.equal(cards().length,1,'one card per protocol with pending data; none at zero');
  assert.equal(cards()[0].props['aria-label'],'flash_family','titled by the protocol name');
  assert.match(text(),/12 new epochs from 2 cells not yet in Main/,'same subtitle as the Overview card');
  assert.match(text(),/2026-10-16_A\.h5/);assert.doesNotMatch(text(),/Applied dataset updates/);
  assert.match(text(),/Hold to merge all new data for a protocol into Main, or inspect it in Workbench to pick individual epochs/);
  await act(()=>renderer.root.findAllByType('button').find(node=>node.props.className==='primary').props.onClick());
  assert.deepEqual(inspected,[['protocol-A',{}]],'Inspect opens the protocol Workbench');assert.equal(open(),false,'inspecting closes the review');
  props={...props,autoOpenJobUuid:'job-2',jobs:[...props.jobs,{job_uuid:'job-2',status:'complete',filename:'next.h5'}]};await render();assert.ok(open());
  await act(()=>hold().props.onPointerDown(event));await tick(1000);await act(async()=>{});
  assert.deepEqual(merges,[['protocol-A',{kind:'merge_all',queue_revision:'q1',origin:'protocol-overview'}]],'one hold sends one merge_all with the row queue revision');
  assert.equal(cards().length,0,'the verified merge retires the card it showed');assert.ok(open(),'the review stays open until the refreshed summary arrives');
  props={...props,workbenchSummary:{...props.workbenchSummary,loading:true}};await render();assert.ok(open());
  props={...props,workbenchSummary:summary(row('protocol-A',0,'q2'),row('protocol-B',0,'qb'))};await render();
  assert.equal(open(),false,'the review closes once nothing remains pending');
  props={...props,autoOpenJobUuid:'job-3',jobs:[...props.jobs,{job_uuid:'job-3',status:'complete',filename:'later.h5'}]};await render();
  assert.ok(open());assert.match(text(),/No pending protocol updates\./,'nothing pending shows the empty text');
  await act(()=>renderer.root.findByProps({'aria-label':'Close import review'}).props.onClick());assert.equal(open(),false,'the review can always be closed');
 }finally{t.mock.timers.reset();}
});
