import test from 'node:test';
import assert from 'node:assert/strict';
import {api} from './api.js';
import {importFailureState,transferElapsedSeconds} from './importTransfer.js';

test('path import HTTP rejection is definite and its elapsed time stops',async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>({ok:false,status:400,json:async()=>({error:'Choose an existing .h5 recording file'})});
  try{
    let failure;
    try{await api('/imports',{method:'POST',body:{source_path:'/missing.h5'}});}catch(error){failure=error;}
    assert.equal(failure.status,400);
    const transfer=importFailureState({phase:'starting',started_at:'2026-01-01T00:00:00Z'},failure,'2026-01-01T00:00:02Z');
    assert.equal(transfer.requestRejected,true);
    assert.equal(transfer.error,'Choose an existing .h5 recording file');
    assert.equal(transferElapsedSeconds(transfer,Date.parse('2026-01-01T00:10:00Z')),2);
  }finally{globalThis.fetch=original;}
});

test('network and server errors keep acceptance uncertain; explicit upload rejection is final',()=>{
  const previous={phase:'starting',started_at:'2026-01-01T00:00:00Z'};
  for(const error of [new TypeError('Failed to fetch'),Object.assign(new Error('server failure'),{status:500})]){
    const transfer=importFailureState(previous,error,'2026-01-01T00:00:02Z');
    assert.equal(transfer.requestRejected,false);assert.equal(transfer.finished_at,undefined);
    assert.equal(transferElapsedSeconds(transfer,Date.parse('2026-01-01T00:10:00Z')),600);
  }
  assert.equal(importFailureState(previous,Object.assign(new Error('Upload rejected'),{requestRejected:true})).requestRejected,true);
});
