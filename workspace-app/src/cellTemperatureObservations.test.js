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
  if(url==='/api/cells/cell/qc?projection=display')data={cell:{cell_uuid:'cell',label:'Cell 1',recording_rigs:['EF'],recording_rig_missing:false},families:[],recording_seconds:125,temperature:{points:[{value:30,start_time:'09/30/2026 12:00:00'}],recorded_count:1,missing_count:500,units:'degC',range:{min:30,max:30}},counts:{epochs:501},resting_voltage:{status:'unavailable'}};
  else if(url.startsWith('/api/cells/cell/qc/temperature')){const offset=Number(new URL(url,'http://fixture').searchParams.get('offset'));data={total:501,has_more:offset<500,observations:[{epoch_uuid:`epoch-${offset}`,cell_uuid:'cell',recording_order:offset+1,epoch_number:2,start_time:'09/30/2026 12:00:00',status:'missing',value:null,units:null}]};}
  else if(url.startsWith('/api/epochs/'))data={epoch_uuid:url.split('/').at(-1),cell_uuid:'cell',streams:[],parameters:{},properties:{bathTemperature:null},date:'2026-09-30',metadata:{}};
  else data={fields:[]};
  return {ok:true,json:async()=>data};
 };
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 let renderer;
 try{
  const {default:CellQC}=await server.ssrLoadModule("/src/cell-qc/ui/CellQC.jsx");
  await act(async()=>{renderer=TestRenderer.create(React.createElement(CellQC,{cellUuid:'cell',revision:0}));});
  const metrics=renderer.root.findByProps({className:'qc-metrics'}).findAllByType('strong').map(node=>node.children.join('')).join(' ');
  assert.ok(metrics.includes('EF'));assert.ok(metrics.includes('2m 5s'));assert.ok(!metrics.includes('Not established'));
  assert.equal(renderer.root.findAllByProps({className:'qc-trend'}).length,0,'Closed conditions do not construct the chart');
  const conditions=renderer.root.findAllByType('details').find(node=>node.props.className==='qc-temperature');
  await act(async()=>conditions.props.onToggle({currentTarget:{open:true}}));
  assert.equal(renderer.root.findAllByProps({className:'qc-trend'}).length,1);
  await act(async()=>conditions.props.onToggle({currentTarget:{open:false}}));
  assert.equal(renderer.root.findAllByProps({className:'qc-trend'}).length,0);
  const findButton=label=>renderer.root.findAllByType('button').find(button=>button.children.includes(label));
  const card=renderer.root.findByProps({className:'qc-temperature-metric'});
  assert.equal(card.props['aria-expanded'],false);
  await act(async()=>card.props.onClick());
  assert.ok(JSON.stringify(renderer.toJSON()).includes('Unmeasured'));
  assert.ok(JSON.stringify(renderer.toJSON()).includes('No reading available'));
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

test('temperature warnings preserve units and distinguish unknown and unmeasured trials',async()=>{
 const previous=globalThis.fetch;
 let temperature;
 globalThis.fetch=async url=>({ok:true,json:async()=>url.includes('/qc?')?{cell:{cell_uuid:'warning-cell'},families:[],temperature,counts:{epochs:3}}:{fields:[]}});
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 let renderer;
 try{
  const {default:CellQC}=await server.ssrLoadModule('/src/cell-qc/ui/CellQC.jsx');
  for(const [value,units,missing,unknown,label,warn] of [[27.9,'degC',0,0,'27.9 °C',true],[28,'degC',0,0,'28 °C',false],[30,'degC',2,0,'30 °C',true],[0,null,0,1,'Unknown',true],[null,null,3,0,'Unmeasured',true]]){
   temperature={recorded_count:value===null?0:1,missing_count:missing,unknown_units_count:unknown,units,range:value===null?null:{min:value,max:value},points:[]};
   await act(async()=>{renderer=TestRenderer.create(React.createElement(CellQC,{cellUuid:'warning-cell',revision:Math.random()}));});
   const card=renderer.root.findByProps({className:'qc-temperature-metric'});
   const strong=card.findByType('strong');
   assert.equal(strong.children.join(''),label);
   assert.equal(strong.props.className==='qc-temperature-warning',warn);
   if(missing)assert.ok(JSON.stringify(card.toJSON?.()||renderer.toJSON()).includes('no reading available'));
   await act(async()=>renderer.unmount());renderer=null;
  }
 }finally{if(renderer)await act(async()=>renderer.unmount());await server.close();globalThis.fetch=previous;}
});
