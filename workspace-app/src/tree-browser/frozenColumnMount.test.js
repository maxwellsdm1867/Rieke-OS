import test from 'node:test';
import assert from 'node:assert/strict';
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {createServer} from '../test-support/isolatedVite.js';

const key='a'.repeat(64),oldRevision='b'.repeat(64),freshRevision='c'.repeat(64);
const saved={path:[key],offset:0,revision:oldRevision,split_order:['date'],scrollTop:20,scrollLeft:30,columnPositions:[{offset:0,scrollTop:10},{offset:0,scrollTop:20}],columnPresentation:{scope:'foreign-prior-selected-view',selected:'epoch-2',columns:[],scrollLeft:30}};
const readContext={root:'/protocols/p/workbench/candidates/c',cohort_key:'cohort',actor:'author',candidate_scope_revision:'fresh-scope',expected_binding_version:2,selection_token:'fresh-selected-token',selection_view_key:'selected-two-epochs',tree_column_pages:true};

async function fixture({frozen=true,hold=false,ignoreRevision=false}={}){
 const dom=new JSDOM('<main></main>',{url:'http://fixture/'});
 const globals=['window','document','localStorage','fetch','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT'];
 const previous=Object.fromEntries(globals.map(k=>[k,globalThis[k]]));
 Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true,window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,requestAnimationFrame:f=>setTimeout(f,0),cancelAnimationFrame:clearTimeout});
 const state={requests:[],held:[],selected:[],metadata:[]};
 const revision=frozen?freshRevision:oldRevision;
 const fence={revision,...(frozen?{candidate_scope_revision:'fresh-scope',query_revision:'fresh-scope',expected_binding_version:2,generation:{metadata:'fresh-metadata',source:'source'}}:{})};
 const branch={key,path:[key],label:'Selected recording date',value:'date',count:2};
 const common={...fence,offset:0,limit:60,total:2,total_epochs:2,split_order:['date'],levels:[{field:'date',label:'Date'}],has_more:false};
 const rootPage={...common,kind:'branches',path:[],depth:0,branches:[branch],epochs:[],ancestors:[]};
 const leaf={...common,kind:'epochs',path:[key],depth:1,branches:[],epochs:[{epoch_uuid:'epoch-1',epoch_number:1},{epoch_uuid:'epoch-2',epoch_number:2}],ancestors:[{...branch,parent_offset:0}]};
 globalThis.fetch=async(url,options)=>{
  assert.equal(url,frozen?'/api'+readContext.root+'/tree/page':'/api/tree-pages');
  const body=JSON.parse(options.body);state.requests.push({body,signal:options.signal});
  if(frozen){assert.equal(body.selection_token,readContext.selection_token);assert.equal(body.candidate_scope_revision,readContext.candidate_scope_revision);}
  if(body.revision&&body.revision!==revision&&!ignoreRevision)return new Response(JSON.stringify({error:'Tree metadata or membership changed; reload the root before continuing'}),{status:409});
  if(frozen&&(body.path.length||body.offset)&&!body.anchor_uuid&&!body.revision)return new Response(JSON.stringify({error:'A tree revision is required for continuation pages'}),{status:400});
  const response=structuredClone(body.anchor_uuid||body.path.length?leaf:rootPage);
  if(body.anchor_uuid)response.anchor={epoch_uuid:body.anchor_uuid,path:[key],index:1,offset:0};
  if(body.include_ancestors)response.ancestor_pages=response.path.length?[structuredClone(rootPage)]:[];
  if(hold)await new Promise(resolve=>state.held.push(resolve));
  return new Response(JSON.stringify(response),{status:200});
 };
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'});
 const {default:ColumnTree}=await server.ssrLoadModule('/src/tree-browser/ui/ColumnTree.jsx');
 const root=createRoot(document.querySelector('main'));
 const render=(extra={})=>act(async()=>root.render(React.createElement(ColumnTree,{protocolId:'p',projectId:'project',splits:'date',design:true,browseOnly:true,initialNavigation:structuredClone(saved),...(frozen?{readContext}:{}),onSelectEpoch:id=>state.selected.push(id),onMetadata:value=>state.metadata.push(value),...extra})));
 const release=()=>act(async()=>state.held.shift()());
 async function close(){await act(()=>root.unmount());await server.close();dom.window.close();for(const[k,v]of Object.entries(previous)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
 return {state,render,release,close};
}

test('frozen initial selected anchor drops foreign saved revision and stays blocked until fresh batch completes',async()=>{
 const h=await fixture({hold:true});
 try{
  await h.render({selected:'epoch-2'});
  assert.equal(h.state.requests.length,1);const body=h.state.requests[0].body;
  assert.equal(body.revision,undefined,'saved revision is presentation history, not current authority');
  assert.equal(body.anchor_uuid,'epoch-2');assert.deepEqual(body.path,[]);assert.equal(body.include_ancestors,true);
  assert.equal(h.state.held.length,1);assert.equal(document.querySelector('.tp-path button').disabled,true);
  document.querySelector('.tp-path button').click();assert.equal(h.state.requests.length,1);assert.deepEqual(h.state.selected,[]);assert.equal(h.state.metadata.length,0);
  await h.release();
  assert.equal(!!document.querySelector('[role="alert"]'),false);assert.equal(h.state.requests.length,1,'anchor returns fresh target and ancestors in one bounded request');
  assert.deepEqual([...document.querySelectorAll('[data-epoch-uuid]')].map(n=>n.dataset.epochUuid),['epoch-1','epoch-2']);
  assert.deepEqual(h.state.metadata.at(-1).path,[key]);assert.equal(h.state.metadata.at(-1).revision,freshRevision);
  assert.equal(document.querySelector('.tp-path button').disabled,false);
  document.querySelector('[data-epoch-uuid="epoch-2"]').click();assert.deepEqual(h.state.selected,['epoch-2']);
 }finally{await h.close();}
});

test('frozen initial path-only restoration obtains a fresh root before pinning target revision',async()=>{
 const h=await fixture();
 try{
  await h.render();assert.equal(!!document.querySelector('[role="alert"]'),false);
  assert.equal(h.state.requests.length,2);const[first,second]=h.state.requests.map(r=>r.body);
  assert.deepEqual(first.path,[]);assert.equal(first.revision,undefined);assert.equal(first.anchor_uuid,undefined);
  assert.deepEqual(second.path,[key]);assert.equal(second.revision,freshRevision);assert.equal(second.anchor_uuid,undefined);
  assert.equal(h.state.metadata.at(-1).revision,freshRevision);
 }finally{await h.close();}
});

test('frozen selected anchor preserves explicit expectedRevision and refuses a mismatched reply',async()=>{
 const h=await fixture({ignoreRevision:true});
 try{
  await h.render({selected:'epoch-2',expectedRevision:oldRevision});
  assert.equal(h.state.requests.length,1);assert.equal(h.state.requests[0].body.revision,oldRevision);
  assert.match(document.querySelector('[role="alert"]').textContent,/Tree revision changed/);
  assert.equal(h.state.metadata.length,0);assert.equal(document.querySelectorAll('[data-epoch-uuid]').length,0);assert.equal(document.querySelector('.tp-path button').disabled,true);
 }finally{await h.close();}
});

test('live initial navigation retains its existing saved-revision request contract',async()=>{
 const h=await fixture({frozen:false});
 try{
  await h.render({selected:'epoch-2'});
  assert.equal(h.state.requests[0].body.revision,oldRevision);assert.equal(h.state.requests[0].body.anchor_uuid,'epoch-2');
  assert.equal(!!document.querySelector('[role="alert"]'),false);assert.equal(h.state.metadata.at(-1).revision,oldRevision);
 }finally{await h.close();}
});
