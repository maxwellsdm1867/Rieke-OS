import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {summaryPreferenceKey} from './requestedSummaries.js';
const generation={metadata:'M',source:'S',annotation:'A',publication:'P'};
const definitions=[{id:'date',label:'Date',category:'Recording',types:['string'],operators:['eq'],path:'date'},...Array.from({length:151},(_,i)=>({id:`parameters/field${i}`,label:`Field ${i}`,category:'Parameters',path:`parameters.field${i}`,types:['number'],operators:['eq','gt']}))];
const registry={fields:definitions,tree_fields:definitions,generation,summary_available:false};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
async function harness(){
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
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom',logLevel:'silent',esbuild:{jsx:'automatic'},plugins:[{name:'summary-test-portals',enforce:'pre',resolveId(id,importer){if(id==='../useProjectPreference.js'&&importer?.endsWith('/components/PredicateDialog.jsx'))return '\0summary-project-preference';if(id==='react-dom')return '\0summary-portals';},load(id){if(id==='\0summary-project-preference')return 'export const useProjectPreference=()=>({value:{}});';if(id==='\0summary-portals')return 'export const createPortal=children=>children;';}}]});
 const {default:TreeBuilder}=await server.ssrLoadModule('/src/components/TreeBuilder.jsx');
 const {useRequestedSummaries}=await server.ssrLoadModule('/src/useRequestedSummaries.js');
 const {useFieldRegistry}=await server.ssrLoadModule('/src/useFieldRegistry.js');
 const {useProtocolSummaryPreferences}=await server.ssrLoadModule('/src/useProtocolSummaryPreferences.js');
 const {default:PredicateDialog}=await server.ssrLoadModule('/src/components/PredicateDialog.jsx');
 // Compile the explorer/App source too; the mounted tree exercises the shared builder.
 await server.ssrLoadModule('/src/components/MetadataExplorer.jsx');
 await server.ssrLoadModule('/src/App.jsx');
 let root,probe;
 function Probe({kind,request,revision,project,protocol,view,enabled=true}){
  const summary=useRequestedSummaries(request||{predicate:{all:[]},summary_fields:[]},{enabled:kind==='summary'&&enabled});
  const fields=useFieldRegistry(revision,'/explore/predicate-fields');
  const preferences=useProtocolSummaryPreferences(project,protocol,view);
  probe={summary,fields,preferences};return React.createElement('probe',{status:summary.status});
 }
 const h={requests,memory,TreeBuilder,PredicateDialog,Probe,set respond(value){respond=value;},get probe(){return probe;},get root(){return root.root;},async render(Component,props){await act(async()=>{const element=React.createElement(Component,props);if(root)root.update(element);else root=TestRenderer.create(element,{createNodeMock:()=>({showModal(){},close(){},focus(){},getBoundingClientRect:()=>({left:50,top:100,bottom:120,width:300}),contains:()=>false})});});},async act(callback){await act(callback);},async settle(ms=0){await act(async()=>{if(ms)await new Promise(resolve=>setTimeout(resolve,ms));for(let i=0;i<12;i++)await Promise.resolve();});},async close(){await act(()=>root?.unmount());await server.close();Object.assign(globalThis,old);},button(label){return root.root.findAllByType('button').find(node=>node.children.some(child=>typeof child==='string'&&child.includes(label)));},text(){return JSON.stringify(root.toJSON());}};
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
test('mounted protocol/view preferences retain missing pinned fields and isolate project switches',async()=>{
 const h=await harness();
 try{
  await h.render(h.Probe,{kind:'preferences',project:'P1',protocol:'A',view:'tree'});await h.act(()=>h.probe.preferences.update(['parameters/field150','history1']));
  assert.deepEqual(JSON.parse(h.memory.get(summaryPreferenceKey('P1','A','tree'))),{version:1,fields:['parameters/field150','history1']});
  for(const context of [{project:'P2',protocol:'A',view:'tree'},{project:'P1',protocol:'B',view:'tree'},{project:'P1',protocol:'A',view:'filter'}]){await h.render(h.Probe,{kind:'preferences',...context});assert.deepEqual(h.probe.preferences.value.fields,[]);}
  await h.render(h.Probe,{kind:'preferences',project:'P1',protocol:'A',view:'tree'});assert.deepEqual(h.probe.preferences.value.fields,['parameters/field150','history1']);
 }finally{await h.close();}
});
test('mounted tree remains editable while pending, keeps saved missing axes, and exposes full registry/full-summary operations',async()=>{
 const h=await harness(),changes=[];
 try{
  const axes=['date','parameters/field150','history1'];const props={projectId:'P1',protocolId:'A',value:axes,onChange:value=>changes.push(value),preview:{count:7},loading:false};
  await h.render(h.TreeBuilder,props);await h.settle();
  const submit=h.requests.find(item=>item.path==='/explore/summaries');assert.deepEqual(submit.body.summary_fields,['date','parameters/field150']);assert.equal(submit.body.protocol_uuid,'A');assert.equal(h.requests.some(item=>item.path.includes('/tree-fields')),false);
  assert.match(h.text(),/pending/);assert.match(h.text(),/history1/);assert.equal(changes.length,0);assert.deepEqual(axes,['date','parameters/field150','history1']);
  assert.equal(h.button('Add a split').props.disabled,false);
  const chooser=h.root.findByProps({'aria-label':'Add preferred summary'});assert.equal(chooser.findAllByType('option').length,153);
  assert.ok(chooser.findAllByType('option').some(option=>option.props.value==='parameters/field150'));
  await h.act(()=>h.button('Summarize all metadata fields').props.onClick());const last=h.requests.filter(item=>item.path==='/explore/summaries').at(-1);assert.equal(last.body.summary_fields.length,152);
  await h.act(()=>h.button('Load full catalog and suggestions').props.onClick());assert.ok(h.requests.some(item=>item.path==='/protocols/A/tree-fields'));
 }finally{await h.close();}
});

test('mounted predicate editor requests active typed fields without blocking edits or substituting invalid drafts',async()=>{
 const h=await harness();
 try{
  const draft={kind:'group',id:'g',mode:'all',negated:false,children:[{kind:'condition',id:'c',field:'parameters/field150',operator:'eq',valueType:'number',valueText:'1',negated:false}]};
  h.memory.set(summaryPreferenceKey('P1','A','filter'),JSON.stringify({version:1,fields:['parameters/field149','missing-pref']}));
  await h.render(h.PredicateDialog,{draft,catalog:{data:registry,supportsSummaries:true,reload(){}},projectId:'P1',protocolId:'A',onClose(){},onSearch(){}});await h.settle();
  assert.equal(h.root.findByType('fieldset').props.disabled,false);assert.match(h.text(),/pending/);
  let submits=h.requests.filter(item=>item.path==='/explore/summaries');assert.deepEqual(submits.at(-1).body.summary_fields,['parameters/field150','parameters/field149']);assert.equal(submits.at(-1).body.protocol_uuid,undefined);
  const value=()=>h.root.findByProps({'aria-label':'Condition value'});
  await h.act(()=>value().props.onChange({target:{value:'2'}}));submits=h.requests.filter(item=>item.path==='/explore/summaries');assert.equal(submits.at(-1).body.predicate.all[0].value,2);assert.equal(h.root.findByType('fieldset').props.disabled,false);
  const count=submits.length;await h.act(()=>value().props.onChange({target:{value:'-'}}));assert.equal(h.requests.filter(item=>item.path==='/explore/summaries').length,count);assert.match(h.text(),/complete numeric value/);assert.equal(h.root.findByType('fieldset').props.disabled,false);
 }finally{await h.close();}
});
