import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
const generation={metadata:'M',source:'S',annotation:'A',publication:'P'};
const definitions=[{id:'date',label:'Date',category:'Recording',types:['string'],operators:['eq'],path:'date'},...Array.from({length:151},(_,i)=>({id:`parameters/field${i}`,label:`Field ${i}`,category:'Parameters',path:`parameters.field${i}`,types:['number'],operators:['eq','gt']}))];
const registry={fields:definitions,tree_fields:definitions,generation,summary_available:false};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
async function harness({explorerShell=false}={}){
 const requests=[],memory=new Map(),old={fetch:globalThis.fetch,window:globalThis.window,document:globalThis.document,localStorage:globalThis.localStorage};
 globalThis.localStorage={getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value)};
 globalThis.window={innerWidth:1200,innerHeight:800,addEventListener(){},removeEventListener(){}};
 globalThis.document={body:{nodeType:1},addEventListener(){},removeEventListener(){},getElementById:()=>null};
 let respond=(path,options)=>{
  if(path==='/explore/field-registry')return registry;
  if(path==='/explore/predicate-fields'||path.includes('/tree-fields'))return {fields:definitions,total:7};
  if(path==='/explore/summaries')return {status:'pending',request_id:`job-${requests.length}`,generation};
  if(path.endsWith('/cancel'))return {status:'cancelled',generation};
  return {status:'pending',request_id:path.split('/').at(-1),generation};
 };
 globalThis.fetch=async(url,options)=>{const path=url.replace(/^\/api/,'');requests.push({path,options,body:options.body?JSON.parse(options.body):undefined});const response=await respond(path,options);return new Response(JSON.stringify(response?.data??response),{status:response?.httpStatus??200});};
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom',logLevel:'silent',esbuild:{jsx:'automatic'},plugins:[{name:'summary-test-portals',enforce:'pre',resolveId(id,importer){if(explorerShell&&id==='../../epoch-browser/ui/MatchingEpochs.jsx'&&importer?.endsWith('/metadata-explorer/ui/MetadataExplorer.jsx'))return '\0summary-explorer-viewer';if(['../project-preferences/useProjectPreference.js','../../project-preferences/useProjectPreference.js'].includes(id)&&(importer?.endsWith('/typed-query/ui/PredicateDialog.jsx')||explorerShell&&importer?.endsWith('/metadata-explorer/ui/MetadataExplorer.jsx')))return '\0summary-project-preference';if(id==='virtual:summary-portals')return '\0summary-portals';},transform(source,id){if(id.endsWith('/TreeBuilder.jsx')||id.endsWith('/PredicateValueInput.jsx'))return source.replace("from 'react-dom'","from 'virtual:summary-portals'");},load(id){if(id==='\0summary-explorer-viewer')return 'import React from "react";export default props=>React.createElement("explorer-viewer",props);';if(id==='\0summary-project-preference')return 'export const useProjectPreference=(project,field)=>({value:field==="recent_searches"?[]:{},update:async()=>{}});';if(id==='\0summary-portals')return 'export const createPortal=children=>children;';}}]});
 const {default:TreeBuilder}=await server.ssrLoadModule('/src/typed-query/ui/TreeBuilder.jsx');
 const {useRequestedSummaries}=await server.ssrLoadModule('/src/requested-summaries/useRequestedSummaries.js');
 const {useFieldRegistry}=await server.ssrLoadModule('/src/summary-jobs/useFieldRegistry.js');
 const {default:PredicateDialog}=await server.ssrLoadModule('/src/typed-query/ui/PredicateDialog.jsx');
 // Compile the explorer/App source too; the mounted tree exercises the shared builder.
 const {default:MetadataExplorer}=await server.ssrLoadModule('/src/metadata-explorer/ui/MetadataExplorer.jsx');
 await server.ssrLoadModule('/src/App.jsx');
 let root,probe;
 function Probe({kind,request,revision,enabled=true,fallbackPath='/explore/predicate-fields'}){
  const summary=useRequestedSummaries(request||{predicate:{all:[]},summary_fields:[]},{enabled:kind==='summary'&&enabled});
  const fields=useFieldRegistry(revision,fallbackPath);
  probe={summary,fields};return React.createElement('probe',{status:summary.status});
 }
 const h={requests,memory,TreeBuilder,PredicateDialog,MetadataExplorer,Probe,set respond(value){respond=value;},get probe(){return probe;},get root(){return root.root;},async render(Component,props){await act(async()=>{const element=React.createElement(Component,props);if(root)root.update(element);else root=TestRenderer.create(element,{createNodeMock:()=>({showModal(){},close(){},focus(){},closest:()=>null,getBoundingClientRect:()=>({left:50,top:100,bottom:120,width:300}),contains:()=>false})});});},async act(callback){await act(callback);},async settle(ms=0){await act(async()=>{if(ms)await new Promise(resolve=>setTimeout(resolve,ms));for(let i=0;i<12;i++)await Promise.resolve();});},async close(){await act(()=>root?.unmount());await server.close();Object.assign(globalThis,old);},button(label){return root.root.findAllByType('button').find(node=>node.children.some(child=>typeof child==='string'&&child.includes(label)));},text(){return JSON.stringify(root.toJSON());}};
 return h;
}

test('mounted summary hook fences rapid A/B/A navigation, late ready responses and cancellation while preserving typed data',async()=>{
 const h=await harness(),pending=[];
 try{
  h.respond=(path)=>{if(path==='/explore/field-registry')return registry;if(path.endsWith('/cancel'))return {status:'cancelled',generation};const work=deferred();pending.push(work);return work.promise;};
  const request={predicate:{all:[]},summary_fields:['parameters/field150'],generation};
  await h.render(h.Probe,{kind:'summary',request});await h.render(h.Probe,{kind:'summary',request:{...request,scope:{cell_uuid:'B'}}});await h.render(h.Probe,{kind:'summary',request});
  const result={matched_count:2,summaries:{'parameters/field150':{values:[{value:null,type:'null',count:1},{value:'2',type:'string',count:1}],missing_count:0,present_count:2,values_truncated:false}}};
  await h.act(()=>pending[2].resolve({status:'ready',request_id:'new-A',generation,result}));assert.equal(h.probe.summary.status,'ready');assert.deepEqual(h.probe.summary.result,result);
  await h.act(()=>{pending[0].resolve({status:'pending',request_id:'old-A',generation});pending[1].resolve({status:'ready',request_id:'old-B',generation,result:{matched_count:999,summaries:{}}});});await h.settle();
  assert.deepEqual(h.probe.summary.result,result);assert.ok(h.requests.some(item=>item.path==='/explore/summaries/old-A/cancel'));
  await h.render(h.Probe,{kind:'summary',request:{...request,scope:{cell_uuid:'C'}}});await h.act(()=>h.probe.summary.cancel());await h.act(()=>pending[3].resolve({status:'pending',request_id:'late-C',generation}));await h.settle();
  assert.equal(h.probe.summary.status,'cancelled');assert.equal(h.probe.summary.result,null);assert.ok(h.requests.some(item=>item.path==='/explore/summaries/late-C/cancel'));
 }finally{await h.close();}
});
test('mounted registry falls back only when new route is absent; service failures remain visible',async()=>{
 const h=await harness();
 try{
  h.respond=path=>path==='/explore/field-registry'?{httpStatus:404,data:{error:'Not found'}}:{fields:definitions};
  await h.render(h.Probe,{kind:'registry',revision:1});assert.equal(h.probe.fields.supportsSummaries,false);assert.equal(h.probe.fields.data.fields.length,152);assert.ok(h.requests.some(item=>item.path==='/explore/predicate-fields'));
  const start=h.requests.length;h.respond=()=>({httpStatus:500,data:{error:'Publication failed'}});await h.render(h.Probe,{kind:'registry',revision:2});assert.equal(h.probe.fields.data,null);assert.match(h.probe.fields.error,/Publication failed/);assert.equal(h.requests.slice(start).length,1);
 }finally{await h.close();}
});
test('mounted tree defers summaries until chooser open and remains editable with bounded field discovery',async()=>{
 const h=await harness(),changes=[];
 try{
  const axes=['date','parameters/field150','history1'],summaryContext={predicate:{all:[]},protocol_uuid:'A',filters:{cell_uuid:'cell-A',tag:'scoped-tag'}};const props={projectId:'P1',protocolId:'A',summaryContext,value:axes,onChange:value=>changes.push(value),preview:{count:7},loading:false};
  await h.render(h.TreeBuilder,props);await h.settle();
  assert.equal(h.requests.some(item=>item.path==='/explore/summaries'),false,'axis cards use registry labels without background summary work');
  assert.equal(h.requests.some(item=>item.path.includes('/tree-fields')),false);
  assert.doesNotMatch(h.text(),/Metadata summaries|Advanced layout suggestions/);assert.match(h.text(),/history1/);assert.equal(changes.length,0);assert.deepEqual(axes,['date','parameters/field150','history1']);
  assert.equal(h.button('Add a split').props.disabled,false);
  assert.equal(h.button('Summarize all metadata fields'),undefined);
  const before=h.requests.length;await h.act(()=>h.button('Add a split').props.onClick());
  const submit=h.requests.find(item=>item.path==='/explore/summaries');assert.deepEqual(submit.body.summary_fields,['date','parameters/field150']);assert.equal(submit.body.protocol_uuid,'A');assert.deepEqual(submit.body.filters,summaryContext.filters);assert.deepEqual(submit.body.predicate,summaryContext.predicate);
  assert.equal(h.requests.slice(before).some(item=>item.path.includes('/tree-fields')),false);
  assert.ok(h.requests.filter(item=>item.path==='/explore/summaries').every(item=>item.body.summary_fields.length===2));
 }finally{await h.close();}
});

test('tree chooser summaries retain exact scope, reject late results and retire when both choosers close',async()=>{
 const h=await harness(),pending=[],changes=[];
 try{
  h.respond=path=>{
   if(path==='/explore/field-registry')return registry;
   if(path.endsWith('/cancel'))return {status:'cancelled',generation};
   if(path==='/explore/summaries'){const work=deferred();pending.push(work);return work.promise;}
   throw Error(`Unexpected summary request ${path}`);
  };
  const props={projectId:'P1',protocolId:'A',value:['date'],onChange:value=>changes.push(value),preview:{count:7},loading:false};
  // The scoped predicate names field149, so open choosers summarize it with the axes.
  const scope=cell=>({...props,summaryContext:{predicate:{all:[{field:'parameters/field149',operator:'exists'}]},protocol_uuid:'A',filters:{cell_uuid:cell}}});
  const submits=()=>h.requests.filter(item=>item.path==='/explore/summaries');
  const ready=(id,count)=>({status:'ready',request_id:id,generation,result:{matched_count:7,summaries:{'parameters/field149':{
   values:Array.from({length:count},(_,value)=>({value,type:'number',count:1})),missing_count:0,present_count:7,values_truncated:false}}}});
  const closeSplit=()=>h.root.findByProps({'aria-label':'Close split chooser'}).props.onClick();
  const toggleCombined=open=>h.root.findByProps({className:'tb-joint-editor'}).props.onToggle({currentTarget:{open}});
  await h.render(h.TreeBuilder,scope('cell-A'));assert.equal(submits().length,0);
  await h.act(()=>h.button('Add a split').props.onClick());
  assert.deepEqual(submits()[0].body.summary_fields,['date','parameters/field149']);
  assert.deepEqual(submits()[0].body.generation,generation);
  await h.act(()=>h.root.findByProps({'aria-label':'Find a split field'}).props.onChange({target:{value:'Field 149'}}));
  await h.act(()=>pending[0].resolve(ready('A',2)));assert.match(h.text(),/2 values/);
  await h.render(h.TreeBuilder,scope('cell-B'));assert.equal(submits().length,2);
  assert.equal(submits()[0].options.signal,undefined,'submits are never aborted');assert.doesNotMatch(h.text(),/2 values/);
  assert.deepEqual(submits()[1].body.filters,{cell_uuid:'cell-B'});
  await h.render(h.TreeBuilder,scope('cell-C'));assert.equal(submits().length,3);
  assert.equal(submits()[1].options.signal,undefined);
  await h.act(()=>pending[2].resolve(ready('C',3)));assert.match(h.text(),/3 values/);
  await h.act(()=>pending[1].resolve(ready('late-B',9)));assert.match(h.text(),/3 values/);assert.doesNotMatch(h.text(),/9 values/);
  await h.act(closeSplit);
  await h.act(()=>h.button('Add a split').props.onClick());assert.equal(submits().length,4);
  await h.act(()=>toggleCombined(true));await h.act(closeSplit);
  await h.act(()=>pending[3].resolve({status:'pending',request_id:'closed-chooser',generation}));await h.settle();
  assert.equal(h.requests.some(item=>item.path==='/explore/summaries/closed-chooser/cancel'),false,'an open combined chooser retains the active request');
  await h.act(()=>toggleCombined(false));await h.settle();
  assert.ok(h.requests.some(item=>item.path==='/explore/summaries/closed-chooser/cancel'));
  await h.render(h.TreeBuilder,scope('cell-D'));
  await h.act(()=>h.root.findByProps({'aria-label':'Remove Recording date grouping'}).props.onClick());
  assert.deepEqual(changes,[[]]);assert.equal(submits().length,4,'closed scope and axis changes do not restart summaries');
  await h.act(()=>toggleCombined(true));assert.equal(submits().length,5);
  assert.deepEqual(submits()[4].body.summary_fields,['parameters/field149']);assert.deepEqual(submits()[4].body.filters,{cell_uuid:'cell-D'});
  await h.act(()=>toggleCombined(false));assert.equal(submits()[4].options.signal,undefined);
  await h.act(()=>pending[4].resolve({status:'pending',request_id:'closed-combined',generation}));await h.settle();
  assert.ok(h.requests.some(item=>item.path==='/explore/summaries/closed-combined/cancel'));
 }finally{await h.close();}
});

test('editing a predicate sends no request of any kind and edits stay unblocked',async()=>{
 const h=await harness();
 try{
  const draft={kind:'group',id:'g',mode:'all',negated:false,children:[{kind:'condition',id:'c',field:'parameters/field150',operator:'eq',valueType:'number',valueText:'1',negated:false}]};
  await h.render(h.PredicateDialog,{draft,catalog:{data:registry,supportsSummaries:true,reload(){}},projectId:'P1',protocolId:'A',onClose(){},onSearch(){}});await h.settle();
  const value=()=>h.root.findByProps({'aria-label':'Condition value'});
  const before=h.requests.length;
  for(const text of ['2','23','-','4'])await h.act(()=>value().props.onChange({target:{value:text}}));
  await h.settle(350);
  assert.deepEqual(h.requests.slice(before).map(item=>item.path),[],'editing a predicate sends no request of any kind');
  assert.equal(h.button('Preview matches'),undefined,'no preview while building a query');
  assert.equal(h.root.findByType('fieldset').props.disabled,false);assert.doesNotMatch(h.text(),/Metadata summaries/);
 }finally{await h.close();}
});

test('running a query sends no catalog statistics in previews and exactly one summary job after results',async()=>{
 const h=await harness({explorerShell:true});
 try{
  const predicate={all:[]},preview={catalog_summary:false,matched_count:17,tree_revision:'T',catalog:{fields:definitions.map(({id,label,category,path})=>({id,label,category,path}))},tree:{count:17,levels:[],split_order:['date']}};
  const applied={revision_uuid:'R',recipe:{predicate,splits:'date'},preview,previewGeneration:0,previewRevision:0};
  const props={projectId:'P1',initialProtocolId:'A',session:{applied,step:'tree',resultsFromDraft:false,splits:'date',filterSplits:'date'}};
  const summaryRegistry={...registry,summary_available:true};
  h.respond=(path)=>{
   if(path==='/explore/field-registry')return summaryRegistry;
   if(path==='/explore/preview')return preview;
   if(path.startsWith('/search-presets'))return {presets:[]};
   if(path.startsWith('/explore/revisions'))return {revisions:[]};
   if(path==='/explore/summaries')return {status:'ready',request_id:'result-job',generation,result:{matched_count:17,summaries:{date:{values:[{value:'2026-01-01',type:'string',count:17}],missing_count:0,present_count:17,values_truncated:false}}}};
   if(path.endsWith('/cancel'))return {status:'cancelled',generation};
   return {status:'cancelled',generation};
  };
  await h.render(h.MetadataExplorer,props);await h.settle();await h.settle(50);
  const builder=()=>h.root.findByType('explorer-viewer').props.builder;
  const jobs=()=>h.requests.filter(item=>item.path==='/explore/summaries');
  assert.ok(h.requests.filter(item=>item.path==='/explore/preview').every(item=>!Object.hasOwn(item.body,'catalog_summary')),'previews never ask for statistics');
  assert.equal(jobs().length,1,'one summary job for the shown result set');
  assert.deepEqual(jobs()[0].body.predicate,predicate);
  assert.deepEqual(jobs()[0].body.summary_fields,definitions.map(field=>field.id));
  assert.equal(builder().summaryEnabled,false,'the builder renders the result job instead of starting its own');
  assert.equal(builder().catalogData.fields.find(field=>field.id==='date').distinct_count,1);
  let start=h.requests.length;await h.act(()=>builder().onChange(['date','parameters/field150']));await h.settle();await h.settle(50);
  assert.ok(h.requests.slice(start).filter(item=>item.path==='/explore/preview').every(item=>!Object.hasOwn(item.body,'catalog_summary')));
  assert.equal(jobs().length,1,'a layout change of the same query reuses the result statistics');
 }finally{await h.close();}
});

test('a changed query cancels the running result summary and summarizes the new results once',async()=>{
 const h=await harness({explorerShell:true});
 try{
  const predicate={all:[]},preview={catalog_summary:false,matched_count:17,tree_revision:'T',catalog:{fields:definitions.map(({id,label,category,path})=>({id,label,category,path}))},tree:{count:17,levels:[],split_order:['date']}};
  const applied={revision_uuid:'R',recipe:{predicate,splits:'date'},preview,previewGeneration:0,previewRevision:0};
  const props={projectId:'P1',initialProtocolId:'A',session:{applied,step:'tree',resultsFromDraft:false,splits:'date',filterSplits:'date'}};
  let job=0;
  h.respond=(path)=>{
   if(path==='/explore/field-registry')return {...registry,summary_available:true};
   if(path==='/explore/preview')return preview;
   if(path.startsWith('/search-presets'))return {presets:[]};
   if(path.startsWith('/explore/revisions'))return {revisions:[]};
   if(path==='/explore/summaries')return {status:'pending',request_id:`job-${++job}`,generation};
   if(path.endsWith('/cancel'))return {status:'cancelled',generation};
   return {status:'pending',request_id:path.split('/').at(-1),generation};
  };
  await h.render(h.MetadataExplorer,props);await h.settle();await h.settle(50);
  const jobs=()=>h.requests.filter(item=>item.path==='/explore/summaries');
  assert.equal(jobs().length,1);
  await h.act(()=>h.root.findByType('explorer-viewer').props.onViewFilters({tag:'scoped'}));await h.settle();await h.settle(50);
  assert.ok(h.requests.some(item=>item.path==='/explore/summaries/job-1/cancel'),'the old query job is cancelled');
  assert.equal(jobs().length,2,'one job for the new result set');
  assert.notDeepEqual(jobs()[1].body.predicate,predicate);
 }finally{await h.close();}
});
test('field registry ignores fallback-path churn on current services and keeps completed fields while refreshing',async()=>{
 const h=await harness(),held=[];
 try{
  h.respond=path=>{if(path==='/explore/field-registry')return registry;throw Error(`Unexpected ${path}`);};
  const reads=()=>h.requests.filter(item=>item.path==='/explore/field-registry').length;
  await h.render(h.Probe,{kind:'registry',revision:1,fallbackPath:'/protocols/A/tree-fields?splits=date'});await h.settle();
  assert.equal(reads(),1);assert.equal(h.probe.fields.supportsSummaries,true);
  await h.render(h.Probe,{kind:'registry',revision:1,fallbackPath:'/protocols/A/tree-fields?splits=date,cell'});await h.settle();
  assert.equal(reads(),1,'split changes do not refetch the registry route');
  h.respond=()=>{const work=deferred();held.push(work);return work.promise;};
  await h.render(h.Probe,{kind:'registry',revision:2,fallbackPath:'/protocols/A/tree-fields?splits=date,cell'});await h.settle();
  assert.equal(reads(),2);assert.equal(h.probe.fields.loading,true);assert.equal(h.probe.fields.data.fields.length,152,'completed fields stay visible while refreshing');
  await h.act(()=>held.at(-1).resolve({...registry,fields:definitions.slice(0,3)}));await h.settle();
  assert.equal(h.probe.fields.loading,false);assert.equal(h.probe.fields.data.fields.length,3);
 }finally{await h.close();}
});
test('legacy field catalogs still follow the fallback path',async()=>{
 const h=await harness();
 try{
  h.respond=path=>path==='/explore/field-registry'?{httpStatus:404,data:{error:'Not found'}}:{fields:definitions.slice(0,path.includes('cell')?2:1)};
  await h.render(h.Probe,{kind:'registry',revision:1,fallbackPath:'/protocols/A/tree-fields?splits=date'});await h.settle();
  assert.equal(h.probe.fields.supportsSummaries,false);assert.equal(h.probe.fields.data.fields.length,1);
  const start=h.requests.length;
  await h.render(h.Probe,{kind:'registry',revision:1,fallbackPath:'/protocols/A/tree-fields?splits=date'});await h.settle();
  assert.equal(h.requests.length,start,'a completed legacy catalog is not refetched');
  await h.render(h.Probe,{kind:'registry',revision:1,fallbackPath:'/protocols/A/tree-fields?splits=date,cell'});await h.settle();
  assert.equal(h.probe.fields.data.fields.length,2);assert.ok(h.requests.slice(start).some(item=>item.path==='/protocols/A/tree-fields?splits=date,cell'));
 }finally{await h.close();}
});

test('building then running a query: editing sends nothing, running sends the run and exactly one summary job',async()=>{
 const h=await harness({explorerShell:true});
 try{
  const result={matched_count:4,catalog_summary:false,last_run:{cell_count:1,epoch_count:4,ran_at:'2026-10-19T00:00:00Z'},catalog:{fields:definitions.map(({id,label,category,path})=>({id,label,category,path}))},tree:{count:4,levels:[],split_order:['date','cell']}};
  h.respond=(path)=>{
   if(path==='/explore/field-registry')return {...registry,summary_available:true};
   if(path==='/explore/run')return result;
   if(path.startsWith('/search-presets'))return {presets:[]};
   if(path.startsWith('/explore/revisions'))return {revisions:[]};
   if(path==='/explore/summaries')return {status:'ready',request_id:'after-run',generation,result:{matched_count:4,summaries:{}}};
   throw Error(`Unexpected ${path}`);
  };
  await h.render(h.MetadataExplorer,{projectId:'P1',initialProtocolId:'A',initialPredicate:{all:[{field:'parameters/field1',operator:'gt',value:1}]}});await h.settle();await h.settle(50);
  const editing=h.requests.length;
  const logic=()=>h.root.findByProps({'aria-label':'Root group logic'});
  for(const next of ['any','all','any','all'])await h.act(()=>logic().props.onChange({target:{value:next}}));
  const value=()=>h.root.findByProps({'aria-label':'Condition value'});
  for(const text of ['2','25','250'])await h.act(()=>value().props.onChange({target:{value:text}}));
  await h.settle(350);
  assert.deepEqual(h.requests.slice(editing).map(item=>item.path),[],'editing a predicate sends no request of any kind');
  const running=h.requests.length;
  await h.act(()=>h.button('View matching epochs').props.onClick());await h.settle();await h.settle(50);
  const after=h.requests.slice(running).map(item=>item.path);
  assert.deepEqual(after.filter(path=>path.startsWith('/explore/')),['/explore/run','/explore/summaries'],'the run, then exactly one summary job');
  assert.equal(Object.hasOwn(h.requests.slice(running).find(item=>item.path==='/explore/run').body,'catalog_summary'),false,'the deprecated catalog_summary flag is not sent');
 }finally{await h.close();}
});

test('the predicate editor keeps tag-name autocomplete: the one request allowed while editing',async()=>{
 const h=await harness();
 try{
  const tagField={id:'annotations/epoch/tags',label:'Epoch tags',category:'Annotations',path:'annotations.epoch.tags',types:['string'],operators:['contains']};
  const draft={kind:'group',id:'g',mode:'all',negated:false,children:[{kind:'condition',id:'c',field:'annotations/epoch/tags',operator:'contains',valueType:'string',valueText:'',negated:false}]};
  h.respond=path=>path.startsWith('/annotation-tags')?{tags:[{tag:'bright',count:3},{tag:'branch-stim',count:1}],has_more:false}:(()=>{throw Error(`Unexpected ${path}`);})();
  await h.render(h.PredicateDialog,{draft,catalog:{data:{...registry,fields:[...definitions,tagField]},supportsSummaries:true,reload(){}},projectId:'P1',protocolId:'A',onClose(){},onSearch(){}});await h.settle();
  const start=h.requests.length,value=()=>h.root.findByProps({'aria-label':'Condition value'});
  await h.act(()=>value().props.onFocus());
  await h.act(()=>value().props.onChange({target:{value:'br'}}));await h.settle(250);
  const reads=h.requests.slice(start).map(item=>item.path);
  assert.ok(reads.length>0&&reads.every(path=>path.startsWith('/annotation-tags?q=')),`only tag-name autocomplete reads: ${reads}`);
  assert.ok(reads.includes('/annotation-tags?q=br&limit=100'));
  assert.match(h.text(),/bright/);assert.match(h.text(),/branch-stim/);
 }finally{await h.close();}
});
