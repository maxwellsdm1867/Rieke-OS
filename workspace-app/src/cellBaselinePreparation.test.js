import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('resting-voltage supporting detail reads prepared anchors and labels the curve unvalidated',async()=>{
 const previous=globalThis.fetch,requests=[];
 const supporting={preparation_status:'complete',anchors:[{epoch_uuid:'exact-epoch',block_uuid:'exact-block',source_sha256:'sha',start_time:'09/30/2026 12:00:05',recording_time_seconds:5,mean_mV:-60,sample_count:10,flags:{possible_spike_first_2ms:true}}],recordings:[{source_sha256:'sha',start_time:'09/30/2026 12:00:00',duration_seconds:10,time_basis:'Seconds from first recorded epoch in this cell/source.'}],interpolation:{status:'unavailable',reason:'Historical curves are not reused.'}};
 globalThis.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>({cell:{label:'Cell 1'},families:[],counts:{epochs:2},temperature:{},resting_voltage:{status:'unavailable',reason:'Review raw estimates before validating a curve.',supporting_measurements:supporting}})};};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});let renderer;
 try{
  const {default:CellQC}=await server.ssrLoadModule("/src/cell-qc/ui/CellQC.jsx");
  await act(async()=>{renderer=TestRenderer.create(React.createElement(CellQC,{cellUuid:'cell',revision:0}));});
  const button=renderer.root.findAllByType('button').find(button=>button.children.includes('View prepared estimates'));
  await act(async()=>button.props.onClick());
  const output=JSON.stringify(renderer.toJSON());
  for(const text of ['exact-epoch','exact-block','Recording time (s)','Raw 1 ms mean (mV)','possible spike first 2ms','Curve unvalidated','Validated resting-voltage curve: unavailable'])assert.ok(output.includes(text),text);
  assert.deepEqual(requests,['/api/cells/cell/qc']);
 }finally{if(renderer)await act(async()=>renderer.unmount());await server.close();globalThis.fetch=previous;}
});
