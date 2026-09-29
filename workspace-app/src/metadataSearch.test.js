import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesMetadataSearch,parseMetadataSearch} from './metadataSearch.js';
const row=(key,value)=>({key,label:key,path:['parameters',key],value});
test('focused metadata field/value search preserves scalar types',()=>{
  assert(matchesMetadataSearch(row('frequencyCutoff',100),'frequencyCutoff = 100'));
  assert(!matchesMetadataSearch(row('frequencyCutoff','100'),'frequencyCutoff = 100'));
  assert(matchesMetadataSearch(row('frequencyCutoff','100'),'frequencyCutoff = "100"'));
  assert(matchesMetadataSearch(row('frequencyCutoff',100),'parameters/frequencyCutoff >= 90'));
  assert(!matchesMetadataSearch(row('frequencyCutoff',false),'frequencyCutoff = 0'));
});
test('array pair order and value case stay exact',()=>{
  assert(matchesMetadataSearch(row('history1',[30,10]),'history1 = [30, 10]'));
  assert(!matchesMetadataSearch(row('history1',[10,30]),'history1 = [30,10]'));
  assert(!matchesMetadataSearch(row('label','CellA'),'label = cella'));
  assert(matchesMetadataSearch(row('label','CellA'),'label = CellA'));
});
test('unsafe numeric literals and malformed pairs fail visibly',()=>{
  assert(parseMetadataSearch('uuid = 9007199254740993').error);
  assert(parseMetadataSearch('history1 = [30,').error);
  assert(!matchesMetadataSearch(row('uuid','9007199254740993'),'uuid = 9007199254740993'));
  assert(matchesMetadataSearch(row('uuid','9007199254740993'),'uuid = "9007199254740993"'));
});
test('unstructured field/value discovery stays substring-based',()=>{
  assert(matchesMetadataSearch(row('frequencyCutoff',100),'cutoff'));
  assert(matchesMetadataSearch(row('frequencyCutoff',100),'100'));
});
