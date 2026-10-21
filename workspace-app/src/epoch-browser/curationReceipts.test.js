import test from 'node:test';
import assert from 'node:assert/strict';
import {createCurationReceipts,curationReceipts,validCurationReceipt} from './curationReceipts.js';
import {epochPageRevision} from './epochBrowserSource.js';

const receipt=(token,included=false)=>({query_revision:token,expected_binding_version:2,event_uuid:null,curation:{e1:{included,tags:[],review_state:'unreviewed',revision:1}},curation_revisions:{e1:1}});
test('own receipts chain query revisions, overlay rows and retire on a foreign page',()=>{
 const store=createCurationReceipts();
 assert.equal(store.record('P',{sentRevision:'q0',bindingVersion:2,epochUuids:['e1'],receipt:receipt('q1')}),true);
 assert.equal(store.latest('P','q0'),'q1','a page that showed q0 writes with the chained token');
 assert.equal(store.record('P',{sentRevision:'q1',bindingVersion:2,epochUuids:['e1'],receipt:receipt('q2',true)}),true);
 assert.equal(store.latest('P','q0'),'q2');assert.equal(store.canonical('P','q2'),'q0');assert.equal(store.canonical('P','other'),'other');
 assert.equal(store.apply('P',{epoch_uuid:'e1',curation:{included:false,tags:['x']}}).curation.included,true);
 assert.equal(store.apply('Q',{epoch_uuid:'e1',curation:{included:false}}).curation.included,false,'another protocol never borrows it');
 store.observe('P','q2');assert.equal(store.latest('P','q0'),'q2','pages inside the chain keep it');
 store.observe('P','foreign');assert.equal(store.latest('P','q0'),'q0','a foreign token retires the chain');
 assert.equal(store.apply('P',{epoch_uuid:'e1',curation:{included:false}}).curation.included,false);
});
test('incomplete, mismatched or legacy replies are not receipts',()=>{
 const ok={protocolId:'P',sentRevision:'q0',bindingVersion:2,epochUuids:['e1']};
 assert.equal(validCurationReceipt(receipt('q1'),ok),true);
 for(const bad of [{curation:{}},{query_revision:''},{expected_binding_version:3},{curation:{e1:{included:'no',tags:[],review_state:'x',revision:1}}},{changed:1,query_revision:undefined}])
  assert.equal(validCurationReceipt({...receipt('q1'),...bad},ok),false,JSON.stringify(bad));
 assert.equal(createCurationReceipts().record('P',{...ok,receipt:{curation:{},event_uuid:null}}),false);
});
test('page chains compare through the receipt chain; frozen sources never do',()=>{
 curationReceipts.record('P',{sentRevision:'q0',bindingVersion:2,epochUuids:['e1'],receipt:receipt('q1')});
 try{
  assert.equal(epochPageRevision({kind:'protocol',protocolId:'P',queryRevision:'q0'},{query_revision:'q1'}),'q0');
  assert.throws(()=>epochPageRevision({kind:'protocol',protocolId:'P',queryRevision:'q0'},{query_revision:'zz'}),/epoch list is out of date/);
  assert.throws(()=>epochPageRevision({kind:'protocol',protocolId:'P',queryRevision:'q0',readContext:{root:'/x'}},{query_revision:'q1'}),/epoch list is out of date/);
 }finally{curationReceipts.clear('P');}
});
