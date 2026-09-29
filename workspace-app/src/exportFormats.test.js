import test from 'node:test';
import assert from 'node:assert/strict';
import {exportDownloadLabel,exportFormatLabel,initialExportFormat,validExportReceipt} from './exportFormats.js';

test('new exports default to SQLite while saved destinations and legacy JSON survive reuse',()=>{
 assert.equal(initialExportFormat(null),'wheeler-sqlite');
 for(const format of ['wheeler-sqlite','epictree-mat','reference-json'])assert.equal(initialExportFormat({format}),format);
 assert.equal(initialExportFormat({source_export_uuid:'legacy'}),'reference-json');
 assert.equal(initialExportFormat({format:'unsupported-future-format'}),'unsupported-future-format');
});
test('history/download labels distinguish SQLite databases, MATLAB bundles and JSON',()=>{
 assert.equal(exportFormatLabel('wheeler-sqlite'),'Wheeler SQLite database');
 assert.equal(exportDownloadLabel('wheeler-sqlite'),'SQLite database');
 assert.equal(exportFormatLabel('epictree-mat'),'EpicTree MATLAB bundle');
 assert.equal(exportDownloadLabel('reference-json'),'JSON');
 assert.equal(exportFormatLabel(undefined),'Reference JSON');
 assert.equal(exportDownloadLabel('unknown'),'Saved artifact');
});
test('export success requires a complete receipt for the requested supported format',()=>{
 const receipt={format:'wheeler-sqlite',dataset_uuid:'dataset-id',event_uuid:'event-id',download_url:'/api/exports/dataset-id/download',epoch_count:4};
 assert.equal(validExportReceipt(receipt,'wheeler-sqlite'),true);
 assert.equal(validExportReceipt(receipt,'epictree-mat'),false);
 assert.equal(validExportReceipt({...receipt,format:'unknown'},'unknown'),false);
 assert.equal(validExportReceipt({...receipt,format:'__proto__'},'__proto__'),false);
 for(const missing of ['dataset_uuid','event_uuid','download_url'])assert.equal(validExportReceipt({...receipt,[missing]:''},'wheeler-sqlite'),false);
 for(const epoch_count of [0,-1,NaN,2.5,Number.MAX_SAFE_INTEGER+1])assert.equal(validExportReceipt({...receipt,epoch_count},'wheeler-sqlite'),false);
});
