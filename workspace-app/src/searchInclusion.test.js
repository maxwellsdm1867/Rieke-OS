import test from 'node:test';
import assert from 'node:assert/strict';
import {searchInclusionPredicate,searchEpochInclusion,toggleSearchInclusion} from './searchInclusion.js';
import {snapshotExplorerState} from './workspaceNavigation.js';
test('local exclusions constrain every candidate destination without changing browsable predicate or protocol curation',()=>{
 const base={field:'protocol',operator:'eq',value:'example'};
 const row={epoch_uuid:'one',curation:{included:false,tags:['existing']}};
 assert.equal(searchEpochInclusion(row,[]).curation.included,true);
 const excluded=toggleSearchInclusion([],'one',false);
 assert.equal(searchEpochInclusion(row,excluded).curation.included,false);
 assert.deepEqual(searchInclusionPredicate(base,excluded),{all:[base,{field:'epoch',operator:'not_in',value:['one']}]});
 assert.deepEqual(base,{field:'protocol',operator:'eq',value:'example'});
 assert.deepEqual(row.curation,{included:false,tags:['existing']});
 assert.equal(searchInclusionPredicate(base,toggleSearchInclusion(excluded,'one',true)),base);
 assert.deepEqual(toggleSearchInclusion(excluded,'one',false),['one']);
});
test('search session retains local exclusions independently of saved revisions',()=>{
 assert.deepEqual(snapshotExplorerState({excludedEpochs:['one'],draft:{all:[]}}).excludedEpochs,['one']);
});
test('large UUID exclusion sets stay inside backend literal limits without adding depth to all queries',()=>{
 const base={all:[{field:'protocol',operator:'eq',value:'example'}]};
 const ids=Array.from({length:250},(_,index)=>`00000000-0000-4000-8000-${String(index).padStart(12,'0')}`);
 const predicate=searchInclusionPredicate(base,ids);
 assert.equal(predicate.all[0],base.all[0]);
 assert.equal(predicate.all.length,5);
 const clauses=predicate.all.slice(1);
 for(const clause of clauses)assert.ok(JSON.stringify(clause.value).length<4096);
 assert.deepEqual(clauses.flatMap(clause=>clause.value),ids);
 assert.equal(base.all.length,1);
 assert.throws(()=>searchInclusionPredicate({all:Array.from({length:127},()=>base.all[0])},ids),/query size limit/);
});

test('deep queries fail clearly before saving a candidate while existing all groups retain their depth',()=>{
 const leaf={field:'protocol',operator:'eq',value:'example'};
 const nested=Array.from({length:7}).reduce(node=>({not:node}),leaf);
 assert.throws(()=>searchInclusionPredicate(nested,['one']),/nested too deeply/);
 const base={all:[Array.from({length:6}).reduce(node=>({not:node}),leaf)]};
 assert.equal(searchInclusionPredicate(base,['one']).all[0],base.all[0]);
});
