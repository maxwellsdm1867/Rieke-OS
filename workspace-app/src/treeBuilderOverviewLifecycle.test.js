import test from 'node:test';
import assert from 'node:assert/strict';
import {useLayoutEffect,createElement} from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

test('incoming overview fences candidate scope, filters and late responses',async()=>{
 const h=await createWorkflowHarness(),pending=[],fields=[{id:'date',label:'Recording date',category:'Recording'}];
 h.fixture.respond=(url,options,fallback)=>url.pathname==='/explore/field-registry'?{fields,generation:{metadata:'m'}}:url.pathname.endsWith('/tree-fields')?new Promise(resolve=>pending.push({url,options,resolve})):fallback();
 const props={protocolId:'protocol-A',projectId:'p',readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'},summaryEnabled:false,queryString:'cell=one',revision:0,value:['date'],onChange:()=>{},preview:{count:9},loading:false};
 const text=()=>h.root.findAll(node=>node.type==='small').map(node=>node.children.join('')).join(' ');
 try{
  const Builder=await h.component('TreeBuilder'),paints=[];
  function Observed(p){useLayoutEffect(()=>{paints.push(text());},[p.queryString]);return createElement(Builder,p);}
  await h.mount(Observed,props);await h.waitFor(()=>pending.length===1);
  for(const [key,value] of Object.entries({candidate_scope_revision:'scope-1',splits:'date',cell:'one'}))assert.equal(pending[0].url.searchParams.get(key),value);
  await h.act(()=>pending[0].resolve({fields:[{...fields[0],distinct_count:7,missing_count:2}],total:9}));
  await h.waitFor(()=>text().includes('7 values · 2 not recorded'));
  await h.render(Observed,{...props,queryString:'cell=two'});await h.waitFor(()=>pending.length===2);
  assert.ok(!paints.at(-1).includes('7 values'),'old scope hidden before passive effects');
  await h.render(Observed,{...props,queryString:'cell=three'});await h.waitFor(()=>pending.length===3);
  assert.equal(pending[1].options.signal.aborted,true);
  await h.act(()=>pending[2].resolve({fields:[{...fields[0],distinct_count:3}],total:3}));await h.waitFor(()=>text().includes('3 values'));
  await h.act(()=>pending[1].resolve({fields:[{...fields[0],distinct_count:99}],total:99}));await h.settle(10);
  assert.ok(!text().includes('99 values'));assert.ok(text().includes('3 values'));
  assert.equal(h.root.findAllByProps({className:'metadata-summary-status'}).length,0);
 }finally{await h.close();}
});
