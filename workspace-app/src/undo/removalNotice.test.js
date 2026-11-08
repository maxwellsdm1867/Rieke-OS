import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('removal notice follows the top receipt and refuses stale Undo clicks',async()=>{
 const dom=new JSDOM('<main></main>',{url:'http://fixture/'});
 const previous={window:globalThis.window,document:globalThis.document};
 globalThis.window=dom.window;globalThis.document=dom.window.document;
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Controls}=await server.ssrLoadModule('/src/undo/ui/UndoControls.jsx');
 const {mutationUndo:history}=await server.ssrLoadModule('/src/undo/mutationUndo.js');
 const root=createRoot(document.querySelector('main'));let calls=0;
 const removal=(revision='removed-A')=>({kind:'protocol-membership',protocol_uuid:'pin-A',removal_revision_uuid:revision,expected_binding_version:2,count:2});
 const notice=()=>document.querySelector('.pin-removal-notice');
 const undo=()=>notice().querySelector('button');
 try{
  await act(()=>{history.project('project-A');root.render(React.createElement(Controls,{onUndo:()=>{calls++;}}));});
  assert.equal(notice(),null);
  await act(()=>history.record(removal()));
  assert.match(notice().textContent,/Removed 2 epochs from pin/);
  assert.equal(notice().parentElement,document.body);
  await act(()=>undo().click());assert.equal(calls,1);
  let token;await act(()=>{token=history.begin();});assert.equal(undo().disabled,true);
  await act(()=>history.complete(token,null));assert.equal(undo().disabled,false);
  await act(()=>notice().querySelector('[aria-label="Dismiss removal notice"]').click());assert.equal(notice(),null);
  await act(()=>history.record(removal('removed-B')));assert.ok(notice());
  const stale=undo();
  await act(()=>{history.record({kind:'curation',protocol_uuid:'pin-A',operations:[{epoch_uuid:'later-edit'}]});stale.click();});
  assert.equal(calls,1,'stale notice must not undo a newer edit');assert.equal(notice(),null);
  await act(()=>history.project('project-B'));assert.equal(notice(),null);
  await act(()=>history.record(removal()));assert.ok(notice(),'dismissal is project scoped');
  await act(async()=>{assert.equal(await history.undo(async()=>{throw Error('temporary failure');}),false);});
  assert.ok(notice());assert.match(document.body.textContent,/Undo was not confirmed/);
  let release,pending;
  await act(()=>{pending=history.undo(()=>new Promise(resolve=>{release=resolve;}));});
  assert.equal(undo().disabled,true);assert.match(notice().textContent,/Restoring/);
  await act(async()=>{release({revisions:{}});await pending;});assert.equal(notice(),null);
 }finally{await act(()=>root.unmount());history.project(null);await server.close();Object.assign(globalThis,previous);dom.window.close();}
});
