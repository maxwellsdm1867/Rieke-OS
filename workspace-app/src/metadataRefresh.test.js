import test from 'node:test';
import assert from 'node:assert/strict';
import {validMetadataRefresh,availabilityLabel,availabilityExplanation} from './metadataRefresh.js';
test('metadata refresh success requires a complete quantitative receipt',()=>{
  const receipt={sources:2,epochs:1776,protocols:5,reused_sources:1,rebuilt_sources:1,elapsed_seconds:.32,completed_at:'2026-09-27T12:00:00Z'};
  assert.equal(validMetadataRefresh(receipt),true);
  for(const key of Object.keys(receipt)){const incomplete={...receipt};delete incomplete[key];assert.equal(validMetadataRefresh(incomplete),false);}
  assert.equal(validMetadataRefresh({...receipt,reused_sources:'1'}),false);
  assert.equal(validMetadataRefresh({...receipt,elapsed_seconds:Infinity}),false);
  assert.equal(validMetadataRefresh({...receipt,completed_at:'not a timestamp'}),false);
  assert.equal(validMetadataRefresh({...receipt,rebuilt_sources:-1}),false);
});
test('availability explicitly distinguishes changed files and does not imply checksum verification',()=>{
  assert.equal(availabilityLabel('changed'),'File size changed');
  assert.equal(availabilityLabel('available'),'Available');
  assert.equal(availabilityLabel(undefined),'Not checked');
  assert.match(availabilityExplanation('available'),/not a full checksum/);
  assert.match(availabilityExplanation('changed'),/size differs/);
  assert.doesNotMatch(availabilityExplanation('missing'),/deleted/);
});
