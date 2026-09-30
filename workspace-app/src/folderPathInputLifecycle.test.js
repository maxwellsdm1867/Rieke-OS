import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
async function mountedPicker(selection){
 const old=globalThis.window,values=[];let chooseCount=0;
 globalThis.window={riekeDesktop:{chooseProjectFolder:async()=>{chooseCount++;return selection;}}};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {default:FolderPathInput}=await server.ssrLoadModule('/src/components/FolderPathInput.jsx');let renderer;
 await act(async()=>{renderer=TestRenderer.create(React.createElement(FolderPathInput,{value:'/chosen/project',onChange:value=>values.push(value),title:'Project folder',purpose:'existing'}),{createNodeMock:()=>({focus(){}})});});
 return {values,get input(){return renderer.root.findByType('input');},get button(){return renderer.root.findByType('button');},get chooseCount(){return chooseCount;},
   async browse(){await act(async()=>renderer.root.findByType('button').props.onClick());},
   async close(){try{await act(async()=>renderer.unmount());}finally{await server.close();if(old===undefined)delete globalThis.window;else globalThis.window=old;}}};
}
test('folder path is a read-only selection with an accessible native Browse action',async()=>{
 const h=await mountedPicker('/selected/folder');try{
   assert.equal(h.input.props.readOnly,true);assert.equal(h.input.props.value,'/chosen/project');
   assert.equal(h.button.props['aria-label'],'Browse: Project folder');await h.browse();
   assert.equal(h.chooseCount,1);assert.deepEqual(h.values,['/selected/folder']);
 }finally{await h.close();}
});
test('canceling the native folder chooser preserves the existing selection',async()=>{
 const h=await mountedPicker(null);try{await h.browse();assert.deepEqual(h.values,[]);assert.equal(h.input.props.value,'/chosen/project');assert.equal(h.button.props.disabled,false);}
 finally{await h.close();}
});
