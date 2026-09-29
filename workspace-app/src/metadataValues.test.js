import test from 'node:test';
import assert from 'node:assert/strict';
import {metadataRows,metadataClipboard,metadataValueSafe,metadataPredicateValueSupported,registeredMetadataField} from './components/metadataValues.js';

test('metadata rows preserve source paths and whole array values',()=>{
  const values={'literal.dot':{'slash/key':[0,false,'',null]},'~tilde':{},empty:''};
  const rows=metadataRows(values,['parameters']);
  assert.deepEqual(rows[0].path,['parameters','literal.dot','slash/key']);
  assert.deepEqual(rows[0].value,[0,false,'',null]);
  assert.deepEqual(rows[1].value,{});
  assert.equal(rows[2].value,'');
});
test('registered fields require exact catalog paths with JSON pointer escaping',()=>{
  const field={id:'parameters/slash~1key/tilde~0key/comma%2Ckey',path:'irrelevant display path'};
  assert.equal(registeredMetadataField(['parameters','slash/key','tilde~key','comma,key'],[field]),field);
  assert.equal(registeredMetadataField(['parameters','slash','key','tilde~key','comma,key'],[field]),undefined);
  assert.equal(registeredMetadataField(['parameters','unregistered'],[field]),undefined);
  const base={id:'cell type',path:'cell_type'};
  assert.equal(registeredMetadataField(['cell_type'],[base]),base);
  assert.equal(registeredMetadataField(['metadata','cell_type'],[base]),undefined);
});
test('clipboard JSON preserves typed values without display coercion',()=>{
  for(const value of [null,'null','',false,0,1.25,[1,'1',false,null]]){
    const row={key:'value',value},field={id:'parameters/value'};
    assert.deepEqual(JSON.parse(metadataClipboard(row,'value',field)),value);
    assert.deepEqual(JSON.parse(metadataClipboard(row,'pair',field)),{value});
    const predicate=JSON.parse(metadataClipboard(row,'predicate',field));
    assert.deepEqual(predicate,value===null?{field:field.id,operator:'is_null'}:{field:field.id,operator:'eq',value});
  }
});
test('unsafe browser numbers fail closed for value and predicate copying',()=>{
  for(const value of [Number.MAX_SAFE_INTEGER+1,Infinity,NaN,[Number.MAX_SAFE_INTEGER+1],{ticks:Number.MAX_SAFE_INTEGER+1},undefined]){
    assert.equal(metadataValueSafe(value),false);
    for(const kind of ['value','pair','predicate'])assert.throws(()=>metadataClipboard({key:'ticks',value},kind,{id:'parameters/ticks'}));
  }
  assert.equal(metadataClipboard({key:'ticks',value:Number.MAX_SAFE_INTEGER+1},'key'),'ticks');
  assert.equal(metadataValueSafe(Number.MAX_SAFE_INTEGER),true);
});
test('unsupported objects and unregistered fields cannot become predicates',()=>{
  assert.equal(metadataPredicateValueSupported({a:1}),false);
  assert.equal(metadataPredicateValueSupported([{a:1}]),false);
  assert.equal(metadataPredicateValueSupported(Array(101).fill(1)),false);
  assert.throws(()=>metadataClipboard({key:'a',value:1},'predicate'));
  assert.throws(()=>metadataClipboard({key:'a',value:{}},'predicate',{id:'parameters/a'}));
  assert.equal(metadataClipboard({key:'a',value:1},'field',{id:'parameters/exact%2Cid'}),'parameters/exact%2Cid');
});
test('API encoded oversized integers remain copyable as API JSON but never become textual predicates',()=>{
  const value='638945620838129991';
  assert.equal(JSON.parse(metadataClipboard({key:'ticks',value},'value')),value);
  assert.equal(metadataPredicateValueSupported(value),false);
  assert.equal(metadataPredicateValueSupported([value]),false);
  assert.throws(()=>metadataClipboard({key:'ticks',value},'predicate',{id:'parameters/ticks'}));
  assert.equal(metadataPredicateValueSupported('42'),true);
});
test('predicate copies obey literal depth and serialized length bounds',()=>{
  let value=1;for(let n=0;n<6;n++)value=[value];
  assert.equal(metadataPredicateValueSupported(value),true);
  assert.equal(metadataPredicateValueSupported([value]),false);
  assert.equal(metadataPredicateValueSupported('x'.repeat(4094)),true);
  assert.equal(metadataPredicateValueSupported('x'.repeat(4095)),false);
});

test('copy setting and value preserves registered path and typed searchable literal',()=>{
  const row={key:'frequencyCutoff',path:['parameters','frequencyCutoff'],value:100};
  assert.equal(metadataClipboard(row,'setting',{id:'parameters/frequencyCutoff'}),'parameters/frequencyCutoff = 100');
  assert.equal(metadataClipboard({...row,value:'100'},'setting',{id:'parameters/frequencyCutoff'}),'parameters/frequencyCutoff = "100"');
  assert.equal(metadataClipboard({...row,value:[0, false, null]},'setting'),'parameters.frequencyCutoff = [0,false,null]');
  assert.throws(()=>metadataClipboard({...row,value:Infinity},'setting'));
});

test('click-to-copy values use plain text for strings and exact JSON for structured values',()=>{
 const row=value=>({key:'setting',path:['parameters','setting'],value});
 assert.equal(metadataClipboard(row('Amp1'),'text'),'Amp1');
 assert.equal(metadataClipboard(row(25),'text'),'25');
 assert.deepEqual(JSON.parse(metadataClipboard(row([0,675]),'text')),[0,675]);
 assert.equal(metadataClipboard(row('9007199254740993'),'text'),'9007199254740993');
 assert.throws(()=>metadataClipboard(row(Number.MAX_SAFE_INTEGER+1),'text'));
});
