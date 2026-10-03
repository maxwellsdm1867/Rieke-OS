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
  await act(async()=>{void button('Import (2 epochs)').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...props,epoch:{epoch_uuid:'a1'}})));
  await act(async()=>release());assert.deepEqual(saved,[{ids:['a1','a2'],value:true}]);
  await act(async()=>{void button('Import (2 epochs)').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...props,cell:{cell_uuid:'b'},epoch:{epoch_uuid:'b1'}})));
  await act(async()=>release());assert.equal(saved.length,1,'late cell result must not save');
  await act(async()=>renderer.update(React.createElement(Tools,{...props,cell:null,targets:['a1']})));
  await act(async()=>button('Deselect all').props.onClick());assert.deepEqual(selected,[[]]);assert.equal(saved.length,1,'deselecting must not remove persisted decisions');
  const browsing={...props,cells:[props.cells[0]],cell:null,focusUuid:'a1',epoch:null};
  await act(async()=>renderer.update(React.createElement(Tools,browsing)));
  await act(async()=>{void button('Select all').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...browsing,epoch:{epoch_uuid:'a1'}})));
  await act(async()=>release());assert.deepEqual(selected,[[],['a1','a2']],'loading metadata for the same focused UUID must not cancel whole-view selection');assert.equal(saved.length,1);
  const replaced=[],filtered={...browsing,filtered:true,onReplace:ids=>{replaced.push(ids);return true;}};
  await act(async()=>renderer.update(React.createElement(Tools,filtered)));
  await act(async()=>{void button('Use only this view in draft').props.onClick();});
  await act(async()=>renderer.update(React.createElement(Tools,{...filtered,disabled:true})));
  await act(async()=>release());assert.deepEqual(replaced,[],'an invalidated receipt must not replace saved decisions');
  assert.match(label(renderer.root),/Incoming view changed/,'cancellation must offer a visible retry instead of silently doing nothing');
  await act(async()=>renderer.update(React.createElement(Tools,filtered)));
  await act(async()=>{void button('Use only this view in draft').props.onClick();});
  await act(async()=>release());assert.deepEqual(replaced,[['a1','a2']]);
  await act(async()=>renderer.update(React.createElement(Tools,{...filtered,cells:[],freshCells:[]})));
  assert.equal(button('Use only this view in draft').props.disabled,true);assert.equal(button('Select all').props.disabled,true);
  await act(async()=>renderer.unmount());
 }finally{globalThis.fetch=oldFetch;await server.close();}
});

test('Import labels the exact current scope, handles singular/zero/unavailable and preserves draft-only clicks',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 let renderer;const saved=[];
 try{
  const {default:Tools}=await server.ssrLoadModule('/src/components/IncomingSelectionTools.jsx');
  const props={source:{},cells:[{cell_uuid:'c',epochs:69}],targets:[],cell:null,epoch:null,disabled:false,savedCount:0,onSave:(ids,add)=>saved.push({ids,add}),onSelect:()=>{},onReview:()=>{throw Error('Import must not mark reviewed');}};
  const render=async extra=>{await act(async()=>{const element=React.createElement(Tools,{...props,...extra});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});return renderer.root.findByProps({className:'primary'});};
  let b=await render({});assert.equal(label(b),'Import (0 epochs)');assert.equal(b.props.disabled,true);
  b=await render({epoch:{epoch_uuid:'one'}});assert.equal(label(b),'Import (1 epoch)');assert.equal(b.props.disabled,false);
  assert.match(b.props['aria-description'],/review draft/);
  b=await render({cell:{cell_uuid:'c',epochs:999},epoch:{epoch_uuid:'one'}});assert.equal(label(b),'Import (69 epochs)','uses scoped receipt, not the cell object or focused epoch');
  b=await render({cell:{cell_uuid:'missing'}});assert.equal(label(b),'Import (count unavailable)');assert.equal(b.props.disabled,true);
  b=await render({targets:['one','two']});assert.equal(label(b),'Import (2 epochs)');
  await act(async()=>b.props.onClick());assert.deepEqual(saved,[{ids:['one','two'],add:true}]);
  b=await render({targets:['one','two'],disabled:true});assert.equal(b.props.disabled,true);
  assert.ok(renderer.root.findAllByType('button').some(n=>label(n)==='Review selected'));
  await act(async()=>renderer.unmount());
 }finally{await server.close();}
});
