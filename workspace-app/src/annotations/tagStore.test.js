import test from 'node:test';
import assert from 'node:assert/strict';
import {createTagStore} from './tagStore.js';

const row=(tags=[])=>({epoch_uuid:'e1',cell_uuid:'c1',annotations:{cell_tags:[],epoch_tags:tags,effective_tags:tags,revisions:{cell:{},epoch:{}}}});
const receipt=(revision,tags)=>({version:1,targets:[{target_kind:'epoch',target_uuid:'e1',revisions:{me:revision},
  tags:tags.map(tag=>({target_kind:'epoch',target_uuid:'e1',profile_uuid:'me',author_name:'Me',tag,revision}))}]});
const shown=(store,value=row())=>store.apply(value).annotations.epoch_tags.map(chip=>chip.tag+(chip.pending?'*':''));

test('a begun tag shows at once as pending, confirms in place and bumps only the confirmed clock',()=>{
  const store=createTagStore();let notified=0;store.subscribe(()=>notified++);
  const ticket=store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a'});
  assert.equal(notified,1);assert.deepEqual(shown(store),['a*']);assert.equal(store.getConfirmedGeneration(),0);
  store.confirm(ticket,receipt(1,['a']));
  assert.deepEqual(shown(store),['a']);assert.equal(store.getConfirmedGeneration(),1);
  assert.equal(store.confirmedRevision('epoch','e1','me'),1,'Next write uses the confirmed revision');
});

test('pending operations never become authority, and failure rolls back with later queued operations',()=>{
  const store=createTagStore();
  const first=store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a'});
  const second=store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'b'});
  assert.equal(store.confirmedRevision('epoch','e1','me'),undefined);
  store.fail(first,new Error('Annotation revision conflict'));
  assert.deepEqual(shown(store),[]);assert.equal(store.isPending(second),false,'A dependent queued op is cancelled');
  assert.equal(store.error('epoch','e1'),'Annotation revision conflict');
});

test('add then remove before the first receipt shows the final intent immediately',()=>{
  const store=createTagStore();
  store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a'});
  store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a',remove:true});
  assert.deepEqual(shown(store),[]);
});

test('older receipts never overwrite newer author state and other authors are preserved',()=>{
  const store=createTagStore();
  store.ingest(receipt(2,['new']));store.ingest(receipt(1,['old']));
  const other={epoch_uuid:'e1',cell_uuid:'c1',annotations:{cell_tags:[],epoch_tags:[{profile_uuid:'you',author_name:'You',tag:'theirs',revision:4}],
    effective_tags:[],revisions:{cell:{},epoch:{you:4}}}};
  assert.deepEqual(store.apply(other).annotations.epoch_tags.map(chip=>chip.tag).sort(),['new','theirs']);
});

test('turns serialize writes per target and author; eviction keeps pending intent',async()=>{
  const store=createTagStore({limit:1}),order=[];
  const a=store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a'});
  store.begin({kind:'epoch',uuid:'e2',profile:'me',authorName:'Me',tag:'b'});
  assert.ok(store.read('epoch','e1'),'Pending entry survives eviction pressure');
  const releaseFirst=await store.turn('epoch','e1','me',a);
  const second=store.turn('epoch','e1','me',2).then(release=>{order.push('second');release();});
  await Promise.resolve();order.push('first');releaseFirst();await second;
  assert.deepEqual(order,['first','second']);
});

test('apply is memoized per row and target versions',()=>{
  const store=createTagStore(),value=row();
  store.begin({kind:'epoch',uuid:'e1',profile:'me',authorName:'Me',tag:'a'});
  assert.equal(store.apply(value),store.apply(value));
  assert.equal(store.apply({...value,epoch_uuid:'other'}).annotations,value.annotations,'Untouched rows are returned as-is');
});

test('after a receipt-less change, shown epochs are verified once and fresh facts win over older overlays',()=>{
  const store=createTagStore();
  store.ingest(receipt(1,['single']));
  assert.equal(store.needsVerification('e1'),false);
  store.changed();
  assert.equal(store.needsVerification('e1'),true,'Group save: epoch must be read fresh before trusted');
  const stale=row([{profile_uuid:'me',author_name:'Me',tag:'single',revision:1}]);stale.annotations.revisions.epoch={me:1};
  store.ingestAnnotations('e1','c1',{epoch_tags:[{profile_uuid:'me',author_name:'Me',tag:'single',revision:2},{profile_uuid:'me',author_name:'Me',tag:'from group',revision:2}],cell_tags:[],revisions:{epoch:{me:2},cell:{}}});
  assert.equal(store.needsVerification('e1'),false);
  assert.deepEqual(store.apply(stale).annotations.epoch_tags.map(chip=>chip.tag),['single','from group'],'Fresh facts overlay the stale cached row');
});
