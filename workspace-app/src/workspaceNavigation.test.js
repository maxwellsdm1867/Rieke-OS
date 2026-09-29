import test from 'node:test';
import assert from 'node:assert/strict';
import {validWorkspaceRoute,makeWorkspaceRoute,routeAddress,resolveProtocolSession,restoredEpochFocus} from './workspaceNavigation.js';

test('workspace history admits local destinations only and preserves exact route identities',()=>{
  const route=makeWorkspaceRoute('protocol',{protocol:'uuid:one'},'visit-1');
  assert.equal(validWorkspaceRoute(route),true);
  assert.equal(routeAddress(route),'#/protocol/uuid%3Aone');
  assert.equal(validWorkspaceRoute({page:'https://example.test',key:'x'}),false);
  assert.equal(validWorkspaceRoute({page:'protocol',key:'x'}),false);
  assert.throws(()=>makeWorkspaceRoute('unknown',{},'x'));
});
test('back restores the precise visited protocol session, not original handoff defaults',()=>{
  const saved={tab:'inspect',filters:{group_label:'NBQX5um'},scope:'cell-date-2',splitOrder:['date','cell'],initialEpoch:'epoch-last',inspector:{focused:'epoch-last',offset:60,treeMode:false}};
  const actual=resolveProtocolSession({saved,inspection:{epoch_uuid:'epoch-first',cell_uuid:'old-cell'},restore:true});
  assert.equal(actual,saved);
  assert.equal(actual.inspector.focused,'epoch-last');
  assert.equal(actual.inspector.offset,60);
  assert.equal(actual.filters.group_label,'NBQX5um');
});
test('explicit new epoch handoff overrides a previous protocol focus while preserving compatible preferences',()=>{
  const saved={tab:'overview',filters:{cell_type:'ON'},format:'wheeler-sqlite',inspector:{focused:'old',offset:120}};
  const result=resolveProtocolSession({saved,inspection:{epoch_uuid:'new',cell_uuid:'new-cell'}});
  assert.equal(result.tab,'inspect');assert.equal(result.inspector.focused,'new');assert.equal(result.inspector.offset,0);
  assert.equal(result.scope,'new-cell');assert.equal(result.format,'wheeler-sqlite');assert.deepEqual(result.filters,{});
});
test('explicit export reuse chooses its saved scope, while back retains edited export settings',()=>{
  const recipe={filters:{group_label:'drug'},format:'epictree-mat',split_order:['cell'],name:'Reused'};
  const saved={tab:'export',filters:{group_label:'wash'},format:'wheeler-sqlite',exportName:'Edited'};
  assert.equal(resolveProtocolSession({saved,recipe}).format,'epictree-mat');
  assert.deepEqual(resolveProtocolSession({saved,recipe}).filters,{group_label:'drug'});
  assert.equal(resolveProtocolSession({saved,recipe,restore:true}),saved);
});

test('explicitly cleared focus does not resurrect the original handoff epoch',()=>{
  assert.equal(restoredEpochFocus({focused:null},'original'),null);
  assert.equal(restoredEpochFocus({},'original'),'original');
  assert.equal(restoredEpochFocus({focused:'new'},'original'),'new');
});
test('explorer snapshots preserve unsaved draft and saved identity without retaining stale preview results',async()=>{
  const {snapshotExplorerState}=await import('./workspaceNavigation.js');
  const draft={kind:'group',operator:'all',children:[{kind:'condition',field:'parameters/frequencyCutoff',valueType:'number',valueText:'25'}]};
  const revision={revision_uuid:'saved',recipe:{predicate:{all:[]},epochs:[{uuid:'e',metadata_hash:'h'}]},summary:{matched_count:1},preview:{membership:[{uuid:'stale'}],tree:{large:'cached'}}};
  const result=snapshotExplorerState({draft,name:'Unsaved name',filterSplits:'',splits:'date,cell',step:'filter',focused:null,applied:revision,restored:null});
  assert.equal(result.draft,draft);assert.equal(result.name,'Unsaved name');assert.equal(result.filterSplits,'');
  assert.equal(result.applied.revision_uuid,'saved');assert.deepEqual(result.applied.recipe.predicate,revision.recipe.predicate);assert.equal(result.applied.recipe.epoch_count,1);assert.equal(Object.hasOwn(result.applied.recipe,'epochs'),false);assert.equal(revision.recipe.epochs.length,1);
  assert.equal(Object.hasOwn(result.applied,'preview'),false);assert.equal(result.restored,null);
});
test('explorer navigation retains immutable revision IDs and counts, not 50k membership/diff arrays',async()=>{
  const {snapshotExplorerState}=await import('./workspaceNavigation.js');
  const epochs=Array.from({length:50_000},(_,i)=>({uuid:`e${i}`,metadata_hash:`h${i}`}));
  const applied={revision_uuid:'immutable-revision',recipe:{predicate:{all:[]},epochs,diff:{added:epochs.map(e=>e.uuid),removed:[],changed:[]}},preview:{membership:epochs,tree:{epochs}}};
  const result=snapshotExplorerState({draft:{kind:'group',children:[]},applied});
  assert.equal(result.applied.recipe.epoch_count,50_000);
  assert.deepEqual(result.applied.recipe.diff_counts,{added:50_000,removed:0,changed:0});
  assert.equal(result.applied.revision_uuid,'immutable-revision');
  assert.equal(JSON.stringify(result).includes('metadata_hash'),false);
  assert.ok(JSON.stringify(result).length<500);
  assert.equal(applied.recipe.epochs.length,50_000);
});

test('reopening a protocol starts epoch browsing but history restores its tree view',()=>{
 const saved={tab:'inspect',inspector:{focused:'epoch-5',offset:60,designMode:true,treeMode:true,treeOpen:false,designNavigation:{path:['date','cell']}}};
 const result=resolveProtocolSession({saved});
 assert.equal(result.inspector.designMode,false);
 assert.equal(result.inspector.treeMode,false);
 assert.equal(result.inspector.treeOpen,true);
 assert.equal(result.inspector.focused,'epoch-5');
 assert.deepEqual(result.inspector.designNavigation,saved.inspector.designNavigation);
 assert.equal(resolveProtocolSession({saved,restore:true}),saved);
 assert.equal(saved.inspector.designMode,true);
});
