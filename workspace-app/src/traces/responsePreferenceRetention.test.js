import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('last explicit response preference survives window changes and exact-epoch restoration without label matching',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const [{default:Trace},{WorkspaceRequestProvider},{normalizeTraceViewPreference:normalize}]=await Promise.all([
  server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx'),server.ssrLoadModule('/src/workspaceRequest.js'),server.ssrLoadModule('/src/traces/traceViewPreference.jsx')]);
 const calls=[];let tree,snapshot,key=0;
 const port={identity:'response-retention',request:async path=>{
  const query=new URLSearchParams(path.split('?')[1]),epoch_uuid=path.split('/')[2],stream_uuid=query.get('stream_uuid'),start=+query.get('start'),count=+query.get('count');
  calls.push({epoch_uuid,stream_uuid,start,count});return {epoch_uuid,stream_uuid,start,count,total_samples:256,sample_rate:10000,units:'pA',values:Array(count).fill(stream_uuid==='s2'?2:1)};
 }};
 const epoch=(id='e',ids=['s1','s2'])=>({epoch_uuid:id,streams:ids.map(uuid=>({kind:'responses',uuid,device:'Same label',sample_count:256,sample_rate:10000,units:'pA'}))});
 function Session({record,initial,mode}){
  const [preference,setPreference]=React.useState(()=>normalize(initial));snapshot=preference;
  return React.createElement(WorkspaceRequestProvider,{port},React.createElement(React.Activity,{mode},React.createElement(Trace,{epoch:record,viewPreference:preference,onViewPreference:setPreference})));
 }
 const render=(record,initial=snapshot,{fresh=false,mode='visible'}={})=>act(async()=>{
  if(fresh)key++;
  const element=React.createElement(Session,{key,record,initial,mode});tree?tree.update(element):tree=TestRenderer.create(element);
 });
 const response=uuid=>tree.root.findAllByType('button').find(node=>node.props.title===uuid);
 const button=text=>tree.root.findAllByType('button').find(node=>node.props.children===text);
 try{
  await render(epoch());assert.equal(calls.at(-1).stream_uuid,'s1');
  await act(()=>response('s2').props.onClick());assert.equal(calls.at(-1).stream_uuid,'s2');assert.deepEqual(snapshot.responseSelection,{epoch_uuid:'e',stream_uuid:'s2'});
  await act(()=>button('Sample').props.onClick());assert.deepEqual(snapshot.responseSelection,{epoch_uuid:'e',stream_uuid:'s2'});
  await act(()=>button('Whole epoch').props.onClick());assert.deepEqual(snapshot.responseSelection,{epoch_uuid:'e',stream_uuid:'s2'});
  await act(()=>tree.root.findByProps({'aria-label':'Trace plot. Left/Right move the sample cursor. Shift and Left/Right pan. Plus and minus zoom. Home resets.'}).props.onKeyDown({key:'+',preventDefault(){}}));
  assert.equal(snapshot.kind,'sample');assert.equal(snapshot.responseSelection.stream_uuid,'s2');
  const saved=JSON.parse(JSON.stringify(snapshot));
  await render(epoch(),saved,{mode:'hidden'});await render(epoch(),saved);assert.equal(response('s2').props['aria-pressed'],true);
  await render(epoch(),saved,{fresh:true});assert.equal(response('s2').props['aria-pressed'],true);assert.equal(calls.at(-1).stream_uuid,'s2');
  await render(epoch('other'),saved,{fresh:true});assert.equal(response('s1').props['aria-pressed'],true);assert.equal(calls.at(-1).epoch_uuid,'other');assert.equal(calls.at(-1).stream_uuid,'s1');
  await render(epoch('e',['replacement','replacement2']),saved,{fresh:true});assert.equal(response('replacement').props['aria-pressed'],true,'duplicate device labels never identify a stored response');assert.equal(calls.at(-1).stream_uuid,'replacement');
  const before=calls.length;
  await render(epoch('e',[]),saved,{fresh:true});assert.equal(calls.length,before,'saved UUID is not a read descriptor');
  await render(epoch(),saved);assert.equal(response('s2').props['aria-pressed'],true);assert.equal(calls.length,before+1);assert.equal(calls.at(-1).stream_uuid,'s2','late descriptors can validate the saved exact pair');
 }finally{await act(()=>tree?.unmount());await server.close();}
});
