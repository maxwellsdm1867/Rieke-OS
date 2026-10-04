import test from 'node:test';
import assert from 'node:assert/strict';
import {createPresentationSessionHarness,draft} from './test-support/presentationSessionHarness.js';

test('a same-key cross-page restore keeps the stable Stores callback destination',async()=>{
 const initial={page:'overview',key:'shared-key'};
 const h=await createPresentationSessionHarness({route:initial,delayDraft:true});
 try{
  await h.mount();
  await h.resolveDraft(draft({route:{page:'stores',key:initial.key},sessions:[],protocolSessions:[],lastExplorerSession:null,lastStoresSession:null}));
  await h.waitFor(()=>h.root.findAllByType('presentation-stores').length>0);
  const remembered={marker:'stores after overview'};
  await h.act(()=>h.probe('stores').onSession(remembered));
  const saved=await h.checkpoint();
  assert.equal(saved.lastStoresSession,remembered,'the existing key-stable callback still remembers a Stores session');
  assert.equal(saved.lastExplorerSession,null);
  await h.click('Project overview');await h.click('Data stores');
  assert.notEqual(h.route.key,initial.key);assert.equal(h.probe('stores').session,remembered);
 }finally{await h.close();}
});
