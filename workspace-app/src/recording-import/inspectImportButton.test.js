import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
test('separate inspection and merge buttons enforce hold-only merge and retire stale gestures',async t=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Button}=await server.ssrLoadModule('/src/recording-import/ui/InspectImportButton.jsx');
 let renderer,inspect=0,merge=0;let props={identity:'a',onInspect:()=>inspect++,onMerge:()=>merge++};
 const render=async()=>act(()=>{if(renderer)renderer.update(React.createElement(Button,props));else renderer=TestRenderer.create(React.createElement(Button,props));});
 const buttons=()=>renderer.root.findAllByType('button'),hold=()=>buttons().find(node=>node.props['aria-label']==='Hold to merge'),inspectButton=()=>buttons().find(node=>node.props.className==='primary');
 const event={button:0,preventDefault(){}},key=name=>({key:name,preventDefault(){}});
 const press=()=>act(()=>hold().props.onPointerDown(event)),tick=ms=>act(()=>t.mock.timers.tick(ms)),release=async()=>{await act(()=>hold().props.onPointerUp());await act(()=>hold().props.onClick(event));};
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();});await render();t.mock.timers.enable({apis:['setTimeout']});
 assert.equal(buttons().length,2);assert.equal(inspectButton().props.onPointerDown,undefined);assert.equal(inspectButton().props.onKeyDown,undefined);
 await act(()=>inspectButton().props.onClick());assert.equal(inspect,1);await tick(1000);assert.equal(merge,0);
 await press();await tick(999);await release();assert.equal(merge,0);assert.equal(inspect,1);
 await press();await tick(1000);await tick(1000);await release();assert.equal(merge,1);assert.equal(inspect,1);
 for(const cancel of ['onPointerLeave','onPointerCancel','onBlur']){await press();await act(()=>hold().props[cancel]());await tick(1000);assert.equal(merge,1);}
 await press();props={...props,disabled:true};await render();await tick(1000);assert.equal(merge,1);assert.ok(buttons().every(b=>b.props.disabled));
 props={...props,disabled:false};await render();
 for(const name of [' ','Enter']){
  await act(()=>hold().props.onKeyDown(key(name)));await tick(999);await act(()=>hold().props.onKeyUp(key(name)));assert.equal(inspect,1);
  const before=merge;await act(()=>hold().props.onKeyDown(key(name)));await tick(1000);await act(()=>hold().props.onKeyDown({...key(name),repeat:true}));await tick(1000);await act(()=>hold().props.onKeyUp(key(name)));assert.equal(merge,before+1);
 }
 assert.equal(merge,3);
 await act(()=>hold().props.onKeyDown(key(' ')));await act(()=>hold().props.onKeyDown(key('Escape')));await act(()=>hold().props.onKeyUp(key(' ')));await tick(1000);assert.equal(merge,3);assert.equal(inspect,1);
 await press();props={...props,identity:'b'};await render();await tick(1000);assert.equal(merge,3);
 await press();const onMerge=props.onMerge;props={...props,onMerge:undefined};await render();await tick(1000);assert.equal(merge,3);assert.equal(buttons().length,1);
 props={...props,onMerge};await render();await press();await act(()=>renderer.unmount());renderer=null;await tick(1000);assert.equal(merge,3);t.mock.timers.reset();
});
