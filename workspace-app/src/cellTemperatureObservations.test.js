import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('temperature opens all-epoch pages and inspects the exact source without a characterization family',async()=>{
 const previous=globalThis.fetch,requests=[];
 globalThis.fetch=async url=>{
  requests.push(url);let data;
  if(url==='/api/cells/cell/qc')data={cell:{cell_uuid:'cell',label:'Cell 1'},families:[],temperature:{recorded_count:1,missing_count:500,units:null,range:{min:30,max:30}},counts:{epochs:501},resting_voltage:{status:'unavailable'}};
  else if(url.startsWith('/api/cells/cell/qc/temperature')){const offset=Number(new URL(url,'http://fixture').searchParams.get('offset'));data={total:501,has_more:offset<500,observations:[{epoch_uuid:`epoch-${offset}`,cell_uuid:'cell',recording_order:offset+1,epoch_number:2,start_time:'09/30/2026 12:00:00',status:'missing',value:null,units:null}]};}
  else if(url.startsWith('/api/epochs/'))data={epoch_uuid:url.split('/').at(-1),cell_uuid:'cell',streams:[],parameters:{},properties:{bathTemperature:null},date:'2026-09-30',metadata:{}};
  else data={fields:[]};
  return {ok:true,json:async()=>data};
 };
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 let renderer;
 try{
  const {default:CellQC}=await server.ssrLoadModule('/src/components/CellQC.jsx');
  await act(async()=>{renderer=TestRenderer.create(React.createElement(CellQC,{cellUuid:'cell',revision:0}));});
  const findButton=label=>renderer.root.findAllByType('button').find(button=>button.children.includes(label));
  const card=renderer.root.findByProps({className:'qc-temperature-metric'});
  assert.equal(card.props['aria-expanded'],false);
  await act(async()=>card.props.onClick());
  assert.ok(JSON.stringify(renderer.toJSON()).includes('Missing temperature'));
  assert.ok(JSON.stringify(renderer.toJSON()).includes('Unit not recorded'));
  for(let index=0;index<10;index++)await act(async()=>findButton('Next').props.onClick());
  assert.equal(findButton('Next').props.disabled,true);
  await act(async()=>findButton('Inspect epoch').props.onClick());
  assert.ok(requests.includes('/api/epochs/epoch-500'));
  assert.ok(JSON.stringify(renderer.toJSON()).includes('Source epoch '));
  assert.equal(requests.filter(url=>url.includes('/response')).length,0);
 }finally{
  if(renderer)await act(async()=>renderer.unmount());
  await server.close();globalThis.fetch=previous;
 }
});
