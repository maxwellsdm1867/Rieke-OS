import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';
import {incomingTagSummary} from './incoming-workbench/incomingTagSummary.js';
import {compactAnnotationTags,incomingRowAnnotation} from "./annotations/annotationTags.js";
const cell={tag:'Quality',profile_uuid:'alice',author_name:'Alice'};
const other={...cell,profile_uuid:'bob',author_name:'Bob'};
const row=(epoch_uuid,cell_uuid,cell_tags=[],epoch_tags=[])=>({epoch_uuid,cell_uuid,annotations:{cell_tags,epoch_tags},curation:{tags:['dataset-only']}});

test('incoming page tag summary deduplicates inherited/direct tags, authors and repeated epoch UUIDs',()=>{
 const a=row('a','cell-one',[cell,other],[cell]),b=row('b','cell-one',[cell]),c=row('c','cell-two',[],[other]);
 const result=incomingTagSummary({total:443,epochs:[a,b,a,c]});
 assert.deepEqual([result.loaded,result.total,result.cells,result.epochs],[3,443,2,3]);
 assert.equal(result.tags.length,1);assert.equal(result.tags[0].tag,'Quality');assert.deepEqual([result.tags[0].cells,result.tags[0].epochs],[2,3]);
 assert.deepEqual(result.tags[0].authors.map(a=>[a.kind,a.profile_uuid]),[['cell','alice'],['cell','bob'],['epoch','alice'],['epoch','bob']]);
 assert.equal(result.cellTags['cell-one'].length,2);assert.equal(result.cellTags['cell-two'],undefined,'an epoch tag must not become a cell annotation');
 assert.equal(incomingTagSummary({total:1,epochs:[a,c]}),null,'impossible coverage must be unavailable');
});

test('unavailable annotation data is never an empty or zero-tag receipt',()=>{
 for(const page of [null,{}, {total:2,epochs:[{epoch_uuid:'a',cell_uuid:'c'}]},{total:2,epochs:[{...row('a','c'),annotations:{cell_tags:[]}}]}])assert.equal(incomingTagSummary(page),null);
 const known=incomingTagSummary({total:2,epochs:[row('a','c'),row('b','d')]});assert.equal(known.tags.length,0);assert.equal(known.epochs,0);assert.equal(known.loaded,2);
});

test('incoming effective tag pills retain cell/epoch provenance and author identity without dataset-tag mixing',()=>{
 const chips=compactAnnotationTags(row('a','c',[cell],[other]),'effective');
 assert.equal(chips.length,1);assert.match(chips[0].title,/Inherited cell: Alice \(alice\)/);assert.match(chips[0].title,/Direct epoch: Bob \(bob\)/);assert.doesNotMatch(chips[0].title,/dataset-only/);
});

test('compact incoming summary filters exact shared tag only on explicit click and labels page coverage',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 let renderer;const calls=[];
 try{
  const {default:Summary}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingTagSummary.jsx');
  const summary=incomingTagSummary({total:443,epochs:[row('a','c',[cell])]});
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Summary,{summary,onFilter:v=>calls.push(v)}));});
  const text=JSON.stringify(renderer.toJSON());assert.match(text,/Incoming page/);assert.match(text,/443/);assert.match(text,/frozen membership/);assert.equal(calls.length,0);
  const button=renderer.root.findByType('button');assert.match(button.props.title,/Inherited cell · Alice \(alice\)/);
  await act(async()=>button.props.onClick());assert.deepEqual(calls,[{all:[{field:'annotations/effective/tags',operator:'contains',value:'Quality'}]}]);
  await act(async()=>renderer.update(React.createElement(Summary,{summary:null,onFilter:v=>calls.push(v),disabled:true})));
  assert.equal(renderer.root.findAllByType('button').length,0);assert.match(JSON.stringify(renderer.toJSON()),/Tag counts unavailable/);
  await act(async()=>renderer.unmount());
 }finally{await server.close();}
});

test('incoming rows expose shared tag descriptions without pills and retain explicit navigation',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const oldFetch=globalThis.fetch,requests=[],selected=[],focused=[];let renderer;
 const a={...row('a','cell-one',[cell]),start_time:'2026-10-01 12:00:00',date:'2026-10-01',cell_label:'Cell1',protocol_name:'Fixture'};
 globalThis.fetch=async(path,options={})=>{requests.push({path,method:options.method||'GET'});return {ok:true,status:200,json:async()=>({offset:0,epochs:[a],total:1,query_revision:'scope',expected_binding_version:1})};};
 try{
  const {default:Tree}=await server.ssrLoadModule('/src/epoch-browser/ui/InspectionCellTree.jsx');
  const props={cells:[{cell_uuid:'cell-one',label:'Cell1',date:'2026-10-01',epochs:1,annotations:{cell_tags:[cell]}}],source:{kind:'protocol',protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope',cohort_key:'fixture'}},targets:[],setTargets:v=>selected.push(v),onFocus:(...args)=>focused.push(args),onSelectCell:()=>{},revision:0};
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Tree,props));});
  const date=renderer.root.findByProps({className:'cell-tree-date'});await act(async()=>date.props.onToggle({currentTarget:{open:true}}));
  const branch=renderer.root.findByProps({className:'cell-tree-cell has-shared-tags'});await act(async()=>branch.props.onToggle({currentTarget:{open:true}}));
  assert.ok(renderer.root.findAll(node=>typeof node.props.className==='string'&&node.props.className.includes('cell-tree-epoch has-shared-tags')).length);
  const pills=renderer.root.findAll(node=>node.props.className==='annotation-row-pills');assert.equal(pills.length,0);
  const button=renderer.root.findByProps({'aria-label':'Inspect 2026-10-01 · Cell1 epoch 1'});
  assert.match(button.props['aria-description'],/Inherited cell tag: Quality · Alice \(alice\)/);
  assert.equal(button.props['aria-pressed'],false);assert.equal(button.props['aria-current'],undefined);
  assert.match(branch.findByType('summary').props['aria-description'],/Cell tag: Quality · Alice \(alice\)/);
  assert.deepEqual(selected,[]);assert.deepEqual(focused,[]);
  await act(async()=>button.props.onClick({}));assert.equal(focused[0][0],'a');assert.deepEqual(selected,[],'inspection must not change incoming selection');
  await act(async()=>renderer.update(React.createElement(Tree,{...props,disabled:true,navigationDisabled:true})));
  assert.equal(renderer.root.findByProps({'aria-label':'Inspect 2026-10-01 · Cell1 epoch 1'}).props.disabled,true);
  assert.ok(requests.length>0);assert.ok(requests.every(r=>r.method==='GET'));
  await act(async()=>renderer.unmount());
 }finally{globalThis.fetch=oldFetch;await server.close();}
});

test('row highlighting is authoritative shared annotation metadata, not dataset tags or unavailable data',()=>{
 assert.equal(incomingRowAnnotation({curation:{tags:['dataset']}}),undefined);
 assert.equal(incomingRowAnnotation(),undefined);
 assert.equal(incomingRowAnnotation(row('a','c',[],[other]),'cell'),undefined);
 assert.match(incomingRowAnnotation(row('a','c',[cell],[other])),/Direct epoch tag: Quality · Bob \(bob\)/);
});
