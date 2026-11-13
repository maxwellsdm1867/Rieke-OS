import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {mutationUndo} from './undo/mutationUndo.js';
import {useMutationUndo} from './undo/useMutationUndo.js';

test('an unconfirmed membership inverse invalidates its original protocol exactly once without retry',async()=>{
 const previous={fetch:globalThis.fetch,document:globalThis.document};
 let handle,root,calls=0;const changes=[];
 globalThis.document={addEventListener(){},removeEventListener(){}};
 globalThis.fetch=async()=>{calls++;throw Error('Response connection lost after commit');};
 function Harness(){handle=useMutationUndo('membership-undo-project',event=>changes.push(event));return null;}
 try{
  await act(async()=>{root=TestRenderer.create(React.createElement(Harness));});
  mutationUndo.record({kind:'protocol-membership',protocol_uuid:'original-pin',removal_revision_uuid:'sealed-removal',expected_binding_version:2,count:1});
  await act(async()=>{assert.equal(await handle.undo(),false);});
  assert.equal(calls,1);
  assert.deepEqual(changes,[{kind:'membership',protocolId:'original-pin'}]);
  assert.match(mutationUndo.view().message,/not confirmed/);
 }finally{
  await act(async()=>root?.unmount());mutationUndo.project(null);
  globalThis.fetch=previous.fetch;globalThis.document=previous.document;
 }
});
