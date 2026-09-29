import test from 'node:test';
import assert from 'node:assert/strict';
import {compilePredicate,predicateToDraft,typedValue} from './components/predicateState.js';
const fields=[{id:'parameters/frequencyCutoff',label:'Frequency cutoff'},{id:'group label',label:'Group label'}];
test('nested ALL ANY and NOT preserve exact grouping through the editor',()=>{
 const predicate={all:[{field:'parameters/frequencyCutoff',operator:'gte',value:25},{not:{any:[{field:'group label',operator:'eq',value:'NBQX'},{not:{field:'group label',operator:'exists'}}]}}]};
 assert.deepEqual(compilePredicate(predicateToDraft(predicate),fields),predicate);
});
test('typed values distinguish numeric strings, numbers, booleans, null and lists',()=>{
 for(const [text,type,expected] of [['25','string','25'],['25','number',25],['false','boolean',false],['ignored','null',null],['[25,"25",null,false]','array',[25,'25',null,false]]])assert.deepEqual(typedValue(text,type),expected);
});
test('unary predicates omit values and empty groups retain explicit truth structure',()=>{
 for(const predicate of [{all:[]},{any:[]},{not:{all:[]}},{not:{any:[]}},{field:'group label',operator:'missing'},{field:'group label',operator:'is_null'}])assert.deepEqual(compilePredicate(predicateToDraft(predicate),fields),predicate);
});
test('unknown metadata fields fail closed',()=>{
 assert.throws(()=>compilePredicate(predicateToDraft({field:'typo',operator:'eq',value:1}),fields),/not in the current/);
 assert.throws(()=>compilePredicate(predicateToDraft({field:'',operator:'eq',value:1}),fields),/Choose a metadata/);
});
test('unsafe integer values and incomplete numeric inputs are rejected',()=>{
 for(const text of ['', 'NaN','Infinity','25abc','1e999','9007199254740993'])assert.throws(()=>typedValue(text,'number'));
 assert.throws(()=>typedValue('[9007199254740993]','array'),/represented exactly/);
 assert.throws(()=>typedValue('[{"x":1}]','array'),/Object values/);
 assert.throws(()=>typedValue('[1,]','array'),/valid JSON/);
});
test('ordering cannot silently coerce a textual source value',()=>{
 assert.throws(()=>compilePredicate(predicateToDraft({field:'parameters/frequencyCutoff',operator:'gt',value:'25'}),fields),/numeric value/);
});
