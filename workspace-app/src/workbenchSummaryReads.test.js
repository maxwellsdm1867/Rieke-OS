import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

test('Workbench defers hidden main-summary annotation refresh until Overview and keeps structural refresh',async()=>{
 const h=await createWorkflowHarness();
 const base={id:'protocol-A',projectId:'project',revision:0,structureRevision:0,initialWorkbench:{},onChange(){}};
 try{
  h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/protocols/protocol-A/workbench'?{contract_version:1,protocol_uuid:'protocol-A',queue_revision:'queue',candidates:[],next_cursor:null,capabilities:{}}:fallback();
  await h.mount(h.Protocol,base);await h.settle(30);
  const summaryCount=()=>h.fixture.requests.filter(record=>record.path==='/protocols/protocol-A').length;
  assert.equal(summaryCount(),1);
  for(let revision=1;revision<=5;revision++){await h.render(h.Protocol,{...base,revision});await h.settle(10);}
  assert.equal(summaryCount(),1,'five annotation revisions trigger no hidden main-summary reads');
  await h.act(()=>h.root.findByProps({'aria-label':'Overview'}).props.onClick());
  await h.waitFor(()=>summaryCount()===2);
  await h.act(()=>h.root.findByProps({'aria-label':'Workbench'}).props.onClick());
  await h.render(h.Protocol,{...base,revision:6,structureRevision:1});
  await h.waitFor(()=>summaryCount()===3);
 }finally{await h.close();}
});
