import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';

// Request ledger through the mounted Inspector, product hooks and shared cache.
// Trace samples follow structure/source events, never curation or tag receipts.
const props={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-0',expected_binding_version:2,cells:[{cell_uuid:'cell-0',date:'2026-09-29',label:'Cell 0',epochs:500}]},filters:{},revision:0,structureRevision:0,initialEpochUuid:'epoch-0'};
const stream={uuid:'s',kind:'responses',device:'Amp1',sample_count:1000,sample_rate:10000,units:'pA'};
function withStreams(h){
 h.fixture.respond=async(url,_options,base)=>{
  const path=url.pathname.replace(/^\/api/,'');
  if(/\/trace$/.test(path)){const count=Number(url.searchParams.get('count'));return {epoch_uuid:path.split('/')[2],stream_uuid:'s',start:0,count,total_samples:1000,decimated:false,sample_rate:10000,units:'pA',source_sha256:'a'.repeat(64),values:new Array(count).fill(0)};}
  const value=base(),add=epoch=>({...epoch,source_sha256:'a'.repeat(64),streams:[stream]});
  if(value?.epochs)return {...value,epochs:value.epochs.map(add)};
  if(value?.epoch_uuid&&value.streams)return add(value);
  return value;
 };
}
const traces=(h,from)=>h.fixture.requests.slice(from).filter(request=>/\/trace\?/.test(request.path));
async function openCell(h){
 const date=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date');
 await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
 const cell=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell');
 await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
 await h.waitFor(()=>h.root.findAllByType('button').some(node=>node.props['aria-label']?.startsWith('Inspect ')));
}

test('one curation change re-reads no trace samples; a structure change re-warms them',async()=>{
 const h=await createWorkflowHarness({total:500,liveMetadata:false});
 try{
  withStreams(h);
  const Inspector=await h.component('Inspector');
  await h.mount(Inspector,props);await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
  await openCell(h);await h.settle(500);
  const warmed=traces(h,0).length;
  assert.ok(warmed>=20,`neighbor trace windows were warmed (${warmed})`);
  const before=h.fixture.requests.length;
  // A curation receipt advances the display clock only.
  await h.render(Inspector,{...props,revision:1,structureRevision:0});await h.settle(600);
  assert.deepEqual(traces(h,before).map(request=>request.path),[],'curation change sends zero trace GETs');
  const structural=h.fixture.requests.length;
  await h.render(Inspector,{...props,revision:2,structureRevision:1});await h.settle(600);
  assert.ok(traces(h,structural).length>0,'structure/source events still invalidate trace samples');
 }finally{await h.close();}
});

test('a tag receipt during trace warming neither drops nor repeats trace reads',async()=>{
 const h=await createWorkflowHarness({total:500,liveMetadata:false});
 try{
  withStreams(h);
  h.fixture.delay=record=>/\/trace\?/.test(record.path)?20:0;
  const {epochResourceCache}=await h.module('resourceCache.js');
  const Inspector=await h.component('Inspector');
  await h.mount(Inspector,props);await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
  await openCell(h);
  await h.waitFor(()=>traces(h,0).length>=4);
  // Confirmed receipt for an unrelated epoch while prefetch is in flight.
  epochResourceCache.invalidateAnnotations({version:1,targets:[{target_kind:'epoch',target_uuid:'epoch-499'}]});
  await h.settle(1500);
  const paths=traces(h,0).map(request=>request.path);
  assert.equal(new Set(paths).size,paths.length,'no trace window is fetched twice');
  const before=h.fixture.requests.length;
  epochResourceCache.invalidateAnnotations({version:1,targets:[{target_kind:'epoch',target_uuid:'epoch-498'}]});
  await h.settle(600);
  assert.deepEqual(traces(h,before).map(request=>request.path),[],'tag receipt sends zero trace GETs');
 }finally{await h.close();}
});
