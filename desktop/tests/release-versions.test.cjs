'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {releaseVersions}=require('../e2e/release-versions.cjs');

test('future releases choose a strictly older synthetic prior without fixed release numbers',()=>{
  assert.deepEqual(releaseVersions('0.1.4'),{candidateVersion:'0.1.4',priorVersion:'0.1.3'});
  assert.deepEqual(releaseVersions('0.2.0'),{candidateVersion:'0.2.0',priorVersion:'0.1.0'});
  assert.deepEqual(releaseVersions('1.0.0'),{candidateVersion:'1.0.0',priorVersion:'0.0.0'});
});

test('an explicit prior version must be stable, valid and strictly older',()=>{
  assert.deepEqual(releaseVersions('1.0.0','0.9.9'),{candidateVersion:'1.0.0',priorVersion:'0.9.9'});
  for(const prior of ['1.0.0','1.0.1','2.0.0','0.9.9-beta','v0.9.9','00.9.9','',null]){
    assert.throws(()=>releaseVersions('1.0.0',prior),/prior|stable/i);
  }
});

test('the zero release fails clearly because there is no older stable fixture',()=>{
  assert.throws(()=>releaseVersions('0.0.0'),/no older stable/i);
});

test('invalid candidate metadata cannot produce a synthetic prior',()=>{
  for(const candidate of [undefined,null,14,'','0.1','0.1.4-beta','v0.1.4','01.1.4','0.1.-1','0.1.4\n','9007199254740992.0.0']){
    assert.throws(()=>releaseVersions(candidate),/stable/i);
  }
});
