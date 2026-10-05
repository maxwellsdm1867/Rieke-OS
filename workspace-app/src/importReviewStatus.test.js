import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import useImportReviewStatus,{importReviewStatusLabel} from './recording-import/useImportReviewStatus.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const resource=counts=>({loading:false,error:null,data:{workbench_counts:counts.map(([protocol_uuid,pending_epoch_count])=>({protocol_uuid,pending_epoch_count}))}});
test('pending status follows authoritative cumulative counts, survives refresh, and resets between projects',async()=>{
 let status,view;function Probe({source,project='p'}){status=useImportReviewStatus(source,project);return null;}
 async function render(source,project){await act(()=>{const element=React.createElement(Probe,{source,project});if(view)view.update(element);else view=TestRenderer.create(element);});}
 try{
  await render({loading:true,data:null});assert.equal(status.pendingProtocols,null);assert.match(importReviewStatusLabel(status),/Checking/);assert.doesNotMatch(importReviewStatusLabel(status),/No incoming/);
  await render(resource([['a',3],['b',0],['c',2]]));assert.deepEqual(status,{pendingProtocols:2,phase:'ready'});
  await render({loading:true,data:null});assert.equal(status.pendingProtocols,2);assert.match(importReviewStatusLabel(status),/last confirmed/);
  await render({loading:false,error:'Offline',data:null});assert.equal(status.pendingProtocols,2);assert.match(importReviewStatusLabel(status),/unavailable/);
  await render(resource([['a',null]]));assert.equal(status.phase,'unavailable');assert.equal(status.pendingProtocols,2,'unknown is not a confirmed resolution');
  await render(resource([['a',0],['c',0]]));assert.equal(status.pendingProtocols,0);assert.equal(importReviewStatusLabel(status),'No incoming data pending review');
  await render(resource([['a',5]]));await render({loading:true,data:null},'other-project');assert.equal(status.pendingProtocols,null,'previous project cannot supply a pending badge');
 }finally{await act(()=>view.unmount());}
});
test('Review import dot survives opening, closing and remounting, then clears only with resolved authority',async()=>{
 const h=await createWorkflowHarness(),Component=await h.component('ProtocolSuggestion');
 window.addEventListener=()=>{};window.removeEventListener=()=>{};
 const {ImportSuggestions}=await h.module("protocol-overview/ui/ProtocolSuggestion.jsx");
 const jobs=[{job_uuid:'finished',status:'complete',finished_at:'2026-10-02T10:00:00Z',source:'fixture.h5'}];
 const pending={pendingProtocols:2,phase:'ready'};
 const props={jobs,reviewStatus:pending};
 try{
  await h.mount(ImportSuggestions,props);
  const button=()=>h.root.findByProps({'aria-haspopup':'dialog'});
  assert.match(button().props.className,/has-pending/);assert.match(button().props['aria-label'],/2 protocols/);
  await h.act(()=>button().props.onClick());assert.equal(h.root.findAllByProps({className:'import-review-dot'}).length,1);
  await h.act(()=>h.root.findByProps({'aria-label':'Close import review'}).props.onClick());assert.match(button().props.className,/has-pending/);
  await h.render(Component,{suggestion:null});await h.render(ImportSuggestions,props);assert.match(button().props.className,/has-pending/);
  await h.render(ImportSuggestions,{...props,reviewStatus:{pendingProtocols:2,phase:'loading'}});assert.match(button().props.className,/has-pending/);assert.match(button().props['aria-label'],/last confirmed/);
  await h.render(ImportSuggestions,{...props,reviewStatus:{pendingProtocols:0,phase:'ready'}});assert.doesNotMatch(button().props.className,/has-pending/);assert.equal(h.root.findAllByProps({className:'import-review-dot'}).length,0);
  await h.render(ImportSuggestions,{...props,reviewStatus:{pendingProtocols:null,phase:'unavailable'}});assert.match(button().props['aria-label'],/unavailable/);assert.doesNotMatch(button().props['aria-label'],/No incoming/);
  assert.equal(h.fixture.requests.filter(r=>r.path.includes('workbench')).length,0,'presenter adds no queue request');
 }finally{await h.close();}
});
test('App passes its existing Workbench summary to the ImportPage launcher without another request',async()=>{
 const h=await createWorkflowHarness();h.fixture.route={page:'import',key:'import-status'};
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/workbench/summary'?resource([['protocol-A',4]]).data:fallback();
 try{
  await h.mount();await h.waitFor(()=>h.root.findAll(node=>node.type==='import-suggestions'&&node.props.reviewStatus?.phase==='ready').length>0);
  const summary=h.root.findByType('import-suggestions');assert.deepEqual(summary.props.reviewStatus,{pendingProtocols:1,phase:'ready'});
  assert.equal(h.fixture.requests.filter(r=>r.path==='/workbench/summary').length,1);
 }finally{await h.close();}
});
