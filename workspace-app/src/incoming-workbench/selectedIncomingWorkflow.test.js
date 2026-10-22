import test from 'node:test';
import assert from 'node:assert/strict';
import {exactSelectedIds,selectedReview,prepareSelectedIncoming,selectedViewFilters} from './selectedIncomingWorkflow.js';
const context=(decisions=[])=>({candidate_scope_revision:'scope-0',draft:{draft_version:0,selection_mode:'all',decisions,decisions_total:decisions.length,decisions_truncated:false}});
const counts=count=>({preview_sha256:'preview',expected_binding_version:4,expected_query_revision:'query',selected_epoch_count:count,accepted_epoch_count:count,already_present_epoch_count:0,retained_epoch_count:100,next_epoch_count:100+count,accepted_cell_count:1});
function server(initial){let current=initial;const calls=[];return {calls,get current(){return current;},request:async(path,options)=>{calls.push({path,...options});if(path.endsWith('/draft')){assert.equal(options.body.expected_version,current.draft.draft_version);assert.equal(options.body.expected_candidate_scope_revision,current.candidate_scope_revision);const decisions=new Map(current.draft.decisions.map(v=>[v.epoch_uuid,v]));for(const value of options.body.decisions)decisions.set(value.epoch_uuid,{selected:false,reviewed:false,excluded:false,...decisions.get(value.epoch_uuid),...value});current={...current,candidate_scope_revision:`scope-${current.draft.draft_version+1}`,draft:{...current.draft,draft_version:current.draft.draft_version+1,selection_mode:options.body.selection_mode,decisions:[...decisions.values()],decisions_total:decisions.size}};return current;}assert.ok(path.endsWith('/preview'));assert.equal(options.body.mode,'selected');assert.equal(options.body.expected_draft_version,current.draft.draft_version);assert.equal(options.body.expected_candidate_scope_revision,current.candidate_scope_revision);return counts(current.draft.decisions.filter(v=>v.selected&&v.reviewed&&!v.excluded).length);}};}
test('selection has no focused-row fallback and rejects duplicates and unavailable IDs',()=>{for(const ids of [[],null,['a','a'],[null]])assert.throws(()=>exactSelectedIds(ids));assert.deepEqual(exactSelectedIds(['a']),['a']);assert.ok(Object.isFrozen(exactSelectedIds(['a'])));});
test('review is explicit and excluded selection fails before any save or preview',async()=>{const s=server(context([{epoch_uuid:'excluded',excluded:true}]));await assert.rejects(prepareSelectedIncoming({root:'/c',context:s.current,ids:['a']},s.request),/Review the selected/);await assert.rejects(prepareSelectedIncoming({root:'/c',context:s.current,ids:['excluded'],review:true},s.request),/excluded/);assert.deepEqual(s.calls,[]);});
test('complete actor draft is required; missing or truncated decisions cannot imply reviewed or zero',()=>{for(const draft of [{draft_version:1},{...context().draft,decisions_truncated:true},{...context().draft,decisions_total:1}])assert.throws(()=>selectedReview({draft},['a']),/complete review draft/);});
test('explicit review replaces selected membership only, retains other reviews/exclusions, and never accepts',async()=>{const s=server(context([{epoch_uuid:'prior',selected:true,reviewed:true,excluded:true},{epoch_uuid:'keep',selected:false,reviewed:true,excluded:false}]));const preview=await prepareSelectedIncoming({root:'/c',context:s.current,ids:['a','b'],review:true},s.request);assert.equal(preview.selected_epoch_count,2);assert.deepEqual(s.current.draft.decisions.find(v=>v.epoch_uuid==='prior'),{epoch_uuid:'prior',selected:false,reviewed:true,excluded:true});assert.deepEqual(s.current.draft.decisions.find(v=>v.epoch_uuid==='keep'),{epoch_uuid:'keep',selected:false,reviewed:true,excluded:false});assert.deepEqual(s.calls.map(v=>v.path),['/c/draft','/c/preview']);assert.ok(s.calls[0].body.decisions.every(v=>!Object.hasOwn(v,'excluded')));});
test('already reviewed intent writes no review flags and uses the refreshed save fences',async()=>{const s=server(context([{epoch_uuid:'a',selected:false,reviewed:true,excluded:false}]));await prepareSelectedIncoming({root:'/c',context:s.current,ids:['a']},s.request);assert.deepEqual(s.calls[0].body.decisions,[{epoch_uuid:'a',selected:true}]);assert.equal(s.calls[1].body.expected_draft_version,1);});
test('multi-page intent batches exact flags and failure is never replayed or previewed',async()=>{const ids=Array.from({length:501},(_,i)=>`id-${i}`),s=server(context());let calls=0;await assert.rejects(prepareSelectedIncoming({root:'/c',context:s.current,ids,review:true},async(...args)=>{if(++calls===2)throw Error('reply lost');return s.request(...args);}),/reply lost/);assert.equal(calls,2);assert.equal(s.calls.length,1);assert.equal(s.current.draft.decisions.length,250);});
test('a fresh preview cannot silently omit one selected epoch',async()=>{const s=server(context());await assert.rejects(prepareSelectedIncoming({root:'/c',context:s.current,ids:['a','b'],review:true},async(path,opts)=>path.endsWith('/preview')?counts(1):s.request(path,opts)),/every selected epoch/);});
test('View selected keeps all 1000 exact identities in bounded clauses and preserves existing filters',()=>{const ids=Array.from({length:1000},(_,i)=>`00000000-0000-0000-0000-${String(i).padStart(12,'0')}`),original={cell_type:'ON',metadata_predicate:JSON.stringify({field:'date',operator:'eq',value:'2026-10-01'})};const result=selectedViewFilters(original,ids),predicate=JSON.parse(result.metadata_predicate);assert.equal(result.cell_type,'ON');assert.deepEqual(predicate.all[0],JSON.parse(original.metadata_predicate));assert.deepEqual(predicate.all[1].any.flatMap(v=>v.value),ids);assert.ok(predicate.all[1].any.every(v=>JSON.stringify(v.value).length<4096));assert.ok(!original.metadata_predicate.includes('epoch'));});

test('large selection identities have no user cardinality ceiling',()=>{const ids=Array.from({length:20000},(_,i)=>String(i));assert.deepEqual(exactSelectedIds(ids),ids);});

test('disk checkpoint omits oversized Workbench selections but preserves live UUIDs and every recovery field',async()=>{
 const {compactWorkbenchSelections}=await import('./selectedIncomingWorkflow.js');
 const ids=Array.from({length:100000},(_,i)=>`00000000-0000-0000-0000-${String(i).padStart(12,'0')}`),recovery={selected:ids,operation:'op',preview:{preview_sha256:'sealed'},unconfirmed:true,acceptPending:true,receipt:{event_uuid:'event'},exportState:{acceptOperation:'export-op',prepared:{token:'export'}},viewer:{focused:'epoch'}};
 const protocol={workbench:{active:'candidate',drafts:{candidate:recovery},cumulative:{prepared:{candidate_revision_uuid:'union'},drafts:{union:recovery}}}};
 const checkpoint={sessions:[['route',protocol]],protocolSessions:[['protocol',protocol]],sourceMerge:{operation:'separate'},unrelated:{selected:ids}};
 const result=compactWorkbenchSelections(checkpoint);
 assert.equal(protocol.workbench.drafts.candidate.selected,ids);assert.equal(ids.length,100000);assert.equal(result.unrelated,checkpoint.unrelated);assert.equal(result.sourceMerge,checkpoint.sourceMerge);
 for(const value of [result.sessions[0][1],result.protocolSessions[0][1]])for(const draft of [value.workbench.drafts.candidate,value.workbench.cumulative.drafts.union]){assert.deepEqual(draft,{...recovery,selected:[],selection_omitted_count:100000});}
 assert.ok(JSON.stringify({...result,unrelated:null}).length<2*1024*1024);
 assert.equal(compactWorkbenchSelections({sessions:[['s',{workbench:{drafts:{c:{selected:['one']}}}}]]}).sessions[0][1].workbench.drafts.c.selected[0],'one');
});

test('checkpoint prunes unreachable cumulative candidates but keeps current and recovery candidates',async()=>{
 const {pruneCumulativeSession,workbenchDraftNeedsRecovery}=await import('./selectedIncomingWorkflow.js');
 const scope=id=>({candidate_revision_uuid:id,context:{protocol:{padding:'x'.repeat(3000)}}});
 const drafts={current:{selected:['a']},stale:{selected:['b']},pending:{acceptPending:true,operation:'op-1'},unconfirmed:{unconfirmed:true,operation:'op-2'},
  receipt:{receipt:{event_uuid:'e'}},exported:{receipt:{event_uuid:'f'},exportState:{exported:true}},exporting:{exportState:{pending:true}}};
 const scopes=Object.fromEntries(Object.keys(drafts).map(key=>[key,scope(key)]));
 const pruned=pruneCumulativeSession({prepared:scope('current'),drafts,scopes,other:'kept'});
 assert.deepEqual(Object.keys(pruned.drafts).sort(),['current','exporting','pending','receipt','unconfirmed']);
 assert.deepEqual(Object.keys(pruned.scopes).sort(),['current','exporting','pending','receipt','unconfirmed']);
 assert.equal(pruned.drafts.pending,drafts.pending);assert.equal(pruned.other,'kept');
 assert.equal(workbenchDraftNeedsRecovery(drafts.stale),false);assert.equal(workbenchDraftNeedsRecovery(drafts.exported),false);
 assert.equal(pruneCumulativeSession(null),null);
});

test('oversized checkpoints drop oldest history views but never current, latest or recovery sessions',async()=>{
 const {compactWorkspaceCheckpoint}=await import('./selectedIncomingWorkflow.js');
 const view=(n,extra={})=>({tab:'workbench',padding:'v'.repeat(20000),n,...extra});
 const recovery=view('recovery',{workbench:{drafts:{c:{unconfirmed:true,operation:'op'}}}});
 const sessions=[['old-recovery',recovery],...Array.from({length:120},(_,i)=>[`h${i}`,view(i)]),['current',view('current')]];
 const checkpoint={route:{key:'current',page:'protocol',protocol:'p'},sessions,protocolSessions:[['p',view('latest')]],sourceMerge:{operation:'kept'}};
 const result=compactWorkspaceCheckpoint(checkpoint,{historyBytes:400*1024});
 const keys=result.sessions.map(([key])=>key);
 assert.ok(new TextEncoder().encode(JSON.stringify(result)).length<=400*1024);
 assert.ok(keys.includes('current')&&keys.includes('old-recovery'));
 assert.equal(keys.at(-1),'current');assert.ok(keys.includes('h119'));assert.ok(!keys.includes('h0'),'oldest history goes first');
 assert.equal(result.history_sessions_omitted,120-keys.filter(key=>key.startsWith('h')).length);
 assert.deepEqual(result.protocolSessions,checkpoint.protocolSessions);assert.equal(result.sourceMerge,checkpoint.sourceMerge);
 assert.equal(checkpoint.sessions.length,122,'live history is not mutated');
 const small={route:{key:'a'},sessions:[['a',view('a')]],protocolSessions:[]};
 assert.deepEqual(compactWorkspaceCheckpoint(small),small);
});

test('inactive author recovery survives checkpoint pressure and its large selections are compacted',async()=>{
 const {compactWorkspaceCheckpoint}=await import('./selectedIncomingWorkflow.js');
 const draft={selected:Array.from({length:4000},(_,i)=>`epoch-${i}`),unconfirmed:true,operation:'author-a-operation',preview:{preview_sha256:'sealed'}};
 const checkpoint={route:{key:'current'},sessions:[['old',{workbench:{sessionActor:'b',sessionsByActor:{a:{drafts:{candidate:draft}},b:{drafts:{}}}}}],['current',{}]]};
 const result=compactWorkspaceCheckpoint(checkpoint,{historyBytes:100,selectionBytes:100});
 assert.equal(result.sessions.length,2,'inactive author recovery protects the old view');
 const restored=result.sessions[0][1].workbench.sessionsByActor.a.drafts.candidate;
 assert.deepEqual(restored.selected,[]);assert.equal(restored.selection_omitted_count,4000);
 assert.equal(restored.operation,'author-a-operation');assert.deepEqual(restored.preview,draft.preview);assert.equal(restored.unconfirmed,true);
 assert.equal(draft.selected.length,4000,'live selection remains intact');
});

test('repeated Undo checkpoints prune completed scopes while preserving current selection and independent recovery',async()=>{
 const {compactWorkspaceCheckpoint,workbenchDraftNeedsRecovery}=await import('./selectedIncomingWorkflow.js');
 const scope=id=>({candidate_revision_uuid:id,context:{draft:{decisions:Array.from({length:334},(_,i)=>({epoch_uuid:`epoch-${i}`,selected:true,reviewed:true,excluded:false}))}}});
 const completed=Object.fromEntries(Array.from({length:20},(_,i)=>[`undone-${i}`,{receipt:{operation_uuid:`merge-${i}`,undone:true},selected:['old-epoch']} ]));
 const independent={finish:{finishOperation:{operationUuid:'finish-op',context:{candidate_scope_revision:'exact-scope',draft:{draft_version:7}}}},
  uncertain:{receipt:{undone:true},unconfirmed:true,operation:'accept-op',preview:{preview_sha256:'exact-preview'}},
  accepting:{receipt:{undone:true},acceptPending:true,operation:'pending-op'},
  exporting:{receipt:{undone:true},exportState:{pending:true,operation:'export-op'}},
  preparedExport:{receipt:{undone:true},exportState:{prepared:{export_uuid:'prepared'}}},
  acceptedExport:{receipt:{undone:true},exportState:{acceptOperation:'export-accept-op'}},
  accepted:{receipt:{operation_uuid:'still-accepted'}},
  unknown:{receipt:{operation_uuid:'not-proven-undone',undone:'true'}}};
 const current={selected:['epoch-4','epoch-5'],viewer:{focused:'epoch-4'},receipt:{undone:true}};
 const drafts={...completed,...independent,current},scopes=Object.fromEntries(Object.keys(drafts).map(key=>[key,scope(key)]));
 const cumulative={prepared:scope('current'),drafts,scopes};
 const actor={cumulative},workbench={...actor,sessionActor:'author',sessionsByActor:{author:actor}};
 const checkpoint={route:{key:'current'},sessions:[['current',{workbench}]],protocolSessions:[['protocol',{workbench}]]};
 const before=JSON.stringify(checkpoint),result=compactWorkspaceCheckpoint(checkpoint);
 assert.ok(Buffer.byteLength(before)>2*1024*1024,'fixture exceeds native saved-view cap before pruning');
 assert.ok(Buffer.byteLength(JSON.stringify(result))<1536*1024,'completed Undo scopes no longer exhaust the saved-view budget');
 for(const [,value] of [...result.sessions,...result.protocolSessions])for(const saved of [value.workbench.cumulative,value.workbench.sessionsByActor.author.cumulative]){
  assert.deepEqual(Object.keys(saved.drafts).sort(),[...Object.keys(independent),'current'].sort());
  assert.deepEqual(Object.keys(saved.scopes).sort(),Object.keys(saved.drafts).sort());
  assert.deepEqual(saved.drafts.current,current,'same-candidate selection remains intact');
  for(const [key,draft] of Object.entries(independent))assert.deepEqual(saved.drafts[key],draft,'recovery fences and operations remain exact');
 }
 assert.equal(workbenchDraftNeedsRecovery({receipt:{undone:true}}),false);
 assert.equal(JSON.stringify(checkpoint),before,'live sessions are not mutated');
 const history=compactWorkspaceCheckpoint({route:{key:'current'},sessions:[['old',{padding:'x'.repeat(4000),workbench:{drafts:{old:{receipt:{undone:true}}}}}],['current',{}]]},{historyBytes:1000});
 assert.deepEqual(history.sessions,[['current',{}]],'old undone history no longer blocks ordinary history eviction');
});
