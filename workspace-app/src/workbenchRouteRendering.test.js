import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

for(const entry of ['tab','restored session','reused Workbench route'])test(`Protocol ${entry} mounts the real incoming workspace through the App route`,async()=>{
 const h=await createWorkflowHarness();
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/protocols/protocol-A/workbench')?{contract_version:1,queue_revision:'queue-1',pending_epoch_count:0,pending_cell_count:0,candidates:[],capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}}:fallback();
 try{
  await h.mount(h.Protocol,{id:'protocol-A',projectId:'project',revision:0,...(entry==='reused Workbench route'?{initialWorkbench:{}}:{session:{tab:entry==='tab'?'inspect':'workbench'}})});
  await h.waitFor(()=>h.root.findAllByProps({'aria-label':'Workbench'}).length>0);
  if(entry==='tab')await h.act(()=>h.root.findByProps({'aria-label':'Workbench'}).props.onClick());
  await h.waitFor(()=>h.fixture.requests.some(r=>r.path==='/protocols/protocol-A/workbench?limit=20'));
  await h.settle();
  assert.equal(h.root.findByProps({className:'incoming-workbench'}).findByType('h1').children.join(''),'Needs review');
  assert.ok(h.root.findAllByProps({role:'status'}).some(n=>n.children.join('').includes('No incoming recordings currently await review')));
 }finally{await h.close();}
});
