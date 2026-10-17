import test from 'node:test';
import assert from 'node:assert/strict';
import {pendingProtocolSuggestions,suggestionBadge,importCompletionKey,sameSuggestionComparison,sourceMergeRequest,mergedSourceKey,rememberMergedSource,withoutMergedSources} from "./protocol-overview/protocolSuggestions.js";
import {datedCellLabel} from './recording-import/recordingIdentity.js';

test('only persisted pending candidates produce update badges',()=>{
  const source=[{protocol_uuid:'mean',candidate_revision_uuid:'m',status:'applied'},{protocol_uuid:'history',candidate_revision_uuid:'h',status:'pending'},{protocol_uuid:'old',candidate_revision_uuid:'o',status:'superseded'}];
  assert.deepEqual(pendingProtocolSuggestions({suggestions:source}).map(item=>item.protocol_uuid),['history']);
  assert.deepEqual(pendingProtocolSuggestions({suggestions:[{status:'pending'}]}),[]);
  assert.equal(suggestionBadge({diff_summary:{delta:{cells:2}},diff_counts:{added:72}}),'+2 cells');
  assert.equal(suggestionBadge({diff_summary:{delta:{cells:0}},diff_counts:{added:1}}),'+1 epoch');
  assert.equal(suggestionBadge({diff_counts:{removed:2}}),'Update');
});
test('completion fingerprint ignores progress updates and detects terminal transitions once',()=>{
  assert.equal(importCompletionKey([{job_uuid:'a',status:'queued'}]),'');
  assert.equal(importCompletionKey([{job_uuid:'a',status:'validating'}]),'');
  const completed={job_uuid:'a',status:'complete',finished_at:'2026-09-27'};
  assert.equal(importCompletionKey([completed]),importCompletionKey([{...completed,progress:100}]));
  assert.notEqual(importCompletionKey([completed]),importCompletionKey([]));
});
test('fresh compare must match displayed totals before one-click apply proceeds',()=>{
  const initial={baseline_binding_version:1,expected_binding_version:1,diff_counts:{added:72,removed:0,changed:0},diff_summary:{current:{cells:2,epochs:101,acquisition_protocols:1},proposed:{cells:4,epochs:173,acquisition_protocols:1}}};
  assert.equal(sameSuggestionComparison(initial,structuredClone(initial)),true);
  const changed=structuredClone(initial);changed.diff_summary.current.epochs=102;
  assert.equal(sameSuggestionComparison(initial,changed),false);
  changed.diff_summary.current.epochs=101;changed.diff_counts.removed=1;
  assert.equal(sameSuggestionComparison(initial,changed),false);
});
test('dated cell labels distinguish repeated cell numbers without changing IDs',()=>{
  assert.equal(datedCellLabel({cell_label:'Cell3',date:'2026-09-23'}),'2026-09-23 · Cell3');
  assert.equal(datedCellLabel({label:'Cell3',date:'2026-09-24'},true),'2026-09-24 · Cell3');
  assert.equal(datedCellLabel({cell_label:'Cell1',start_time:'2026-09-23T10:00:00Z'}),'2026-09-23 · Cell1');
  assert.equal(datedCellLabel({label:'2026-09-23 · Cell3',date:'2026-09-23'},true),'2026-09-23 · Cell3');
  assert.equal(datedCellLabel({cell_label:'Cell1'}),'Date not recorded · Cell1');
});
test('stale candidates remain actionable as refresh notices, never new-data count badges',async()=>{
  const {activeProtocolSuggestions}=await import("./protocol-overview/protocolSuggestions.js");
  const stale={protocol_uuid:'p',candidate_revision_uuid:'r',status:'stale',diff_summary:{delta:{cells:5}}};
  assert.deepEqual(activeProtocolSuggestions({suggestions:[stale]}),[stale]);
  assert.deepEqual(pendingProtocolSuggestions({suggestions:[stale]}),[]);
  assert.equal(suggestionBadge(stale),'Refresh');
});
test('import attempt notice follows actual job state rather than staying queued',async()=>{
  const {importAttemptNotice}=await import("./protocol-overview/protocolSuggestions.js");
  assert.match(importAttemptNotice({status:'queued'}).message,/queued/);
  assert.equal(importAttemptNotice({status:'validating'}).pending,true);
  assert.equal(importAttemptNotice({status:'complete'}).pending,false);
  assert.match(importAttemptNotice({status:'complete'}).message,/main catalog/);
  assert.doesNotMatch(importAttemptNotice({status:'complete'}).message,/queued/);
  assert.match(importAttemptNotice({status:'duplicate'}).message,/No duplicate data/);
  assert.equal(importAttemptNotice({status:'failed'}).failed,true);
});
test('same counts with a different working binding require a refreshed visible comparison',()=>{
  const displayed={baseline_binding_version:3,diff_counts:{added:72,removed:0,changed:0},diff_summary:{current:{cells:2,epochs:101,acquisition_protocols:1},proposed:{cells:4,epochs:173,acquisition_protocols:1}}};
  const fresh={...structuredClone(displayed),expected_binding_version:4,expected_query_revision:'revision-4'};
  assert.equal(sameSuggestionComparison(displayed,fresh),false);
  // Once this comparison has been shown, a second click may proceed only if
  // both membership version and curation/query revision remain unchanged.
  assert.equal(sameSuggestionComparison(fresh,structuredClone(fresh)),true);
  assert.equal(sameSuggestionComparison(fresh,{...fresh,expected_query_revision:'changed-tags'}),false);
  assert.equal(sameSuggestionComparison(fresh,{...fresh,expected_binding_version:5}),false);
  assert.equal(sameSuggestionComparison({...displayed,baseline_binding_version:undefined},fresh),false);
});

test('approval rechecks displayed candidate and sends both concurrency guards',async()=>{
  const {approveProtocolSuggestion}=await import("./protocol-overview/protocolSuggestions.js");
  const suggestion={protocol_uuid:'p',candidate_revision_uuid:'r'};
  const shown={expected_binding_version:2,expected_query_revision:'q',diff_counts:{added:3,removed:0,changed:0},diff_summary:{current:{cells:1,epochs:2},proposed:{cells:2,epochs:5}}};
  const calls=[];
  const result=await approveProtocolSuggestion(suggestion,shown,async(path,options)=>{
    calls.push({path,body:options.body});
    return path.endsWith('compare-to-protocol')?shown:{binding:{revision_uuid:'r',version:3}};
  });
  assert.equal(result.applied,true);
  assert.deepEqual(calls[1].body,{protocol_uuid:'p',expected_binding_version:2,expected_query_revision:'q'});
});
test('changed bulk approval is held for visible review without mutating dataset',async()=>{
  const {approveProtocolSuggestion}=await import("./protocol-overview/protocolSuggestions.js");
  const shown={expected_binding_version:2,expected_query_revision:'q',diff_counts:{added:3}};
  const fresh={...shown,expected_binding_version:3};
  let calls=0;
  const result=await approveProtocolSuggestion({protocol_uuid:'p',candidate_revision_uuid:'r'},shown,async()=>{calls++;return fresh;});
  assert.equal(calls,1);
  assert.equal(result.applied,false);
  assert.equal(result.comparison,fresh);
});
test('approval refuses invalid comparison and ambiguous apply receipt',async()=>{
  const {approveProtocolSuggestion}=await import("./protocol-overview/protocolSuggestions.js");
  const candidate={protocol_uuid:'p',candidate_revision_uuid:'r'};
  await assert.rejects(()=>approveProtocolSuggestion(candidate,{},async()=>({expected_binding_version:1})),/valid dataset version/);
  const shown={expected_binding_version:1,expected_query_revision:'q'};
  await assert.rejects(()=>approveProtocolSuggestion(candidate,shown,async path=>path.endsWith('compare-to-protocol')?shown:{binding:{revision_uuid:'other',version:2}}),/complete receipt/);
});
test('card hold requests exactly one pending recording in its frozen candidate',()=>{
  const card={protocol_uuid:'p',candidate_revision_uuid:'c',source_sha256:'s',status:'pending',diff_counts:{added:3}};
  assert.deepEqual(sourceMergeRequest(card),{kind:'merge_source',candidate_revision_uuid:'c',source_sha256:'s'});
  for(const change of [{status:'stale'},{status:'applied'},{status:'superseded'},{diff_counts:{added:0}},{diff_counts:{added:null}},{source_sha256:''},{source_sha256:undefined},{candidate_revision_uuid:null}])
    assert.equal(sourceMergeRequest({...card,...change}),null,JSON.stringify(change));
  assert.equal(sourceMergeRequest(null),null);
});
test('only a verified source receipt retires its exact card while suggestions refresh',()=>{
  const receipt={mode:'source',protocol_uuid:'p',candidate_revision_uuid:'c',source_sha256:'s',event_uuid:'event'};
  const key=mergedSourceKey('project',receipt);assert.ok(key);
  for(const change of [{mode:'selected'},{event_uuid:''},{source_sha256:undefined},{protocol_uuid:null}])assert.equal(mergedSourceKey('project',{...receipt,...change}),null);
  assert.equal(mergedSourceKey('project',null),null);assert.equal(mergedSourceKey(null,receipt),null);
  const rows=[{protocol_uuid:'p',candidate_revision_uuid:'c',source_sha256:'s',status:'pending'},{protocol_uuid:'p',candidate_revision_uuid:'c',source_sha256:'other',status:'pending'},
    {protocol_uuid:'q',candidate_revision_uuid:'c',source_sha256:'s',status:'pending'},{protocol_uuid:'p',candidate_revision_uuid:'next',source_sha256:'s',status:'pending'}];
  const data={suggestions:rows,approved_history:[{protocol_uuid:'p',candidate_revision_uuid:'c',source_sha256:'s',status:'applied'}]};
  assert.equal(withoutMergedSources(data,'project',[]),data);
  const shown=withoutMergedSources(data,'project',[key]);
  assert.deepEqual(shown.suggestions,rows.slice(1),'other recordings, protocols and candidates stay pending');assert.equal(shown.approved_history,data.approved_history);
  assert.equal(withoutMergedSources(data,'other-project',[key]),data,'another project is unaffected');
  assert.equal(withoutMergedSources(null,'project',[key]),null);
  assert.deepEqual(rememberMergedSource(['a'],null),['a']);assert.deepEqual(rememberMergedSource(['a'],'a'),['a']);
  assert.deepEqual(rememberMergedSource(['a','b'],'c',2),['b','c']);
});

const pendingQueue=(overrides={})=>({contract_version:1,queue_revision:'q1',pending_epoch_count:755,pending_cell_count:4,eligible_pending_epoch_count:755,eligible_pending_cell_count:4,next_cursor:null,
  capabilities:{cumulative_pending_browse:true,additive_accept:true,frozen_browse:true,drafts:true,incoming_export:true},
  candidates:[
    {candidate_revision_uuid:'a',source_filename:'2026-10-12_F.h5',source_sha256:'sa',eligible_pending_epoch_count:500},
    {candidate_revision_uuid:'b',source_filename:'2026-10-13_A.h5',source_sha256:'sb',eligible_pending_epoch_count:255},
    {candidate_revision_uuid:'c',source_filename:'2026-10-01_old.h5',source_sha256:'sc',status:'conflict',eligible_pending_epoch_count:0},
    {candidate_revision_uuid:'u',kind:'workbench_pending_union',source_filename:'Accumulated incoming',source_sha256:'',eligible_pending_epoch_count:755},
  ],...overrides});
const mainSummary={counts:{epochs:36},cells:[{cell_uuid:'x'},{cell_uuid:'y'},{cell_uuid:'x'}]};

test('pending card model sums the cumulative queue across recordings and lists only mergeable recordings',async()=>{
  const {pendingProtocolSuggestion,mergeAllRequest}=await import('./protocol-overview/protocolSuggestions.js');
  const card=pendingProtocolSuggestion(pendingQueue(),mainSummary,'protocol-A');
  assert.deepEqual(card.diff_summary,{current:{cells:2,epochs:36},proposed:{cells:6,epochs:791},delta:{cells:4,epochs:755}},'older services fall back to pending cells');
  const exact=pendingProtocolSuggestion(pendingQueue({pending_new_cell_count:3}),mainSummary,'protocol-A');
  assert.deepEqual(exact.diff_summary,{current:{cells:2,epochs:36},proposed:{cells:5,epochs:791},delta:{cells:3,epochs:755}},'a pending cell already in main is not counted twice');
  assert.equal(exact.pending_cell_count,4);
  const sourced=pendingProtocolSuggestion(pendingQueue({pending_recordings:[{source_sha256:'s1',filename:'2026-09-24_F.h5',epoch_count:443},{source_sha256:'s2',filename:'2026-10-06_F.h5',epoch_count:312},{source_sha256:'s3',filename:'empty.h5',epoch_count:0}]}),mainSummary,'protocol-A');
  assert.deepEqual(sourced.recordings,['2026-09-24_F.h5','2026-10-06_F.h5'],'the pending epochs\' own recordings, not the proposals that listed them');
  assert.deepEqual(card.diff_counts,{added:755,removed:0,changed:0});
  assert.deepEqual(card.recordings,['2026-10-12_F.h5','2026-10-13_A.h5'],'nothing-mergeable and union rows contribute no recording');
  assert.equal(card.status,'pending');assert.equal(card.protocol_uuid,'protocol-A');
  assert.deepEqual(mergeAllRequest(card),{kind:'merge_all',queue_revision:'q1',origin:'protocol-overview'});
});
test('pending card model is hidden at zero or unknown mergeable counts and uses eligible fields',async()=>{
  const {pendingProtocolSuggestion,mergeAllRequest}=await import('./protocol-overview/protocolSuggestions.js');
  assert.equal(pendingProtocolSuggestion(pendingQueue({eligible_pending_epoch_count:0,eligible_pending_cell_count:0}),mainSummary,'protocol-A'),null,'non-mergeable pending is not pending');
  assert.equal(pendingProtocolSuggestion(pendingQueue({eligible_pending_epoch_count:null}),mainSummary,'protocol-A'),null);
  assert.equal(pendingProtocolSuggestion(null,mainSummary,'protocol-A'),null);
  assert.equal(pendingProtocolSuggestion({...pendingQueue(),contract_version:2},mainSummary,'protocol-A'),null);
  const legacy=pendingQueue();delete legacy.eligible_pending_epoch_count;delete legacy.eligible_pending_cell_count;
  assert.equal(pendingProtocolSuggestion(legacy,mainSummary,'protocol-A').pending_epoch_count,755,'older services fall back to totals');
  const unknownMain=pendingProtocolSuggestion(pendingQueue(),{counts:{},cells:[{}]},'protocol-A');
  assert.deepEqual(unknownMain.diff_summary.proposed,{cells:null,epochs:null},'unknown main never becomes a partial total');
  assert.equal(mergeAllRequest(pendingProtocolSuggestion(pendingQueue({capabilities:{cumulative_pending_browse:false,additive_accept:true}}),mainSummary,'protocol-A')),null);
  assert.deepEqual(pendingProtocolSuggestion(pendingQueue({main_blocked_reason:'Main contains epochs whose recorded metadata changed; save the query again to update main.',eligible_pending_epoch_count:0}),mainSummary,'protocol-A'),{blocked:'Main contains epochs whose recorded metadata changed; save the query again to update main.',queue_revision:'q1'});
});
