import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

// The same registered bytes must read identically on Project overview and Data stores.
const sizes=[219_500_000,305_000_000,168_700_000,365_600_000,301_200_000];
const stores=sizes.map((size,index)=>({source_sha256:`s${index}`,filename:`s${index}.h5`,source_path:`/s${index}.h5`,size_bytes:size,recorded_size_bytes:size,metadata_size_bytes:14_580_000,file_status:'available',state:{version:1,archived:index===4,query_excluded:false},counts:{cells:1,epochs:1}}));
const total=sizes.reduce((sum,size)=>sum+size,0);
const inventory={data_stores:stores,counts:{total:5,active:4,archived:1,frozen:0},storage:{recordings:{known_bytes:total,size_bytes:total,unavailable_files:0,files:5},parsed_metadata:{known_bytes:72_900_000,size_bytes:72_900_000,unavailable_files:0,files:5},combined:{known_bytes:total+72_900_000,size_bytes:total+72_900_000,unavailable_files:0}}};
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?text(node.children):'';

test('Project overview and Data stores show the same size string for the same registered bytes',async()=>{
  const prior={window:globalThis.window,document:globalThis.document,fetch:globalThis.fetch,requestAnimationFrame:globalThis.requestAnimationFrame};
  globalThis.window={innerWidth:1400,innerHeight:1000,addEventListener(){},removeEventListener(){},matchMedia:()=>({matches:true})};
  globalThis.document={body:{},getElementById:()=>null,addEventListener(){},removeEventListener(){}};
  globalThis.requestAnimationFrame=callback=>callback();
  globalThis.fetch=async path=>new Response(JSON.stringify(String(path).startsWith('/api/data-stores')?inventory:{}),{status:200});
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
  let tree;
  try{
    const render=async(Component,props)=>{await act(async()=>{const node=React.createElement(Component,props);tree?tree.update(node):tree=TestRenderer.create(node,{createNodeMock:()=>({focus(){},scrollIntoView(){},showModal(){},close(){},querySelector(){return null;}})});});await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20));});};
    const Overview=(await server.ssrLoadModule('/src/protocol-overview/ui/Overview.jsx')).default;
    await render(Overview,{data:{cells:[],counts:{},protocols:[],sources:stores.map(({source_sha256})=>({source_sha256,filename:'x.h5'}))},projectName:'Fixture'});
    const ribbon=tree.root.findByProps({className:'ov-metric-ribbon'}).children.at(-1);
    const overviewSize=text(ribbon.findByType('strong'));
    assert.match(text(ribbon),/includes archived/,'the project tile names the same scope as Data stores');
    await act(()=>tree.unmount());tree=null;
    const DataStores=(await server.ssrLoadModule('/src/project-workspace/ui/DataStores.jsx')).default;
    await render(DataStores,{});
    const cards=tree.root.findByProps({className:'ds-storage-cards'}).findAllByType('strong').map(text);
    assert.equal(overviewSize,'1.36 GB');assert.equal(cards[0],overviewSize,'H5 recordings matches Project overview');
    assert.equal(cards[2],'1.43 GB','combined size keeps distinct precision from H5 recordings');
    const rows=tree.root.findAllByProps({className:'ds-file-size'}).map(cell=>text(cell.findByType('strong')));
    // The Current list omits the archived store; the storage cards above still include it.
    assert.deepEqual(rows,['219.5 MB','305.0 MB','168.7 MB','365.6 MB']);
  }finally{if(tree)await act(()=>tree.unmount());await server.close();Object.assign(globalThis,prior);}
});
