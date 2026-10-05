import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const text=node=>Array.isArray(node)?node.map(text).join(' '):typeof node==='string'?node:node?.children?.map(text).join(' ')||'';

test('summary public controls preserve pending cancellation, stale retry and exact preferred fields',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 let root,cancelled=0,retried=0,updated;
 try{
  const {default:Status}=await server.ssrLoadModule('/src/summary-jobs/ui/SummaryStatus.jsx');
  const {default:Preferences}=await server.ssrLoadModule('/src/summary-jobs/ui/SummaryPreferences.jsx');
  await act(async()=>{root=TestRenderer.create(React.createElement(Status,{state:{status:'pending',cancel:()=>cancelled++}}));});
  await act(async()=>root.root.findByType('button').props.onClick());assert.equal(cancelled,1);
  await act(async()=>root.update(React.createElement(Status,{state:{status:'stale',retry:()=>retried++}})));
  assert.match(text(root.toJSON()),/current generation/);
  await act(async()=>root.root.findByType('button').props.onClick());assert.equal(retried,1);
  await act(async()=>root.update(React.createElement(Preferences,{fields:[{id:'kept'},{id:'next'},{id:'joint/hidden'}],preferences:{enabled:true,value:{fields:['kept']},update:fields=>updated=fields,error:'Storage failed'}})));
  assert.deepEqual(root.root.findAllByType('option').map(option=>option.props.value),['','next']);
  await act(async()=>root.root.findByType('select').props.onChange({target:{value:'next'}}));assert.deepEqual(updated,['kept','next']);
  await act(async()=>root.root.findByType('button').props.onClick());assert.deepEqual(updated,[]);
  assert.match(text(root.toJSON()),/Storage failed/);
 }finally{await act(async()=>root?.unmount());await server.close();}
});
