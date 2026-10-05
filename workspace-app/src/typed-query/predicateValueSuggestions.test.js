import test from 'node:test';
import assert from 'node:assert/strict';
import {predicateValueSuggestions} from './predicateValueSuggestions.js';
const choices=[{type:'string',value:'lab.SingleSpot'},{type:'string',value:'lab.VariableMeanNoiseCurInject'},{type:'string',value:'lab.VariableHistoryNoiseCurInject'}];
const pins=[{acquisition_protocol:'lab.VariableHistoryNoiseCurInject',name:'History noise'},{acquisition_protocol:'lab.VariableMeanNoiseCurInject',name:'Mean noise'}];
test('protocol suggestions rank pinned matches first but retain exact source IDs',()=>{
 const result=predicateValueSuggestions(choices,'',pins,true);
 assert.deepEqual(result.map(x=>x.value),['lab.VariableHistoryNoiseCurInject','lab.VariableMeanNoiseCurInject','lab.SingleSpot']);
 assert.equal(result[0].pinned,true);assert.equal(result[2].pinned,false);
 assert.equal(predicateValueSuggestions(choices,'variable mean',pins,true)[0].value,'lab.VariableMeanNoiseCurInject');
});
test('contains suggestions preserve literal strings and do not turn array or numeric values into strings',()=>{
 const result=predicateValueSuggestions([{type:'string',value:'NBQX 5um'},{type:'string',value:'NBQX 5um'},{type:'number',value:5},{type:'array',value:['NBQX']}],'nbqx',[],false);
 assert.equal(result.length,1);assert.equal(result[0].value,'NBQX 5um');
 assert.deepEqual(predicateValueSuggestions(choices,'unrecorded'),[]);
});
