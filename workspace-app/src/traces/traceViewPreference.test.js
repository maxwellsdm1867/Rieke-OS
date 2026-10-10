import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('viewing preferences validate restored input, strip authority and isolate protocol providers',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {normalizeTraceViewPreference:normalize,TraceViewPreferenceProvider:Provider,useTraceViewPreference:usePreference}=await server.ssrLoadModule('/src/traces/traceViewPreference.jsx');
 const whole={kind:'whole',start:0,count:20000};
 for(const invalid of [null,{},'sample',{kind:'sample',start:-1,count:2},{kind:'sample',start:0,count:20001},{kind:'sample',start:0,count:0},{kind:'sample',start:Infinity,count:5},{kind:'sample',start:0,count:'20'}])assert.deepEqual(normalize(invalid),whole);
 const sample={kind:'sample',start:30000,count:1000};
 assert.deepEqual(normalize({...sample,epoch_uuid:'not-a-preference',read_context:{root:'untrusted'}}),sample);
 let renderer;
 function Viewer({name}){const [value,onChange]=usePreference();return React.createElement('view-probe',{name,value,onChange});}
 function Protocol({initial,children}){const [value,onChange]=React.useState(()=>normalize(initial));return React.createElement(Provider,{value,onChange},children);}
 try{
  await act(async()=>{renderer=TestRenderer.create(React.createElement(React.Fragment,null,
   React.createElement(Protocol,{key:'a'},React.createElement(Viewer,{name:'inspect'}),React.createElement(Viewer,{name:'workbench'})),
   React.createElement(Protocol,{key:'b'},React.createElement(Viewer,{name:'other'})),React.createElement(Viewer,{name:'search'})));
  });
  const view=name=>renderer.root.findByProps({name}).findByType('view-probe').props;
  await act(async()=>view('inspect').onChange(sample));
  assert.deepEqual(view('workbench').value,sample);assert.deepEqual(view('other').value,whole);assert.deepEqual(view('search').value,whole);
  await act(async()=>view('workbench').onChange({...sample,kind:'whole'}));assert.equal(view('inspect').value.kind,'whole');assert.equal(view('inspect').value.start,30000);
 }finally{await act(async()=>renderer?.unmount());await server.close();}
});
