import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';

for(const kind of ['queue','summary'])test(`${kind} preparation is explicit and retires across project switch/unmount`,async t=>{
 const previous={window:globalThis.window,fetch:globalThis.fetch};
 globalThis.window={...(previous.window||{}),addEventListener(){},removeEventListener(){}};
 const calls=[];let ready=false,held,latest,holdRead=false,releaseRead;
 globalThis.fetch=async(url,options)=>{
  calls.push({url,options});
  if(url.endsWith('/prepare'))return new Promise(resolve=>held=resolve);
  if(!ready)return new Response(JSON.stringify({status:'preparing',preparation:{status:'pending',resource:'workbench'}}),{status:202});
  if(holdRead)await new Promise(resolve=>releaseRead=resolve);
  return new Response(JSON.stringify({contract_version:1,queue_revision:'fresh',candidates:[],pending_epoch_count:3,pending_cell_count:1,
   capabilities:{frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}}));
 };
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:useQueue}=await server.ssrLoadModule('/src/incoming-workbench/useWorkbenchQueue.js');
 const {default:usePreparation}=await server.ssrLoadModule('/src/incoming-workbench/useWorkbenchPreparation.js');
 const {useResource}=await server.ssrLoadModule('/src/api.js');
 const {default:View}=await server.ssrLoadModule('/src/protocol-overview/ui/ViewPreparation.jsx');
 function Queue({project}){latest=useQueue('p',project,undefined,project);return React.createElement(View,{resource:latest});}
 function Summary({project}){latest=usePreparation(useResource('/workbench/summary',project),project,'/workbench/summary',project);return React.createElement(View,{resource:latest});}
 let renderer;
 const render=async project=>act(()=>{const element=React.createElement(kind==='queue'?Queue:Summary,{project});if(renderer)renderer.update(element);else renderer=TestRenderer.create(element);});
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();Object.assign(globalThis,previous);});
 await render('A');assert.equal(calls.length,1);assert.equal(latest.data,null);
 await act(()=>renderer.root.findByType('button').props.onClick());assert.equal(calls.length,2);assert.equal(latest.preparing,true);
 const abandoned=held;
 await render('B');assert.equal(calls[1].options.signal.aborted,true);assert.equal(calls.length,3);
 await act(()=>abandoned(new Response('{}')));assert.equal(calls.length,3);assert.equal(latest.data,null);
 await act(()=>renderer.root.findByType('button').props.onClick());ready=true;holdRead=true;
 await act(()=>held(new Response('{}')));assert.equal(calls.length,5);assert.equal(latest.data,null);assert.equal(latest.preparing,true);
 assert.equal(renderer.root.findByType('button').props.disabled,true);
 await act(()=>latest.prepare());assert.equal(calls.length,5,'no second preparation while the fresh queue is held');
 holdRead=false;await act(()=>releaseRead());assert.equal(latest.data.queue_revision,'fresh');assert.equal(latest.preparation,undefined);
 ready=false;await act(()=>latest.reload());assert.equal(latest.data,null);
 await act(()=>renderer.root.findByType('button').props.onClick());const final=held;
 await act(()=>renderer.unmount());renderer=null;assert.equal(calls.at(-1).options.signal.aborted,true);
 const count=calls.length;await act(()=>final(new Response('{}')));assert.equal(calls.length,count);
});

test('import review exposes preparation without claiming zero pending or enabling merge',async t=>{
 const previous=globalThis.window;globalThis.window={...(previous||{}),addEventListener(){},removeEventListener(){}};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {ImportSuggestions}=await server.ssrLoadModule('/src/protocol-overview/ui/ProtocolSuggestion.jsx');
 let renderer,prepares=0;
 t.after(async()=>{await act(()=>renderer?.unmount());await server.close();globalThis.window=previous;});
 await act(()=>{renderer=TestRenderer.create(React.createElement(ImportSuggestions,{projectId:'project',autoOpenJobUuid:'job',
  workbenchSummary:{data:null,error:'Prepare this view to continue.',preparation:{status:'pending',resource:'workbench'},reload(){},prepare(){prepares++;}}}));});
 const text=JSON.stringify(renderer.toJSON());
 assert.match(text,/Pending updates unavailable/);assert.doesNotMatch(text,/No pending protocol updates|Refreshing catalog totals/);
 const buttons=renderer.root.findAllByType('button');assert.equal(buttons.filter(node=>node.props['aria-label']==='Hold to merge all').length,0);
 await act(()=>buttons.find(node=>node.children.includes('Prepare view')).props.onClick());assert.equal(prepares,1);
});
