import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {localInputToUtc} from './typed-query/protocolViewFilter.js';

test('view filter tag rule with an added-after time applies a tag-time predicate and reopens it',async()=>{
 const previous=globalThis.fetch;
 globalThis.fetch=async()=>({ok:true,json:async()=>({tags:[{tag:'good',count:2,authors:[]}]})});
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 let renderer;const applied=[];
 try{
  const {default:ProtocolViewFilter}=await server.ssrLoadModule('/src/typed-query/ui/ProtocolViewFilter.jsx');
  const render=filters=>React.createElement(ProtocolViewFilter,{filters,revision:0,onChange:next=>applied.push(next)});
  await act(async()=>{renderer=TestRenderer.create(render({}));});
  const props=label=>renderer.root.findByProps({'aria-label':label}).props;
  await act(async()=>renderer.root.findByProps({className:'protocol-view-filter'}).findByType('button').props.onClick());
  await act(async()=>renderer.root.findByProps({className:'protocol-view-filter-panel'}).findAllByType('select')[0].props.onChange({target:{value:'rules'}}));
  await act(async()=>props('Tag value 1').onChange({target:{value:'good'}}));
  await act(async()=>props('Tag added after 1').onChange({target:{value:'2026-10-01T09:00'}}));
  await act(async()=>renderer.root.findByProps({className:'protocol-view-filter-panel'}).props.onSubmit({preventDefault(){}}));
  assert.equal(applied.length,1);
  assert.deepEqual(JSON.parse(applied[0].tag_predicate),{all:[{field:'annotations/effective/tag_times',operator:'contains',value:{tag:'good',after:localInputToUtc('2026-10-01T09:00')}}]});
  await act(async()=>renderer.update(render(applied[0])));
  await act(async()=>renderer.root.findByProps({className:'protocol-view-filter'}).findByType('button').props.onClick());
  assert.equal(props('Tag added after 1').value,'2026-10-01T09:00');
  assert.equal(props('Tag added before 1').value,'');
  assert.equal(props('Tag value 1').value,'good');
 }finally{
  if(renderer)await act(async()=>renderer.unmount());
  await server.close();globalThis.fetch=previous;
 }
});
