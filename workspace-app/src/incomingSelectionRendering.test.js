import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('').trim();
const create=()=>createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
test('Select all publishes every scoped ID, ignores focus loading, and refuses a changed view before publication',async()=>{
 const server=await create(),oldFetch=globalThis.fetch;let release,renderer;const selected=[],commands=[];
 globalThis.fetch=async()=>{await new Promise(resolve=>{release=resolve;});return {ok:true,status:200,json:async()=>({query_revision:'scope',offset:0,total:2,epochs:[{epoch_uuid:'a1',cell_uuid:'a'},{epoch_uuid:'a2',cell_uuid:'a'}]})};};
 try{
  const {default:Tools}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingSelectionTools.jsx');
  const props={source:{kind:'protocol',protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},query:'',queryRevision:'scope'},cells:[{cell_uuid:'a',epochs:2}],targets:[],epoch:null,disabled:false,onSelect:(ids,command)=>{selected.push(ids);commands.push(command);},onMerge:()=>assert.fail('selection must not merge')};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Tools,props));});const button=name=>renderer.root.findAllByType('button').find(node=>label(node)===name);
  await act(async()=>{void button('Select all').props.onClick();});await act(async()=>renderer.update(React.createElement(Tools,{...props,epoch:{epoch_uuid:'a1'}})));await act(async()=>release());assert.deepEqual(selected,[['a1','a2']]);assert.deepEqual(commands,[{treeSelection:{on:true}}]);
  await act(async()=>{void button('Select all').props.onClick();});await act(async()=>renderer.update(React.createElement(Tools,{...props,source:{...props.source,query:'cell_type=OFF'}})));await act(async()=>release());assert.equal(selected.length,1);assert.match(label(renderer.root),/Incoming view changed/);
  await act(async()=>renderer.update(React.createElement(Tools,{...props,targets:['a1']})));await act(async()=>button('Deselect all').props.onClick());assert.deepEqual(selected,[['a1','a2'],[]]);assert.deepEqual(commands,[{treeSelection:{on:true}},{treeSelection:{on:false}}]);
 }finally{if(renderer)await act(async()=>renderer.unmount());globalThis.fetch=oldFetch;await server.close();}
});
test('Merge uses only explicit selected IDs, including zero while an epoch or cell is focused',async()=>{
 const server=await create();let renderer;const merged=[];
 try{
  const {default:Tools}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingSelectionTools.jsx');
  const props={source:{},cells:[{cell_uuid:'c',epochs:69}],targets:[],epoch:{epoch_uuid:'one'},cell:{cell_uuid:'c'},disabled:false,onSelect:()=>{},onMerge:ids=>merged.push(ids)};
  const render=async extra=>{await act(async()=>{const element=React.createElement(Tools,{...props,...extra});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});return renderer.root.findByProps({className:'primary'});};
  let b=await render({});assert.equal(label(b),'Merge (0 epochs)');assert.equal(b.props.disabled,true);
  b=await render({targets:['one']});assert.equal(label(b),'Merge (1 epoch)');await act(async()=>b.props.onClick());assert.deepEqual(merged,[['one']]);
  b=await render({targets:['one','two'],disabled:true});assert.equal(label(b),'Merge (2 epochs)');assert.equal(b.props.disabled,true);
  b=await render({targets:[null]});assert.equal(label(b),'Merge (count unavailable)');assert.equal(b.props.disabled,true);
  await render({targets:['one'],viewSelected:true});assert.ok(renderer.root.findAllByType('button').some(node=>label(node)==='Return to all'));assert.doesNotMatch(label(renderer.root),/Import|Merge all|Merge selected/);
 }finally{if(renderer)await act(async()=>renderer.unmount());await server.close();}
});
