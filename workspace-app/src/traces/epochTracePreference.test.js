import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?text(node.children):'';

test('EpochViewer retains Sample bounds across browse/tree remounts and an empty selection',async()=>{
 const server=await createServer({
  root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,
  server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',
  // Keep actual EpochViewer, retained layout, Trace, and request lifecycle. Only
  // unrelated tree reads are omitted; its supplied trace pane mounts normally.
  plugins:[{name:'trace-preference-tree-fixture',enforce:'pre',transform(_code,id){
   if(id.endsWith('/tree-browser/ui/PagedTree.jsx'))return 'export default function Tree({trailingPane}){return trailingPane??null;}';
  }}],
 });
 const {default:EpochViewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');
 const {WorkspaceRequestProvider}=await server.ssrLoadModule('/src/workspaceRequest.js');
 const calls=[];let renderer;
 const port={identity:'page-preference-owner',request:async path=>{
  assert.match(path,/\/trace\?/,'only the active trace may request data');
  const query=new URLSearchParams(path.split('?')[1]),start=+query.get('start'),count=+query.get('count');
  calls.push({start,count});
  return {epoch_uuid:'epoch-a',stream_uuid:'stream-a',start,count,total_samples:67500,sample_rate:10000,units:'pA',source_sha256:'source',decimated:false,values:Array(count).fill(1)};
 }};
 const epoch={epoch_uuid:'epoch-a',streams:[{kind:'responses',uuid:'stream-a',sample_count:67500,sample_rate:10000,units:'pA'}]};
 const layout={treeOpen:false,metadataOpen:false,sizes:{columns:'1fr',tree:200,treeMax:400,metadata:300,metadataMax:500}};
 const render=async({designMode=false,selected=true,pageKey='same-page'}={})=>act(async()=>{
  const element=React.createElement(WorkspaceRequestProvider,{port},React.createElement(EpochViewer,{
   key:pageKey,epoch:selected?epoch:null,designMode,layout,columnTree:{selected:selected?'epoch-a':null},
  }));
  if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);
 });
 const view=()=>renderer.root.findByProps({'aria-label':'Recorded response viewer'});
 const button=label=>view().findAllByType('button').find(node=>text(node.props.children)===label);
 const assertSample=()=>{
  assert.equal(button('Sample').props['aria-pressed'],true);
  assert.match(text(renderer.toJSON()),/1,000 \/ 67,500 samples/);
  assert.deepEqual(calls.at(-1),{start:30000,count:1000});
 };
 try{
  await render();assert.equal(button('Whole epoch').props['aria-pressed'],true);
  await act(async()=>button('Sample').props.onClick());
  const inputs=view().findByType('form').findAllByType('input');
  await act(async()=>{inputs[0].props.onChange({target:{value:'30000'}});inputs[1].props.onChange({target:{value:'1000'}});});
  await act(async()=>view().findByType('form').props.onSubmit({preventDefault(){}}));
  assertSample();
  let before=calls.length;
  await render({designMode:true});assertSample();assert.equal(calls.length,before+1,'tree preview remount performs the retained Sample request');
  assert.equal(renderer.root.findAllByProps({'aria-label':'Raw recording preview'}).length,1);
  before=calls.length;
  await render();assertSample();assert.equal(calls.length,before+1,'browse remount performs the retained Sample request');
  before=calls.length;
  await render({selected:false});assert.equal(renderer.root.findAllByProps({'aria-label':'Recorded response viewer'}).length,0);
  assert.equal(calls.length,before,'empty selection does not request a trace');
  await render();assertSample();assert.equal(calls.length,before+1);
  await render({pageKey:'fresh-page'});assert.equal(button('Whole epoch').props['aria-pressed'],true);
  assert.match(text(renderer.toJSON()),/67,500 \/ 67,500 samples/);
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});
