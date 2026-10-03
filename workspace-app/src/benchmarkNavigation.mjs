// Product App/Protocol/Inspector mounted-work timings. Not a browser/paint benchmark.
import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const samples=Number(process.argv[2]), output=process.argv[3];
const rows=['first','return'].map(phase=>({id:`ui.mounted.inspector.${phase}`,status:'passed',metrics:{content_ms:[],authority_ms:[]},requests:[]}));
async function ready(h){
 await h.waitFor(()=>{try{return h.viewer.epoch?.epoch_uuid==='epoch-0';}catch{return false;}});
}
async function authority(h){
 await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-0'&&!h.viewer.navigation.loading&&!h.viewer.treePane.listProps.disabled);
 assert.equal(h.fixture.generation,0);
 assert.equal(h.viewer.epoch.cell_uuid,'cell-0');
 assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-0');
}
for(let sample=-1;sample<samples;sample++){
 const h=await createWorkflowHarness({total:500});
 try{
  // Module transform/harness construction excluded; first mount includes React work.
  let mark=performance.now(), before=h.fixture.requests.length;
  await h.mount();await ready(h);const firstContent=performance.now()-mark;
  await authority(h);const firstAuthority=performance.now()-mark;
  if(sample>=0){rows[0].metrics.content_ms.push(firstContent);rows[0].metrics.authority_ms.push(firstAuthority);rows[0].requests.push(h.fixture.requests.length-before);}
  const tab=name=>h.root.findAllByType('button').find(n=>n.props.role==='tab'&&n.props['aria-label']===name);
  assert.ok(tab('Overview'));await h.act(()=>tab('Overview').props.onClick());
  before=h.fixture.requests.length;mark=performance.now();
  assert.ok(tab('Inspect'));await h.act(()=>tab('Inspect').props.onClick());
  await ready(h);const content=performance.now()-mark;
  await authority(h);const current=performance.now()-mark;
  if(sample>=0){rows[1].metrics.content_ms.push(content);rows[1].metrics.authority_ms.push(current);rows[1].requests.push(h.fixture.requests.length-before);}
  assert.equal(h.fixture.requests.filter(r=>r.method!=='GET'&& !r.path.endsWith('/annotations/read')).length,0,'navigation cannot mutate scientific state');
 }finally{await h.close();}
}
writeFileSync(output,JSON.stringify({cases:rows,fixture_cleaned:true,scope:'Mounted product App/Inspector with mock API and trace child; no native layout/scroll/H5/paint qualification'},null,2)+'\n');
