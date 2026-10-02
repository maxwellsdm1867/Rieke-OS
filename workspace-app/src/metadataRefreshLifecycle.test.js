import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const text=node=>typeof node==='string'?node:node?.children?.map(text).join(' ')||'';
test('metadata refresh remains a metadata operation and ignores legacy MATLAB mask proposals',async()=>{
 const prior={fetch:globalThis.fetch,document:globalThis.document},calls=[];let changed=0,root;
 const refresh={sources:3,epochs:12,protocols:1,reused_sources:2,rebuilt_sources:1,elapsed_seconds:0.25,completed_at:'2026-09-30T12:00:00Z'};
 const masks={checked:true,candidates:[{dataset_uuid:'legacy-export',name:'Legacy mask',changed_count:2,included_count:4,epoch_count:5}]};
 globalThis.document={addEventListener(){},removeEventListener(){}};
 globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>path==='/api/metadata/refresh'?{refresh,masks,warnings:[]}:{status:'ready',last_refresh:refresh,masks}};};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 try{const {default:MetadataRefresh}=await server.ssrLoadModule('/src/components/MetadataRefresh.jsx');await act(async()=>{root=TestRenderer.create(React.createElement(MetadataRefresh,{revision:0,onChange:()=>changed++}),{createNodeMock:()=>({contains:()=>true})});});
  await act(async()=>root.root.findByProps({'aria-label':'Metadata refresh status'}).props.onClick());
  assert.doesNotMatch(text(root.toJSON()),/MATLAB|selection masks|Apply updated mask/);
  await act(async()=>root.root.findByProps({'aria-label':'Refresh project metadata'}).props.onClick());
  assert.match(text(root.toJSON()),/Metadata refresh completed/);assert.equal(changed,1);
  assert.equal(calls.filter(call=>call.path==='/api/metadata/refresh').length,1);assert.equal(calls.some(call=>call.path.includes('/masks/')),false);
 }finally{await act(async()=>root?.unmount());await server.close();for(const [key,value]of Object.entries(prior)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});
