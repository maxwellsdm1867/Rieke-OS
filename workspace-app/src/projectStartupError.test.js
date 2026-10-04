import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('startup recovery details can be copied, repeated failure stays visible, recovery clears it',async()=>{
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
  const old=Object.getOwnPropertyDescriptor(globalThis,'navigator');let renderer,copied,deny=false;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async value=>{if(deny)throw Error('denied');copied=value;}}}});
  try{
    const {default:ErrorView}=await server.ssrLoadModule('/src/components/ProjectStartupError.jsx');
    const message='Disco could not open this project. The bundled MySQL client is missing. Recovery log: /owned/log';
    await act(async()=>{renderer=TestRenderer.create(React.createElement(ErrorView,{message}));});
    await act(async()=>renderer.root.findByType('button').props.onClick());assert.equal(copied,message);
    await act(async()=>renderer.update(React.createElement(ErrorView,{message:''})));assert.equal(renderer.toJSON(),null);
    await act(async()=>renderer.update(React.createElement(ErrorView,{message})));assert.match(JSON.stringify(renderer.toJSON()),/MySQL client is missing/);
    deny=true;await act(async()=>renderer.root.findByType('button').props.onClick());assert.match(JSON.stringify(renderer.toJSON()),/Copy unavailable/);
    await act(async()=>renderer.update(React.createElement(ErrorView,{message:''})));assert.equal(renderer.toJSON(),null);
    await act(async()=>renderer.update(React.createElement(ErrorView,{message:'Unclassified error'})));assert.equal(renderer.root.findAllByType('button').length,0);
  }finally{if(renderer)await act(async()=>renderer.unmount());await server.close();if(old)Object.defineProperty(globalThis,'navigator',old);else delete globalThis.navigator;}
});
