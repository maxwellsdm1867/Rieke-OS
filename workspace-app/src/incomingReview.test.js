import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptIncoming,exportIncoming,reviewKey,reviewWorklist,currentProposalCellCount,currentProposalCellBadge} from './incomingReview.js';
const item={protocol_uuid:'protocol',candidate_revision_uuid:'candidate',status:'pending',baseline_binding_version:2,diff_counts:{added:5,removed:0,changed:0},diff_summary:{cell_changes:{counts:{added:1,removed:0,updated:2}},current:{cells:3,epochs:30,acquisition_protocols:1},proposed:{cells:4,epochs:35,acquisition_protocols:1}}};
const fresh={...item,expected_binding_version:2,expected_query_revision:'query',compatibility:{compatible:true}};
const binding={revision_uuid:'candidate',version:3};
test('worklists only contain authoritative active records and never expand by protocol name',()=>{
 const other={...item,protocol_uuid:'other',candidate_revision_uuid:'different'};
 assert.deepEqual(reviewWorklist({suggestions:[item,other,{...item,status:'superseded'}]},[reviewKey(item)]),[item]);
 assert.equal(currentProposalCellCount(item),3);
 assert.equal(currentProposalCellBadge(item),'3 cells');
 assert.equal(currentProposalCellCount({...item,diff_summary:{cell_changes:{added:[{}]}}}),null);
 assert.equal(currentProposalCellBadge({...item,status:'stale'}),'Refresh');
});
test('acceptance checks exact fresh comparison, compatibility and fenced receipt',async()=>{
 const calls=[];
 const result=await acceptIncoming(item,item,async(path,options)=>{calls.push({path,body:options.body});return path.endsWith('compare-to-protocol')?fresh:{binding,event_uuid:'event'};});
 assert.deepEqual(result.receipt.binding,binding);
 assert.deepEqual(calls[1].body,{protocol_uuid:'protocol',expected_binding_version:2,expected_query_revision:'query'});
 const changed={...fresh,diff_counts:{...fresh.diff_counts,added:6}};
 let writes=0;
 const refresh=await acceptIncoming(item,item,async()=>{writes++;return changed;});
 assert.equal(writes,1);assert.equal(refresh.comparison,changed);
 await assert.rejects(()=>acceptIncoming(item,item,async()=>({...fresh,compatibility:{compatible:false}})),/Protocol ID/);
});
test('authoritative existing binding reconciles interrupted apply without replay',async()=>{
 let requests=0;
 const result=await acceptIncoming(item,item,async()=>{requests++;return {...fresh,binding};});
 assert.equal(requests,1);assert.equal(result.reconciled,true);assert.deepEqual(result.receipt.binding,binding);
});
test('failed or incomplete acceptance is ambiguous and cannot become an export receipt',async()=>{
 await assert.rejects(()=>acceptIncoming(item,item,async path=>path.endsWith('compare-to-protocol')?fresh:{}),error=>error.acceptanceUnconfirmed===true);
});
test('export retry has no membership write and uses immutable hash plus authoritative artifact receipt',async()=>{
 const candidate={revision_uuid:'candidate',recipe:{full_recipe_sha256:'full-hash'}};
 const calls=[];const request=async(path,options)=>{calls.push({path,body:options.body});if(calls.length===1)throw Error('source unavailable');return {dataset_uuid:'artifact',download_url:'/download',epoch_count:35};};
 await assert.rejects(()=>exportIncoming(candidate,{format:'wheeler-sqlite',name:' Test '},request),/source unavailable/);
 const result=await exportIncoming(candidate,{format:'wheeler-sqlite',name:' Test '},request);
 assert.equal(result.dataset_uuid,'artifact');assert.equal(calls.length,2);
 for(const call of calls){assert.equal(call.path,'/explore/revisions/candidate/exports');assert.deepEqual(call.body,{format:'wheeler-sqlite',expected_recipe_sha256:'full-hash',name:'Test'});}
 await assert.rejects(()=>exportIncoming(candidate,{format:'wheeler-sqlite'},async()=>({})),/artifact receipt/);
});
