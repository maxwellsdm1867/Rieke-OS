import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
test('cell addition survives its first trace loading but rejects a changed cell while resolving',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'}),oldFetch=globalThis.fetch;
 let release,renderer;const saved=[],selected=[];
 globalThis.fetch=async()=>{await new Promise(resolve=>{release=resolve;});return {ok:true,status:200,json:async()=>({query_revision:'scope',offset:0,total:2,epochs:[{epoch_uuid:'a1',cell_uuid:'a'},{epoch_uuid:'a2',cell_uuid:'a'}]})};};
 try{
  const {default:Tools}=await server.ssrLoadModule('/src/components/IncomingSelectionTools.jsx');
  const props={source:{kind:'protocol',protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},query:'',queryRevision:'scope'},cells:[{cell_uuid:'a',epochs:2},{cell_uuid:'b',epochs:2}],targets:[],cell:{cell_uuid:'a'},epoch:null,disabled:false,savedCount:0,onSave:(ids,value)=>saved.push({ids,value}),onSelect:ids=>selected.push(ids),onReview:()=>{throw Error('No implicit review');}};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Tools,props));});const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  await act(async()=>{void button('Add cell').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...props,epoch:{epoch_uuid:'a1'}})));
  await act(async()=>release());assert.deepEqual(saved,[{ids:['a1','a2'],value:true}]);
  await act(async()=>{void button('Add cell').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...props,cell:{cell_uuid:'b'},epoch:{epoch_uuid:'b1'}})));
  await act(async()=>release());assert.equal(saved.length,1,'late cell result must not save');
  await act(async()=>renderer.update(React.createElement(Tools,{...props,cell:null,targets:['a1']})));
  await act(async()=>button('Deselect all').props.onClick());assert.deepEqual(selected,[[]]);assert.equal(saved.length,1,'deselecting must not remove persisted decisions');
  const browsing={...props,cells:[props.cells[0]],cell:null,focusUuid:'a1',epoch:null};
  await act(async()=>renderer.update(React.createElement(Tools,browsing)));
  await act(async()=>{void button('Select all').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...browsing,epoch:{epoch_uuid:'a1'}})));
  await act(async()=>release());assert.deepEqual(selected,[[],['a1','a2']],'loading metadata for the same focused UUID must not cancel whole-view selection');assert.equal(saved.length,1);
  await act(async()=>renderer.unmount());
 }finally{globalThis.fetch=oldFetch;await server.close();}
});
