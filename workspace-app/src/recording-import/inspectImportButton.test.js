import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
test('import click and one-second hold are separate, cancellable, single-use gestures',async t=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:Button}=await server.ssrLoadModule('/src/recording-import/ui/InspectImportButton.jsx');
 let renderer,inspect=0,merge=0;let props={identity:'a',onInspect:()=>inspect++,onMerge:()=>merge++};
 const render=async()=>act(()=>{if(renderer)renderer.update(React.createElement(Button,props));else renderer=TestRenderer.create(React.createElement(Button,props));});const button=()=>renderer.root.findByType('button');
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();});await render();t.mock.timers.enable({apis:['setTimeout']});
 await act(()=>button().props.onPointerDown({button:0}));await act(()=>t.mock.timers.tick(999));assert.equal(merge,0);await act(()=>button().props.onPointerUp());await act(()=>button().props.onClick());assert.equal(inspect,1);
 await act(()=>button().props.onPointerDown({button:0}));await act(()=>t.mock.timers.tick(1000));assert.equal(merge,1);await act(()=>button().props.onPointerUp());await act(()=>button().props.onClick());assert.equal(inspect,1);
 for(const cancel of ['onPointerLeave','onPointerCancel','onBlur']){await act(()=>button().props.onPointerDown({button:0}));await act(()=>button().props[cancel]());await act(()=>t.mock.timers.tick(1000));assert.equal(merge,1);}
 await act(()=>button().props.onPointerDown({button:0}));props={...props,disabled:true};await render();await act(()=>t.mock.timers.tick(1000));assert.equal(merge,1);
 props={...props,disabled:false,identity:'b'};await render();await act(()=>button().props.onPointerDown({button:0}));await act(()=>t.mock.timers.tick(1000));assert.equal(merge,2);await act(()=>button().props.onPointerUp());await act(()=>button().props.onClick());
 const key={key:' ',preventDefault(){}};await act(()=>button().props.onKeyDown(key));await act(()=>button().props.onKeyUp(key));assert.equal(inspect,2);
 await act(()=>button().props.onKeyDown(key));await act(()=>button().props.onKeyDown({key:'Escape'}));await act(()=>button().props.onKeyUp(key));await act(()=>t.mock.timers.tick(1000));assert.equal(merge,2);assert.equal(inspect,2);
 await act(()=>button().props.onPointerDown({button:0}));props={...props,identity:'c'};await render();await act(()=>t.mock.timers.tick(1000));assert.equal(merge,2);
 await act(()=>button().props.onPointerDown({button:0}));await act(()=>renderer.unmount());renderer=null;await act(()=>t.mock.timers.tick(1000));assert.equal(merge,2);t.mock.timers.reset();
});
