import test from 'node:test';
import assert from 'node:assert/strict';
import {groupChoice,setGroupChoice,preferredValueType,canUseDateInput,fieldCategory,recordedValueChoices} from './components/predicateEditor.js';
import {compilePredicate,predicateToDraft,newGroup} from './components/predicateState.js';

test('None group means NOT ANY and never incorrectly negates ALL',()=>{
 const group=setGroupChoice({...newGroup(),children:[predicateToDraft({field:'date',operator:'eq',value:'2026-09-24'})]},'none');
 assert.deepEqual(compilePredicate(group),{not:{any:[{field:'date',operator:'eq',value:'2026-09-24'}]}});
 assert.equal(groupChoice(group),'none');
});
test('existing NOT ALL remains explicitly Not all and round-trips unchanged',()=>{
 const predicate={not:{all:[{field:'protocol',operator:'contains',value:'Noise'}]}};
 const loaded=predicateToDraft(predicate);
 assert.equal(groupChoice(loaded),'not_all');
 assert.deepEqual(compilePredicate(setGroupChoice(loaded,groupChoice(loaded))),predicate);
 assert.equal(setGroupChoice(loaded,'all').negated,false);
});
test('array contains defaults to a recorded element type, empty arrays to string',()=>{
 assert.equal(preferredValueType({types:['array'],choices:[{value:['NBQX','control']}]},'contains'),'string');
 assert.equal(preferredValueType({types:['array'],choices:[{value:[25,100]}]},'contains'),'number');
 assert.equal(preferredValueType({types:['array'],choices:[{value:[]}]},'contains'),'string');
 assert.equal(preferredValueType({types:['array']},'eq'),'array');
 assert.equal(preferredValueType({types:['null']},'eq'),'null');
});
test('calendar editor is limited to valid source recording dates, preserving other timestamps',()=>{
 const date={field:'date',valueType:'string',operator:'eq',valueText:'2026-09-24'};
 assert.equal(canUseDateInput(date),true);
 assert.equal(canUseDateInput({...date,valueText:'2026-02-31'}),false);
 assert.equal(canUseDateInput({...date,valueText:'2026-09-24 12:30:00'}),false);
 assert.equal(canUseDateInput({...date,field:'metadata/cell/start_time'}),false);
 assert.equal(canUseDateInput({...date,operator:'in',valueType:'array'}),false);
 assert.equal(canUseDateInput({...date,operator:'contains'}),false);
});
test('metadata grouping labels do not alter case-sensitive field identities',()=>{
 const field={id:'metadata/experiment/attributes/purpose',category:'Recording'};
 assert.equal(fieldCategory(field),'Experiment');
 assert.equal(field.id,'metadata/experiment/attributes/purpose');
 assert.equal(fieldCategory({id:'parameters/frequencyCutoff',category:'Parameters'}),'Protocol settings');
 assert.equal(fieldCategory({id:'metadata/block/parameters/frequencyCutoff',category:'Epoch block'}),'Epoch block');
});

test('array contains suggestions offer deduplicated typed elements without fabricated match counts',()=>{
 const choices=recordedValueChoices({choices:[{value:['NBQX',25,'25'],count:10},{value:['NBQX',null,25],count:2}],choices_truncated:true},'contains');
 assert.deepEqual(choices,[{value:'NBQX',type:'string',example_only:true},{value:25,type:'number',example_only:true},{value:'25',type:'string',example_only:true},{value:null,type:'null',example_only:true}]);
 assert.deepEqual(recordedValueChoices({choices:[{value:[],count:10}]},'contains'),[]);
});

test('choosing shared or dataset tags starts a single-tag membership search',async()=>{
 const {fieldCondition,isTagField}=await import('./components/predicateEditor.js');
 for(const id of ['annotations/effective/tags','annotations/cell/tags','annotations/epoch/tags','curation/protocol-uuid/tags']){
  const field={id,types:['array'],operators:['eq','ne','contains'],choices:[{type:'array',value:['good','stable']}]};
  const condition=fieldCondition(field);
  assert.equal(isTagField(field),true);
  assert.deepEqual(condition,{field:id,operator:'contains',valueType:'string',valueText:''});
  assert.deepEqual(compilePredicate({...predicateToDraft({field:id,operator:'contains',value:'stable'}),...condition,valueText:'stable'}),{field:id,operator:'contains',value:'stable'});
 }
 // Exact array comparison remains the default for ordinary recorded arrays.
 assert.equal(fieldCondition({id:'parameters/vector',types:['array'],operators:['eq','contains']}).operator,'eq');
});


test('live annotation catalogs without an operators list still default to text membership',async()=>{
 const {fieldCondition}=await import('./components/predicateEditor.js');
 assert.deepEqual(fieldCondition({id:'annotations/effective/tags',types:['array'],element_types:['string'],choices:[{type:'array',value:[]}]}),{field:'annotations/effective/tags',operator:'contains',valueType:'string',valueText:''});
});
