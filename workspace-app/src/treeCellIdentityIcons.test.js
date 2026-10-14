import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from './test-support/isolatedVite.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {fileURLToPath} from 'node:url';

test('only exact cell and cell-type levels get identity glyphs; labels and joint nodes never classify',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {default:Icon}=await server.ssrLoadModule('/src/tree-browser/ui/TreeBranchIcon.jsx');
  const render=(field,node)=>renderToStaticMarkup(React.createElement(Icon,{field,node}));
  assert.match(render('cell',{value:'uuid',cell_type:'RGC/ON-parasol',label:'OFF midget'}),/var\(--cell-on\)/);
  assert.match(render('cell type',{value:'RGC/OFF-midget',label:'ON parasol'}),/var\(--cell-off\)/);
  assert.match(render('cell',{value:'uuid',label:'ON parasol'}),/var\(--cell-unknown\)/);
  assert.match(render('cell type',{value:null,missing:true}),/var\(--cell-unknown\)/);
  for(const field of ['date','group','block','protocol','parameters/type','metadata/other'])assert.doesNotMatch(render(field,{value:'RGC/ON-parasol',cell_type:'RGC/ON-parasol'}),/tree-cell-identity-icon/);
  assert.doesNotMatch(render('cell',{value:'uuid',components:[{field:'cell'}]}),/tree-cell-identity-icon/);
 }finally{await server.close();}
});

for(const [name,extra] of [['ColumnTree',{}],['ColumnTree',{design:true}],['HierarchyTree',{}]])test(`${name} ${extra.design?'Edit Tree':'browse'} renders recorded identity without extra reads`,async()=>{
 const h=await createWorkflowHarness();
 const page={revision:'a'.repeat(64),kind:'branches',path:[],depth:0,offset:0,limit:60,total:2,total_epochs:4,count:4,selection:{count:4},split_order:['cell'],levels:[{field:'cell',label:'Cell'}],ancestors:[],epochs:[],has_more:false,branches:[{key:'c1',path:['c1'],label:'Display label',value:'c1',cell_type:'RGC/ON-parasol',count:2},{key:'c2',path:['c2'],label:'ON parasol display name',value:'c2',cell_type:null,count:2}]};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?page:fallback();
 try{
  const Tree=await h.component(name);await h.mount(Tree,{protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},splits:'cell',revision:0,...extra});
  await h.waitFor(()=>h.root.findAllByProps({className:'tree-cell-identity-icon'}).length===2);
  const glyphs=h.root.findAllByProps({className:'tree-cell-identity-icon'}).map(n=>n.findByType('svg'));
  assert.equal(glyphs[0].props.style.color,'var(--cell-on)');assert.equal(glyphs[1].props.style.color,'var(--cell-unknown)');
  assert.ok(glyphs.every(n=>n.props['aria-hidden']===true));
  assert.equal(h.fixture.requests.filter(r=>r.path.includes('/cells/')).length,0);
 }finally{await h.close();}
});
