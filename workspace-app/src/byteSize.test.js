import test from 'node:test';
import assert from 'node:assert/strict';
import {formatBytes} from './byteSize.js';

test('byte sizes use decimal units with fixed precision and explicit whole values',()=>{
  assert.equal(formatBytes(0),'0 B');assert.equal(formatBytes(999),'999 B');
  assert.equal(formatBytes(1000),'1.0 KB');assert.equal(formatBytes(1024),'1.0 KB');
  assert.equal(formatBytes(305_000_000),'305.0 MB');assert.equal(formatBytes(536_700_000),'536.7 MB');
  assert.equal(formatBytes(1_360_000_000),'1.36 GB');assert.equal(formatBytes(1_432_900_000),'1.43 GB');
  assert.equal(formatBytes(999_960_000),'1.00 GB','rounding rolls over to the next unit');
  assert.equal(formatBytes(2_500_000_000_000),'2.50 TB');assert.equal(formatBytes(5e15),'5000.00 TB');
});

test('unavailable sizes never become zero and callers may name them',()=>{
  for(const value of [null,undefined,NaN,Infinity,-1,'305'])assert.equal(formatBytes(value),'—');
  assert.equal(formatBytes(null,{unavailable:'Not recorded'}),'Not recorded');
});
