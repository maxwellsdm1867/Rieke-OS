import test from 'node:test';
import assert from 'node:assert/strict';
import {compileTagRules,readTagRules,clearTagFilters,tagFilterLabel,predicateWithTagFilters} from './protocolViewFilter.js';
test('multiple tag rules preserve all/any, scopes, and negative membership on reopen',()=>{
 const rules=[{scope:'effective',comparison:'is',value:' selected '},{scope:'cell',comparison:'is_not',value:'artifact'}];
 for(const mode of ['all','any']){
  const predicate=compileTagRules(mode,rules);
  assert.deepEqual(predicate[mode][1],{not:{field:'annotations/cell/tags',operator:'contains',value:'artifact'}});
  assert.deepEqual(readTagRules({tag_predicate:JSON.stringify(predicate)}),{mode,rules:[{...rules[0],value:'selected'},rules[1]]});
 }
});
test('clearing tags preserves other protocol filters and shows readable multi-rule scope',()=>{
 const filters={cell_type:'RGC',tag:'old',tagged:'true',tag_predicate:JSON.stringify(compileTagRules('all',[{scope:'epoch',comparison:'is',value:'keep'}]))};
 assert.deepEqual(clearTagFilters(filters),{cell_type:'RGC'});
 assert.equal(tagFilterLabel(filters),'All of 1 tag rule: epoch is “keep”');
 assert.ok(filters.tag_predicate);
 assert.throws(()=>compileTagRules('all',[{scope:'effective',comparison:'is',value:''}]));
});

test('search local tag filters narrow the base query, and clearing restores that same query',()=>{
 const base={all:[{field:'protocol',operator:'eq',value:'VariableHistoryNoiseCurInject'}]};
 const rules=compileTagRules('any',[{scope:'epoch',comparison:'is',value:'reviewed'},{scope:'cell',comparison:'is_not',value:'artifact'}]);
 const filters={tag_predicate:JSON.stringify(rules)};
 assert.deepEqual(predicateWithTagFilters(base,filters),{all:[base,rules]});
 assert.equal(predicateWithTagFilters(base,clearTagFilters(filters)),base);
 assert.deepEqual(base,{all:[{field:'protocol',operator:'eq',value:'VariableHistoryNoiseCurInject'}]});
 assert.deepEqual(predicateWithTagFilters(base,{tagged:'true'}),{all:[base,{field:'annotations/effective/tags',operator:'ne',value:[]}]});
});

test('protocol handoff includes every supported current condition without changing base membership',async()=>{
 const {predicateWithProtocolFilters}=await import('./protocolViewFilter.js');
 const base={field:'protocol',operator:'eq',value:'Noise'};
 const filters={cell_uuid:'cell-one',cell_type:'RGC',group_label:'Drug',tagged:'true'};
 const result=predicateWithProtocolFilters(base,filters);
 assert.deepEqual(result,{all:[{all:[base,{field:'cell',operator:'eq',value:'cell-one'},{field:'cell type',operator:'eq',value:'RGC'},{field:'group label',operator:'eq',value:'Drug'}]},{field:'annotations/effective/tags',operator:'ne',value:[]}]});
 assert.deepEqual(base,{field:'protocol',operator:'eq',value:'Noise'});
});

test('tag-time rules compile to a UTC window on the same tag and reopen in local time',async()=>{
 const {localInputToUtc,utcToLocalInput}=await import('./protocolViewFilter.js');
 const rules=[{scope:'effective',comparison:'is',value:' good ',after:'2026-10-01T08:00',before:'2026-10-03T17:30'},{scope:'epoch',comparison:'is_not',value:'bad',after:'2026-10-02T00:00'}];
 const predicate=compileTagRules('all',rules);
 const after=localInputToUtc('2026-10-01T08:00');
 assert.match(after,/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
 assert.equal(Date.parse(after),new Date('2026-10-01T08:00').getTime());
 assert.deepEqual(predicate.all[0],{field:'annotations/effective/tag_times',operator:'contains',value:{tag:'good',after,before:localInputToUtc('2026-10-03T17:30')}});
 assert.deepEqual(predicate.all[1],{not:{field:'annotations/epoch/tag_times',operator:'contains',value:{tag:'bad',after:localInputToUtc('2026-10-02T00:00')}}});
 assert.deepEqual(readTagRules({tag_predicate:JSON.stringify(predicate)}),{mode:'all',rules:[{...rules[0],value:'good'},rules[1]]});
 assert.equal(utcToLocalInput(after),'2026-10-01T08:00');
 assert.match(tagFilterLabel({tag_predicate:JSON.stringify(predicate)}),/effective is “good” added after 2026-10-01 08:00 and added before 2026-10-03 17:30/);
 assert.throws(()=>compileTagRules('all',[{scope:'effective',comparison:'is',value:'x',after:'2026-10-03T00:00',before:'2026-10-01T00:00'}]),/earlier/);
 assert.throws(()=>compileTagRules('all',[{scope:'effective',comparison:'is',value:'x',after:'2026-10-03'}]),/complete date/);
 // Plain rules stay plain membership, unchanged for older saved filters.
 assert.deepEqual(compileTagRules('all',[{scope:'cell',comparison:'is',value:'x',after:'',before:''}]),{all:[{field:'annotations/cell/tags',operator:'contains',value:'x'}]});
 const base={field:'protocol',operator:'eq',value:'Noise'};
 assert.deepEqual(predicateWithTagFilters(base,{tag_predicate:JSON.stringify(predicate)}),{all:[base,predicate]});
});
