import test from 'node:test';
import assert from 'node:assert/strict';
import {pendingProtocolSuggestions,suggestionBadge,importCompletionKey,sameSuggestionComparison} from './protocolSuggestions.js';
import {datedCellLabel} from './recordingIdentity.js';

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
  const {activeProtocolSuggestions}=await import('./protocolSuggestions.js');
  const stale={protocol_uuid:'p',candidate_revision_uuid:'r',status:'stale',diff_summary:{delta:{cells:5}}};
  assert.deepEqual(activeProtocolSuggestions({suggestions:[stale]}),[stale]);
  assert.deepEqual(pendingProtocolSuggestions({suggestions:[stale]}),[]);
  assert.equal(suggestionBadge(stale),'Refresh');
});
test('import attempt notice follows actual job state rather than staying queued',async()=>{
  const {importAttemptNotice}=await import('./protocolSuggestions.js');
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
