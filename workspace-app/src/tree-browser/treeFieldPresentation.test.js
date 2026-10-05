import test from 'node:test';
import assert from 'node:assert/strict';
import {COMMON_TREE_FIELDS,treeFieldLabel,treeFieldHint,treeFieldExamples,treeFieldMatches,groupingFieldRank} from './treeFieldPresentation.js';

test('ordinary tree splits remain discoverable even when automatic suggestions omit them',()=>{
 const group={id:'group',label:'Epoch group',category:'Recording',path:'group_uuid',examples:['NBQX5um']};
 assert.ok(COMMON_TREE_FIELDS.includes('group'));
 assert.equal(treeFieldMatches(group,{suggestions:[]}),true);
 assert.equal(treeFieldMatches(group,{category:'All',search:'epoch group'}),true);
 assert.equal(treeFieldMatches(group,{order:['group']}),false);
 assert.equal(group.id,'group');
 assert.match(treeFieldHint(group),/each recorded epoch group/);
 assert.match(treeFieldHint({id:'group label'}),/same label/);
});
test('display formatting hides namespaces and JSON escaping without changing source values',()=>{
 const field={id:'protocol',examples:['"edu.washington.riekelab.VariableMeanNoiseCurInject"']};
 const before=structuredClone(field);
 assert.equal(treeFieldExamples(field),'Variable Mean Noise current injection');
 assert.deepEqual(field,before);
 assert.equal(treeFieldExamples({id:'cell type',examples:['"RGC\\\\ON-parasol"']}),'ON-parasol');
 assert.equal(treeFieldExamples({id:'date',examples:['"2026-09-24"']}),'2026-09-24');
 assert.equal(treeFieldExamples({id:'parameters/vector',examples:['[1,2]']}),'[1,2]');
});
test('friendly labels preserve full metadata search and do not invent a saved field name',()=>{
 assert.equal(treeFieldLabel({id:'group label',label:'Recorded group label'}),'Epoch group label');
 assert.equal(treeFieldLabel({id:'unknown/raw/path'}),'Saved metadata field');
 const field={id:'parameters/frequencyCutoff',label:'Frequency cutoff',category:'Parameters',path:'parameters.frequencyCutoff',examples:['100']};
 for(const search of ['frequency cutoff','parameters.frequencyCutoff','100'])assert.equal(treeFieldMatches(field,{category:'All',search}),true);
 assert.equal(treeFieldMatches(field,{category:'Common'}),false);
});


test('varying scientific settings rank before alternatives, constants and acquisition bookkeeping',()=>{
 const fields=[{id:'seed',grouping_role:'technical',varying:true},{id:'history2',grouping_role:'primary',varying:false},
 {id:'history1Mean',grouping_role:'alternative',varying:true},{id:'history1',grouping_role:'primary',varying:true}];
 assert.deepEqual(fields.sort((a,b)=>groupingFieldRank(a)-groupingFieldRank(b)).map(f=>f.id),['history1','history1Mean','history2','seed']);
});
