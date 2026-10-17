import test from 'node:test';
import assert from 'node:assert/strict';
import {addVocabularyTag,completeVocabulary,loadVocabulary,matchVocabulary,resetVocabulary,vocabularyVersion} from './tagVocabulary.js';

const tags=[{tag:'branch',count:3},{tag:'Bright flash',count:9},{tag:'rebranch',count:1},{tag:'noise',count:5}];

test('prefix matches come first (by usage), then substring matches, case-insensitively',()=>{
  assert.deepEqual(matchVocabulary('br',12,tags).map(item=>item.tag),['Bright flash','branch','rebranch']);
  assert.deepEqual(matchVocabulary('',2,tags).map(item=>item.tag),['Bright flash','noise']);
});

test('inline completion returns the most used existing tag extending what was typed',()=>{
  assert.equal(completeVocabulary('bra',tags),'branch');
  assert.equal(completeVocabulary('B',tags),'Bright flash');
  assert.equal(completeVocabulary('branch',tags),null,'An exact tag needs no completion');
  assert.equal(completeVocabulary('zzz',tags),null);
});

test('loads once, keeps tags saved during the load, and new tags are suggested at once',async()=>{
  resetVocabulary();let calls=0,release;
  const request=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
  loadVocabulary(request);loadVocabulary(request);assert.equal(calls,1);
  addVocabularyTag('fresh tag');
  release({tags:[{tag:'old',count:2}],has_more:false});await Promise.resolve();await Promise.resolve();
  assert.deepEqual(matchVocabulary('').map(item=>item.tag).sort(),['fresh tag','old']);
  const before=vocabularyVersion();addVocabularyTag('another');assert.ok(vocabularyVersion()>before);
  assert.equal(completeVocabulary('ano'),'another');
  loadVocabulary(request);assert.equal(calls,1,'Loaded vocabularies are not refetched');
});
