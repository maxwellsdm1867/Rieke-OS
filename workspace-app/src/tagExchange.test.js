import test from 'node:test';
import assert from 'node:assert/strict';
import {readTagDocument,tagExportUrl,MAX_TAG_IMPORT_BYTES} from './tagExchange.js';
test('tag import rejects masks, oversized files, invalid JSON and arrays',async()=>{
 for(const file of [{size:MAX_TAG_IMPORT_BYTES+1},{name:'mask.ugm',size:2},{size:1,text:async()=>'{broken'},{size:2,text:async()=>'[]'}])await assert.rejects(readTagDocument(file));
 assert.deepEqual(await readTagDocument({size:2,text:async()=>'{}'}),{});
});
test('tag export scope uses stable UUID, never cell label or row position',()=>{
 assert.equal(tagExportUrl({}),'/api/annotations/export?format=rieke');
 assert.equal(tagExportUrl({scope:'cell',epoch:{cell_uuid:'exact-cell',cell_label:'Cell1'}}),'/api/annotations/export?format=rieke&target_kind=cell&target_uuid=exact-cell');
 assert.throws(()=>tagExportUrl({scope:'cell',epoch:{cell_label:'Cell1'}}));
 assert.throws(()=>tagExportUrl({format:'other'}));
});
