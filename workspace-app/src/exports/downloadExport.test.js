import test from 'node:test';
import assert from 'node:assert/strict';
import {downloadExport} from './downloadExport.js';
test('explicit download uses the published URL and removes its temporary link',()=>{
 const events=[],link={click(){events.push(['click',this.href,this.download]);},remove(){events.push('remove');}};
 const doc={createElement:()=>link,body:{appendChild(value){assert.equal(value,link);events.push('append');}}};
 assert.equal(downloadExport({download_url:'/api/exports/frozen/download'},doc),true);
 assert.deepEqual(events,['append',['click','/api/exports/frozen/download',''],'remove']);
});
test('download failure preserves the receipt for retry',()=>{
 const receipt={dataset_uuid:'saved',download_url:'/api/exports/saved/download'};let removed=false;
 const doc={createElement:()=>({click(){throw Error('unavailable');},remove(){removed=true;}}),body:{appendChild(){}}};
 assert.equal(downloadExport(receipt,doc),false);assert.equal(removed,true);assert.equal(receipt.dataset_uuid,'saved');
 assert.equal(downloadExport({},doc),false);
});
