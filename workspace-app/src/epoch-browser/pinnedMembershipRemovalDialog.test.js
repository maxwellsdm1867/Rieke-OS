import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('removal confirmation names the pin and count, reassures about recordings and Undo, and supports Cancel/Escape',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Dialog}=await server.ssrLoadModule('/src/epoch-browser/ui/PinnedMembershipRemovalDialog.jsx');
 let root,shown=0,closed=0,cancelled=0,confirmed=0,prevented=0;
 const props={protocolName:'ON parasol pin',count:30,onClose:()=>cancelled++,onConfirm:()=>confirmed++};
 const render=async value=>act(()=>{const element=React.createElement(Dialog,value);if(root)root.update(element);else root=TestRenderer.create(element,{createNodeMock:element=>element.type==='dialog'?{showModal:()=>shown++,close:()=>closed++}:null});});
 try{
  await render(props);assert.equal(shown,1);assert.equal(confirmed,0);
  const content=JSON.stringify(root.toJSON());
  for(const expected of ['ON parasol pin','30 epochs','recordings stay in your project','Other protocols and existing exported files remain unchanged','Undo afterward'])assert.ok(content.includes(expected),expected);
  const buttons=root.root.findAllByType('button');
  await act(()=>buttons.find(button=>button.children.includes('Cancel')).props.onClick());
  await act(()=>root.root.findByType('dialog').props.onCancel({preventDefault:()=>prevented++}));
  assert.equal(cancelled,2);assert.equal(prevented,1);assert.equal(confirmed,0);
  await render({...props,count:1,stale:true});
  assert.ok(JSON.stringify(root.toJSON()).includes('1 epoch'));
  assert.equal(root.root.findAllByType('button').find(button=>button.props.className==='primary').props.disabled,true);
  assert.match(root.root.findByProps({role:'alert'}).children.join(''),/selection or dataset changed/);
  await render({...props,count:1});
  await act(()=>root.root.findAllByType('button').find(button=>button.props.className==='primary').props.onClick());
  assert.equal(confirmed,1);
 }finally{await act(()=>root?.unmount());await server.close();}
 assert.equal(closed,1);
});
