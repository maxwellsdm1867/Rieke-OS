import test from 'node:test';
import assert from 'node:assert/strict';
import { overviewModel } from './components/overviewModel.js';

test('overview dates and types count source cells independently of overlapping protocol cohorts',()=>{
  const result=overviewModel({cells:[{date:'2026-09-25',cell_type:'A',epochs:5,duration_seconds:2},{date:'2026-09-24',cell_type:'A',epochs:2,duration_seconds:3},{date:'2026-09-24',cell_type:'B',epochs:8,duration_seconds:4}],protocols:[{counts:{cells:3,epochs:15}},{counts:{cells:3,epochs:15}}]});
  assert.equal(result.totalCells,3);assert.equal(result.dateCount,2);
  assert.deepEqual(result.dates,[{date:'2026-09-24',cells:2,epochs:10,duration:7},{date:'2026-09-25',cells:1,epochs:5,duration:2}]);
  assert.deepEqual(result.types,[{type:'A',count:2},{type:'B',count:1}]);
});
test('missing recording dates remain visible and never inflate date count',()=>{
  const result=overviewModel({cells:[{cell_uuid:'known',date:'2026-09-24',epochs:3},{cell_uuid:'missing',epoch_count:4}]});
  assert.equal(result.dateCount,1);assert.equal(result.unknownDateCells,1);assert.equal(result.dates.find(x=>x.date==='Not recorded').epochs,4);
  assert.equal(result.types[0].type,'Unclassified');assert.equal(overviewModel({}).dateCount,0);
});

test('missing durations are unknown rather than fabricated zero or partial totals',()=>{
  assert.equal(overviewModel({cells:[{date:'2026-09-24'}]}).dates[0].duration,null);
  assert.equal(overviewModel({cells:[{date:'2026-09-24',duration_seconds:3},{date:'2026-09-24'}]}).dates[0].duration,null);
  assert.equal(overviewModel({cells:[{date:'2026-09-24',duration_seconds:0}]}).dates[0].duration,0);
});
