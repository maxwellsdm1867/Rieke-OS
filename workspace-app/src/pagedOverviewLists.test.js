import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const cell=id=>({cell_uuid:id,label:id,cell_type:'ON-midget',date:'2026-10-20',epochs:1,exported:0});
for(const [name,path] of [['Overview','/overview'],['ProtocolInfographic','/protocols/p/overview']])test(`${name} loads a bounded second window and keeps the full count distinct from loaded summaries`,async t=>{
 const calls=[],key=`__paging${name}`;globalThis[key]=async(p,options)=>{calls.push({p,options});return {project:{project_uuid:'project'},cells:[cell('b')],cells_total:2,cells_next:null};};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
  name:'paging-api',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/useOverviewCells.js')&&id==='../api.js')return '\0paging-api';if(id.endsWith('/RecordingSize.jsx'))return '\0paging-size';},
  load(id){if(id==='\0paging-api')return `export const api=(...args)=>globalThis[${JSON.stringify(key)}](...args);`;if(id==='\0paging-size')return 'export default function Size(){return null;}';}
 }]});
 const {default:View}=await server.ssrLoadModule(`/src/protocol-overview/ui/${name}.jsx`);let renderer;
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();delete globalThis[key];});
 const data={definition:{protocol_uuid:'p'},project:{project_uuid:'project'},cells:[cell('a')],cells_total:2,cells_next:1,counts:{cells:2,epochs:2},protocols:[],sources:[]};
 await act(()=>{renderer=TestRenderer.create(React.createElement(View,{data}));});
 const root=renderer.root;
 assert(root.findAllByType('strong').some(x=>x.children.join('')==='2'),'headline shows full count');
 assert(root.findAllByType('p').some(x=>x.children.join('').includes('loaded cells')));
 const more=root.findAllByType('button').find(x=>x.children.includes('Load more cells'));assert(more);
 await act(()=>more.props.onClick());assert.equal(calls.length,1);assert.equal(calls[0].p,`${path}?cells_limit=200&cells_after=1`);
 assert.equal(root.findAllByProps({className:'cell-row'}).length,2);
 assert(!root.findAllByType('button').some(x=>x.children.includes('Load more cells')));
});
