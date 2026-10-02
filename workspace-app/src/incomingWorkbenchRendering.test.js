import test from 'node:test';
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
const label=node=>node.children.map(child=>typeof child==='string'?child:label(child)).join('');
const root=fileURLToPath(new URL('..',import.meta.url));
const create=()=>createServer({root,configFile:false,cacheDir:root+'/.review-vite-cache',optimizeDeps:{noDiscovery:true,include:[]},esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});

test('actual Workbench renders authoritative queue and session worklist controls',async()=>{
 const server=await create();
 try{
  const {default:Workbench}=await server.ssrLoadModule('/src/components/IncomingWorkbench.jsx');
  const item={protocol_uuid:'history',protocol_name:'VariableHistoryNoiseCurInject',candidate_revision_uuid:'candidate-immutable',baseline_revision_uuid:'base-immutable',status:'pending',created_at:'2026-10-02T01:00:00Z',source_filename:'incoming.h5',diff_counts:{added:12,removed:0,changed:2},next_count:50};
  const props={protocolId:'history',suggestions:[item,{...item,protocol_uuid:'other',protocol_name:'Other'}],projectId:'project'};
  const html=renderToStaticMarkup(React.createElement(Workbench,props));
  for(const text of ['Needs review','candidate-immutable','base-immutable','incoming.h5','Earlier unmerged updates'])assert.ok(html.includes(text),text);
  assert.doesNotMatch(html,/>Other</);assert.match(html,/disabled=""[^>]*>Accept &amp; export/);
  let renderer,saved;
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Workbench,{...props,onSession:value=>{saved=value;}}));});
  await act(async()=>renderer.root.findByType('input').props.onChange());
  assert.deepEqual(saved.selected,['history:candidate-immutable']);
  assert.ok(renderer.root.findAllByType('button').some(button=>label(button)==='Review selected'));
  assert.equal(saved.active,null);
  await act(async()=>renderer.unmount());
  const restored=renderToStaticMarkup(React.createElement(Workbench,{...props,session:saved}));
  assert.match(restored,/1 selected proposals/);
  const dir=fileURLToPath(new URL('../../review-evidence',import.meta.url));
  await mkdir(dir,{recursive:true});await writeFile(`${dir}/workbench-component.html`,html);
 }finally{await server.close();}
});
test('App and affected dialog/browser/sidebar JSX transform from isolated source',async()=>{
 const server=await create();
 try{
  for(const file of ['App.jsx','components/MetadataExplorer.jsx','components/IncomingExportDialog.jsx','components/ExportSelectionDialog.jsx','components/ProtocolSidebar.jsx']){
   const result=await server.transformRequest(`/src/${file}`);assert.ok(result?.code.length>0,file);
  }
 }finally{await server.close();}
});
