import test from 'node:test';
import assert from 'node:assert/strict';
import {exportDownloadLabel,exportFormatLabel,initialExportFormat,validExportReceipt} from "./exports/exportFormats.js";

test('new exports default to SQLite while saved destinations and legacy JSON survive reuse',()=>{
 assert.equal(initialExportFormat(null),'wheeler-sqlite');
 for(const format of ['wheeler-sqlite','matlab-mat','reference-json','linked-sqlite'])assert.equal(initialExportFormat({format}),format);
 assert.equal(initialExportFormat({source_export_uuid:'legacy'}),'reference-json');
 assert.equal(initialExportFormat({format:'unsupported-future-format'}),'unsupported-future-format');
});
test('history/download labels distinguish SQLite databases, MAT data, legacy bundles and JSON',()=>{
 assert.equal(exportFormatLabel('wheeler-sqlite'),'Wheeler SQLite database');
 assert.equal(exportDownloadLabel('wheeler-sqlite'),'SQLite database');
 assert.equal(exportDownloadLabel('linked-sqlite'),'SQLite + loader (.zip)');
 assert.match(exportFormatLabel('linked-sqlite'),/internal use/);
 assert.equal(exportFormatLabel('epictree-mat'),'Legacy MATLAB bundle');
 assert.equal(exportDownloadLabel('reference-json'),'JSON');
 assert.equal(exportFormatLabel(undefined),'Reference JSON');
 assert.equal(exportDownloadLabel('unknown'),'Saved artifact');
});
test('export success requires a complete receipt for the requested supported format',()=>{
 const receipt={format:'wheeler-sqlite',dataset_uuid:'dataset-id',event_uuid:'event-id',download_url:'/api/exports/dataset-id/download',epoch_count:4};
 assert.equal(validExportReceipt(receipt,'wheeler-sqlite'),true);
 for(const otherFormat of ['matlab-mat','reference-json'])assert.equal(validExportReceipt(receipt,otherFormat),false);
 assert.equal(validExportReceipt(receipt,'epictree-mat'),false);
 assert.equal(validExportReceipt({...receipt,format:'unknown'},'unknown'),false);
 assert.equal(validExportReceipt({...receipt,format:'__proto__'},'__proto__'),false);
 assert.equal(validExportReceipt({...receipt,format:{}},{}),false);
 for(const missing of ['dataset_uuid','event_uuid','download_url'])assert.equal(validExportReceipt({...receipt,[missing]:''},'wheeler-sqlite'),false);
 for(const epoch_count of [0,-1,NaN,2.5,Number.MAX_SAFE_INTEGER+1])assert.equal(validExportReceipt({...receipt,epoch_count},'wheeler-sqlite'),false);
});

test('MATLAB data export is standalone and legacy saved destinations reopen as data-only MAT',()=>{
 assert.equal(initialExportFormat({format:'matlab-mat'}),'matlab-mat');
 assert.equal(initialExportFormat({format:'epictree-mat'}),'matlab-mat');
 assert.equal(exportFormatLabel('matlab-mat'),'MATLAB data (.mat)');
 assert.equal(exportDownloadLabel('matlab-mat'),'MAT data');
 assert.equal(exportFormatLabel('epictree-mat'),'Legacy MATLAB bundle');
 const receipt={format:'matlab-mat',dataset_uuid:'id',event_uuid:'event',download_url:'/api/exports/id/download',epoch_count:3};
 assert.equal(validExportReceipt(receipt,'matlab-mat'),true);
});
