import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from './test-support/isolatedVite.js';

test('inline type counts expose distinct frozen cells without a popup or hover-only content',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try{
  const {default:Types}=await server.ssrLoadModule('/src/components/IncomingCellTypes.jsx');
  const a={cell_uuid:'a',cell_type:'ON-midget',epochs:999};
  const html=renderToStaticMarkup(React.createElement(Types,{cells:[a,a,{cell_uuid:'b',cell_type:'ON-midget'},{cell_uuid:'c',cell_type:'Unknown'}],count:3}));
  assert.match(html,/aria-label="Frozen proposal cell types"/);
  assert.match(html,/<strong>2<\/strong> ON-midget/);
  assert.match(html,/<strong>1<\/strong> Unclassified/);
  assert.match(html,/role="listitem" tabindex="0"/,'individual pills remain keyboard reachable without an outer frame');
  assert.doesNotMatch(html,/role="list" tabindex=/);
  assert.doesNotMatch(html,/<details|<summary|title=|role="dialog"|incoming-type-disclosure|999/);
  const filtered=renderToStaticMarkup(React.createElement(Types,{cells:[a],count:1,scope:'Filtered incoming view',compact:true}));
  assert.match(filtered,/Filtered incoming view · 1 cell/);
  assert.match(filtered,/<strong>1<\/strong> ON-midget/);
  for(const props of [{cells:null,count:0},{cells:[],count:2}]){
   const unavailable=renderToStaticMarkup(React.createElement(Types,props));
   assert.match(unavailable,/Types unavailable/);assert.doesNotMatch(unavailable,/>0 cells</);
  }
  assert.match(renderToStaticMarkup(React.createElement(Types,{cells:[],count:0})),/>0 cells</);
 }finally{await server.close();}
});
