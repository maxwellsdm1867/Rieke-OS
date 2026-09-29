import test from 'node:test';
import assert from 'node:assert/strict';
import {createTreeLayoutSaver} from './treeLayoutPersistence.js';
test('rapid tree edits serialize with the acknowledged server version',async()=>{
 const requests=[],states=[];let finish;
 const saver=createTreeLayoutSaver({version:3,splitOrder:['date'],onState:s=>states.push(s),write:body=>{
   requests.push(body);
   if(requests.length===1)return new Promise(resolve=>finish=()=>resolve({version:4,split_order:body.split_order}));
   return Promise.resolve({version:5,split_order:body.split_order});
 }});
 const first=saver.remember(['cell','date']);
 await Promise.resolve();
 saver.remember(['cell','date','block']);
 finish();await first;
 assert.deepEqual(requests,[{split_order:['cell','date'],expected_version:3},{split_order:['cell','date','block'],expected_version:4}]);
 assert.equal(states.at(-1).status,'saved');
 await saver.remember(['cell','date','block']);assert.equal(requests.length,2);
});
test('failed saves preserve the desired layout for an explicit retry',async()=>{
 let fail=true;const states=[],requests=[];
 const saver=createTreeLayoutSaver({version:0,splitOrder:['date'],onState:s=>states.push(s),write:async body=>{requests.push(body);if(fail)throw new Error('Offline');return {split_order:body.split_order,version:1};}});
 await saver.remember([]);assert.equal(states.at(-1).status,'error');
 fail=false;await saver.retry();assert.equal(states.at(-1).status,'saved');
 assert.deepEqual(requests[1],{split_order:[],expected_version:0});
});

test('the first validated default layout is also persisted before a query update can replace its fallback',async()=>{
 const writes=[];
 const saver=createTreeLayoutSaver({version:0,splitOrder:['date','cell'],write:async body=>{writes.push(body);return {version:1,split_order:body.split_order};}});
 await saver.remember(['date','cell']);await saver.remember(['date','cell']);
 assert.equal(writes.length,1);
});
