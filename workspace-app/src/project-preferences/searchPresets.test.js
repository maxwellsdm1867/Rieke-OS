import test from 'node:test';
import assert from 'node:assert/strict';
import {rememberSearch,presetKey,suggestedSearches,predicateSummary} from './searchPresets.js';
const history={field:'protocol',operator:'contains',value:'History'};
test('reruns update one preset and preserve pins without retaining epoch payloads',()=>{
 let entries=rememberSearch([],{predicate:history,pinned:true,name:'History',epochs:Array(5000).fill('uuid')},'first');
 entries=rememberSearch(entries,{predicate:{all:[history]},matched_count:173},'second');
 assert.equal(entries.length,1);assert.equal(entries[0].pinned,true);assert.equal(entries[0].matched_count,173);assert.equal(entries[0].lastRunAt,'second');assert.equal(entries[0].epochs,undefined);
 assert.equal(presetKey(history),presetKey({all:[history]}));
});
test('recent searches are bounded and pinned searches survive new queries',()=>{
 let entries=rememberSearch([],{predicate:history,pinned:true});
 for(let i=0;i<20;i++)entries=rememberSearch(entries,{predicate:{field:'parameters/cutoff',operator:'eq',value:i}});
 assert.equal(entries.length,13);assert.equal(entries.filter(x=>x.pinned).length,1);
});
test('setting starter uses a recorded numeric value rather than inventing one',()=>{
 assert.equal(suggestedSearches([]).length,2);
 const suggestions=suggestedSearches([{id:'parameters/frequencyCutoff',choices:[{type:'number',value:25}]}]);
 assert.equal(suggestions[2].predicate.value,25);
 assert.equal(predicateSummary({field:'tag',operator:'contains',value:'drug.5'}),'tag contains drug.5');
});

test('run summaries keep epoch and cell counts distinct, including zero and missing',async()=>{
 const {searchRunSummary}=await import('./searchPresets.js');
 assert.deepEqual(searchRunSummary({last_run:{ran_at:'now',epoch_count:173,cell_count:4}}),{at:'now',epochs:173,cells:4});
 assert.deepEqual(searchRunSummary({last_run:{ran_at:'now',epoch_count:0,cell_count:0}}),{at:'now',epochs:0,cells:0});
 assert.deepEqual(searchRunSummary({matched_count:10}),{at:null,epochs:10,cells:null});
 let entries=rememberSearch([],{predicate:history,pinned:true},'not-a-run');
 assert.equal(entries[0].lastRunAt,undefined);
 entries=rememberSearch(entries,{predicate:history,matched_count:5,cell_count:2},'actual-run');
 entries=rememberSearch(entries,{...entries[0],pinned:false},'pin-change');
 assert.equal(entries[0].lastRunAt,'actual-run');assert.equal(entries[0].cell_count,2);
});

test('predicate shortcut identity ignores condition order and repetitions without changing array equality',()=>{
 const a={field:'setting',operator:'eq',value:[1,2]},b={field:'protocol',operator:'contains',value:'History'};
 assert.equal(presetKey({all:[a,b]}),presetKey({all:[b,{all:[a,a]}]}));
 assert.notEqual(presetKey(a),presetKey({...a,value:[2,1]}));
 assert.notEqual(presetKey({all:[a,b]}),presetKey({any:[a,b]}));
});
