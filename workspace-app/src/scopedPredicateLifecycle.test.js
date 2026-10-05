import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from './test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {predicateToDraft} from './typed-query/ui/predicateState.js';
const catalog={data:{fields:[{id:'parameters/x',label:'X',types:['number'],operators:['eq','gt']}],generation:{metadata:'m',typed:'t',source:'s',publication:'p',annotation:'a'}},supportsSummaries:false,reload(){}};
const root='/protocols/p/workbench/candidates/r';
const deferred=()=>{let resolve;return {promise:new Promise(done=>resolve=done),resolve:value=>resolve(value)};};
async function harness(){
 const old={fetch:globalThis.fetch,localStorage:globalThis.localStorage,window:globalThis.window,document:globalThis.document};
 const requests=[],memory=new Map();let respond=()=>({});
 globalThis.localStorage={getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value)};
 globalThis.window={innerWidth:1200,innerHeight:800,addEventListener(){},removeEventListener(){}};
 globalThis.document={body:{nodeType:1},addEventListener(){},removeEventListener(){},getElementById:()=>null};
 globalThis.fetch=async(url,options)=>{const body=options.body?JSON.parse(options.body):null;requests.push({url,body});return new Response(JSON.stringify(await respond(url,body)),{status:200});};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom',logLevel:'silent',esbuild:{jsx:'automatic'},plugins:[{name:'scoped-preferences',enforce:'pre',resolveId(id,importer){if(id==='../../project-preferences/useProjectPreference.js'&&importer?.endsWith('PredicateDialog.jsx'))return '\0scoped-preferences';},load(id){if(id==='\0scoped-preferences')return 'export const useProjectPreference=()=>({value:{},update:async()=>{}});';}}]});
 const {default:Dialog}=await server.ssrLoadModule('/src/typed-query/ui/PredicateDialog.jsx');let renderer;
 const h={requests,Dialog,set respond(fn){respond=fn;},async render(props){await act(async()=>{const child=React.createElement(Dialog,{draft:predicateToDraft({all:[{field:'parameters/x',operator:'eq',value:1}]}),catalog,onSearch:async()=>{},onClose(){},...props});if(renderer)renderer.update(child);else renderer=TestRenderer.create(child,{createNodeMock:()=>({showModal(){},close(){},focus(){},getBoundingClientRect:()=>({left:0,top:0,bottom:0,width:300}),contains:()=>false})});});},button(text){return renderer.root.findAllByType('button').find(item=>item.children.some(child=>typeof child==='string'&&child.includes(text)));},text:()=>JSON.stringify(renderer.toJSON()),async act(fn){await act(fn);},async settle(){await act(async()=>{for(let i=0;i<12;i++)await Promise.resolve();});},async close(){await act(()=>renderer?.unmount());await server.close();Object.assign(globalThis,old);}};
 return h;
}
test('candidate previews discard late old token results even for the same AST',async()=>{
 const h=await harness(),late=deferred();
 try{
  h.respond=(url,body)=>url.includes('/summary')?late.promise:{};
  await h.render({readContext:{root,candidate_scope_revision:'scope-a',filters:{cell_type:'RGC'}}});
  await h.act(()=>{void h.button('Preview matches').props.onClick();});
  const requested=h.requests.find(item=>item.url.includes('/summary')).body;
  await h.render({readContext:{root,candidate_scope_revision:'scope-b',filters:{cell_type:'RGC'}}});
  late.resolve({...requested,counts:{epochs:777}});await h.settle();
  assert.doesNotMatch(h.text(),/777 matching epochs/);
  assert.equal(h.requests.some(item=>item.url.includes('/explore/run')||item.url.includes('/explore/summaries')),false);
  h.respond=(url,body)=>url.includes('/summary')?{...body,counts:{epochs:2}}:{};
  await h.act(()=>{void h.button('Preview matches').props.onClick();});await h.settle();
  assert.match(h.text(),/2 matching epochs/);
 }finally{await h.close();}
});
test('candidate preview rejects unacknowledged filters and displays unsupported saved AST',async()=>{
 const h=await harness();
 try{
  await h.render({readContext:{root,candidate_scope_revision:'scope-a',filters:{cell_type:'RGC'}}});
  h.respond=(url,body)=>url.includes('/summary')?{...body,filters:{},counts:{epochs:0}}:{};
  await h.act(()=>{void h.button('Preview matches').props.onClick();});await h.settle();
  assert.match(h.text(),/Candidate preview authority changed/);
  await h.render({key:'restored',draft:predicateToDraft({all:[{field:'curation/other/tags',operator:'contains',value:'QC'}]}),readContext:{root,candidate_scope_revision:'scope-c',filters:{}}});
  assert.match(h.text(),/curation\/other\/tags/);assert.match(h.text(),/not in the current metadata catalog/);
  await h.close();
 }catch(error){await h.close();throw error;}
});

import {createWorkflowHarness} from './test-support/workflowHarness.js';
test('candidate Inspector routes frozen rows/cells/detail and review callbacks without protocol curation',async()=>{
 const h=await createWorkflowHarness({total:10}),selections=[],decisions=[];
 const context={root:'/protocols/protocol-A/workbench/candidates/revision-A',candidate_scope_revision:'candidate-a'};
 try{
  h.fixture.respond=(url,options,fallback)=>{
   if(url.pathname.startsWith('/api'+context.root)){
    assert.equal(url.searchParams.get('candidate_scope_revision'),context.candidate_scope_revision);
    const suffix=url.pathname.slice(('/api'+context.root).length);
    url.pathname=suffix.startsWith('/epochs/epoch-')?'/api'+suffix:'/api/protocols/protocol-A'+suffix;
   }
   return fallback();
  };
  const Inspector=await h.component('Inspector');
  await h.mount(Inspector,{protocol:{definition:{protocol_uuid:'protocol-A',name:'Frozen candidate'},counts:{epochs:10},cells:[]},projectId:'project',filters:{},revision:0,readContext:context,initialEpochUuid:'epoch-0',onSelectionChange:ids=>selections.push(ids),onReviewDecision:async body=>decisions.push(body),onChange(){}});
  await h.waitFor(()=>!!h.viewer.epoch&&!h.viewer.treePane.listProps.disabled);
  await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-0','epoch-1']));
  assert.deepEqual(selections.at(-1),['epoch-0','epoch-1']);
  await h.act(()=>h.viewer.treePane.listProps.onToggleInclusion({epoch_uuid:'epoch-0'},false));
  assert.deepEqual(decisions[0].epoch_uuids,['epoch-0']);assert.deepEqual(decisions[0].changes,{included:false});
  assert.equal(h.viewer.tags.props.children,false);assert.equal(h.viewer.detailExtras.props.epoch.epoch_uuid,'epoch-0');
  assert.equal(h.viewer.builder.summaryEnabled,false);assert.deepEqual(h.viewer.builder.readContext,context);
  assert.ok(h.viewer.builder.onAnnotationsChanged);assert.ok(h.viewer.columnTree.onAnnotationsChanged);assert.ok(h.viewer.treePane.treeProps.onAnnotationsChanged);
  assert.ok(h.fixture.requests.some(item=>item.path.startsWith(context.root+'/epochs?')));
  assert.ok(h.fixture.requests.some(item=>item.path.startsWith(context.root+'/epochs/epoch-0?')));
  assert.equal(h.fixture.requests.some(item=>item.path.startsWith('/protocols/protocol-A/curation')||item.path.startsWith('/epochs/epoch-0?')),false);
 }finally{await h.close();}
});
