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
  assert.equal(h.root.findByProps({className:'incoming-workbench'}).findAllByType('h1').length,0,'the existing Workbench tab supplies the title');
  assert.equal(h.root.findByProps({'aria-label':'Workbench'}).props['aria-selected'],true);
  assert.equal(h.root.findByProps({'aria-label':'Protocol workspace views'}).findAllByProps({className:'protocol-view-filter'}).length,0,'Main filter is replaced by the incoming header slot');
  assert.equal(h.root.findByProps({className:'incoming-workbench'}).findAllByProps({className:'incoming-action-bar'}).length,1);
  assert.equal(h.root.findAllByProps({className:'incoming-header-filter'}).length,1);
  assert.ok(h.root.findAllByProps({role:'status'}).some(n=>n.children.join('').includes('No pending incoming recordings')));
 }finally{await h.close();}
});
