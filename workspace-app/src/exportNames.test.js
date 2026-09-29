import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultExportName,localExportDate} from './exportNames.js';

test('export default uses readable protocol, underscores, date, and no ID',()=>{
  assert.equal(defaultExportName('VariableMeanNoiseCurInject','2026-09-28'),'Variable_Mean_Noise_current_injection_2026-09-28');
  assert.equal(defaultExportName('My selection_2026-09-28','2026-09-28'),'My_selection_2026-09-28');
  assert.equal(defaultExportName('','2026-09-28'),'Search_2026-09-28');
});
test('local export date keeps the calendar day at midnight and late evening',()=>{
  assert.equal(localExportDate(new Date(2026,8,28,0,1)),'2026-09-28');
  assert.equal(localExportDate(new Date(2026,8,28,23,59)),'2026-09-28');
});
test('generated labels are filesystem safe and fit the export name limit',()=>{
  assert.equal(defaultExportName('../Café / trial: one','2026-09-28'),'Cafe_trial_one_2026-09-28');
  assert.ok(defaultExportName('x'.repeat(500),'2026-09-28').length<=120);
});
