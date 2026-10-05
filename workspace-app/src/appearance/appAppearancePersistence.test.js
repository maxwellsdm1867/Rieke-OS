import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {useAppAppearance} from './appAppearance.js';
import {APPEARANCE_CACHE} from './appearanceThemes.js';

async function fixture(t,request,bridge){
 const previousWindow=globalThis.window,previousStorage=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
 const saved=new Map();
 globalThis.window={riekeDesktop:bridge};
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)}});
 let value,renderer;
 function Host(){value=useAppAppearance({request});return null;}
 t.after(async()=>{await act(async()=>renderer?.unmount());globalThis.window=previousWindow;if(previousStorage)Object.defineProperty(globalThis,'localStorage',previousStorage);else delete globalThis.localStorage;});
 await act(async()=>{renderer=TestRenderer.create(React.createElement(Host));});
 return{get value(){return value;},saved,async choose(theme){await act(async()=>value.chooseTheme(theme));}};
}

test('failed preference write restores the last saved theme and reports a save failure',async t=>{
 const h=await fixture(t,async(_path,options)=>{if(options?.method==='POST')throw new Error('Preference disk is read-only');return{theme:'fred',icon:'rieke'};});
 await h.choose('dark');
 assert.equal(h.value.theme,'fred');assert.equal(h.value.icon,'rieke');assert.equal(h.value.errorPhase,'save');assert.equal(h.value.busy,false);
 assert.equal(JSON.parse(h.saved.get(APPEARANCE_CACHE)).theme,'fred');
});

test('a failed native icon update keeps the successfully persisted color theme',async t=>{
 let failIcon=false,saved={theme:'bright',icon:'disco'};
 const h=await fixture(t,async(_path,options)=>{if(options?.method==='POST')saved={theme:options.body.theme,icon:'disco'};return saved;},{async applyAppIcon(){if(failIcon)throw new Error('Dock icon is unavailable');}});
 failIcon=true;await h.choose('dark');
 assert.equal(saved.theme,'dark');assert.equal(h.value.theme,'dark');assert.equal(h.value.errorPhase,'icon');
 assert.equal(JSON.parse(h.saved.get(APPEARANCE_CACHE)).theme,'dark');
});

test('loading failures are distinguished from writing failures and can recover',async t=>{
 const h=await fixture(t,async(_path,options)=>{if(options?.method==='POST')return{theme:options.body.theme,icon:'disco'};throw new Error('Saved preference is unavailable');});
 assert.equal(h.value.errorPhase,'load');assert.equal(h.value.loading,false);
 await h.choose('dark');assert.equal(h.value.theme,'dark');assert.equal(h.value.error,'');assert.equal(h.value.errorPhase,null);
});

test('System follows device changes and stops following after a fixed theme is chosen',async t=>{
 const previousDocument=globalThis.document,listeners=new Set();
 const media={matches:false,addEventListener:(_event,fn)=>listeners.add(fn),removeEventListener:(_event,fn)=>listeners.delete(fn)};
 globalThis.document={documentElement:{dataset:{},style:{}},querySelector:()=>null};
 t.after(()=>{globalThis.document=previousDocument;});
 const h=await fixture(t,async(_path,options)=>({theme:options?.body?.theme||'system',icon:'disco'}));
 globalThis.window.matchMedia=()=>media;
 await h.choose('light');await h.choose('system');
 assert.equal(globalThis.document.documentElement.dataset.theme,'light');assert.equal(listeners.size,1);
 await act(async()=>{media.matches=true;for(const notify of listeners)notify();});
 assert.equal(h.value.theme,'system');assert.equal(globalThis.document.documentElement.dataset.theme,'dark');
 await h.choose('light');assert.equal(listeners.size,0);
 assert.equal(globalThis.document.documentElement.dataset.theme,'light');
});
