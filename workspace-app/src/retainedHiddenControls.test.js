import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

test('busy hidden views release global Escape handlers and modal top-layer ownership',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const dom=new JSDOM('<main></main><button id="outside">Current view</button>');
 const previous={window:globalThis.window,document:globalThis.document};Object.assign(globalThis,{window:dom.window,document:dom.window.document});
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
 const root=createRoot(document.querySelector('main'));
 const [{RetainedWorkspaceViews,useRetainedViewProtection},{default:Actions},{default:Types},{default:Folder}]=await Promise.all([
  server.ssrLoadModule('/src/retainedWorkspaceViews.js'),server.ssrLoadModule('/src/epoch-browser/ui/InspectorActions.jsx'),
  server.ssrLoadModule('/src/incoming-workbench/ui/IncomingCellTypes.jsx'),server.ssrLoadModule('/src/file-picker/ui/FolderBrowserDialog.jsx')]);
 const request=async()=>({directory:'/owned',parent:'/',folders:[],locations:[],has_more:false,offset:0,total:0,empty:true});
 function Panel(){useRetainedViewProtection({busy:true});return React.createElement(React.Fragment,null,
  React.createElement(Actions,{actions:[]}),React.createElement(Types,{cells:[],count:0,trigger:'Types'}),
  React.createElement(Folder,{request,onChoose(){},initialDirectory:'/owned'}));}
 const presentation={remember(){}};
 const render=key=>act(async()=>{root.render(React.createElement(RetainedWorkspaceViews,{route:{page:'history',key},projectId:'p',projectPath:'/owned/p',presentation,render:route=>route.key==='a'?React.createElement(Panel):React.createElement('p',null,'Current view')}));});
 try{
  await render('a');const dialog=document.querySelector('dialog');assert.equal(dialog.open,true);
  await act(()=>document.querySelector('.inspector-more > button').click());
  await act(()=>document.querySelector('.incoming-cell-type-trigger').click());
  assert.equal(document.querySelector('.incoming-cell-type-trigger').getAttribute('aria-expanded'),'true');
  await render('b');assert.equal(document.querySelector('dialog'),dialog,'hidden owner remains mounted');assert.equal(dialog.open,false,'hidden modal leaves top layer');
  const outside=document.querySelector('#outside');outside.focus();
  const escape=new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});
  await act(()=>document.dispatchEvent(escape));
  assert.equal(escape.defaultPrevented,false,'hidden capture and bubbling handlers cannot consume Escape');assert.equal(document.activeElement,outside);
  await render('a');assert.equal(dialog.open,true);assert.equal(document.querySelector('.inspector-more > button').getAttribute('aria-expanded'),'true');
  const visibleEscape=new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});
  await act(()=>document.dispatchEvent(visibleEscape));assert.equal(visibleEscape.defaultPrevented,true,'visible controls reconnect');
 }finally{await act(()=>root.unmount());await server.close();Object.assign(globalThis,previous);dom.window.close();}
});
