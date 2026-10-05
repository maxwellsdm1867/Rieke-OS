import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useState} from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {incomingTreeSelectionScope,incomingBranchOn,incomingBranchCommand} from './incoming-workbench/incomingSelection.js';
const rev='a'.repeat(64),scopeProps={projectId:'project',protocolId:'protocol-A',readContext:{root:'/candidate',candidate_scope_revision:'frozen'},filters:{},splits:'date,cell',revision:0};
const parent={path:['p'],count:3},child={path:['p','x'],count:2},other={path:['p','y'],count:1};
const rows={x:[{epoch_uuid:'a',cell_uuid:'x'},{epoch_uuid:'b',cell_uuid:'x'}],y:[{epoch_uuid:'c',cell_uuid:'y'}]};
const rootPage={revision:rev,candidate_scope_revision:'frozen',path:[],offset:0,limit:60,kind:'branches',total:1,selection:{count:3},has_more:false,branches:[parent]};
function response(body){
 const path=body.path||[];
 if(!path.length)return rootPage;
 if(path.length===1)return {...rootPage,path,selection:{count:3},total:2,branches:[child,other]};
 const epochs=rows[path[1]];
 return {...rootPage,path,kind:'epochs',total:epochs.length,selection:{count:epochs.length},epochs,branches:[]};
}
function setup(h,{useIncomingTreeSelection,IncomingEpochSelect}){
 let observed;
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?response(JSON.parse(options.body)):fallback();
 function View({selected,intent,setSelected,setIntent,revision}){
  const props={...scopeProps,revision,selectedEpochs:selected,setSelectedEpochs:setSelected,treeSelectionIntent:intent,onTreeSelectionIntentChange:setIntent};
  const state=useIncomingTreeSelection(props,rootPage);
  return createElement('div',null,...[['parent',parent],['child',child],['other',other],['oversize',{path:['p'],count:1001}]].map(([id,item])=>createElement('button',{key:id,id,disabled:state.working,'data-on':state.on(item,rootPage),onClick:()=>state.select(item,rootPage) },id)),createElement(IncomingEpochSelect,{epoch:{epoch_uuid:'a'},selected,onSelect:setSelected}),state.feedback);
 }
 function Owner({revision=0}){
  const [selected,setSelected]=useState([]),[intent,setIntent]=useState(null),[view,setView]=useState(false);
  observed={selected,intent,setSelected,setIntent,setView};
  return createElement('div',null,createElement(View,{key:String(view),selected,intent,setSelected,setIntent,revision}),
   createElement('button',{id:'global-off',onClick:()=>{setSelected([]);setIntent({scope:incomingTreeSelectionScope({...scopeProps,revision}),revision:null,markers:[{path:[],on:false}]});}},'clear'),
   createElement('button',{id:'global-on',onClick:()=>{setSelected(['a','b','c']);setIntent({scope:incomingTreeSelectionScope({...scopeProps,revision}),revision:null,markers:[{path:[],on:true}]});}},'all'));
 }
 return {Owner,observed:()=>observed};
}
const event=()=>({preventDefault(){},stopPropagation(){}});
test('binary branch commands preserve parent on with child off and replace descendant overrides',()=>{
 const scope='scope';let intent=incomingBranchCommand(null,scope,rev,['p'],true);
 intent=incomingBranchCommand(intent,scope,rev,['p','x'],false);
 assert.equal(incomingBranchOn(intent,scope,rev,['p']),true);
 assert.equal(incomingBranchOn(intent,scope,rev,['p','x','leaf']),false);
 assert.equal(incomingBranchOn(intent,scope,rev,['p','y']),true);
 intent=incomingBranchCommand(intent,scope,rev,['p'],false);
 assert.deepEqual(intent.markers,[{path:['p'],on:false}]);
 intent=incomingBranchCommand(intent,scope,rev,['p','x'],true);
 assert.equal(incomingBranchOn(intent,scope,rev,['p']),false);
 assert.equal(incomingBranchOn(intent,scope,rev,['p','x']),true);
 assert.equal(incomingBranchOn(intent,'different',rev,['p','x']),false);
 assert.equal(incomingBranchOn(intent,scope,'changed',['p','x']),false);
});
test('fresh complete branch flips, individual overrides, global commands and view remount preserve exact selection',async()=>{
 const h=await createWorkflowHarness();
 try{
  const state=setup(h,await h.module('incoming-workbench/ui/IncomingTreeSelection.jsx'));await h.mount(state.Owner);
  const button=id=>h.root.findByProps({id}),click=async id=>{await h.act(()=>button(id).props.onClick(event()));};
  await click('parent');assert.deepEqual(state.observed().selected,['a','b','c']);assert.equal(button('parent').props['data-on'],true);assert.equal(button('child').props['data-on'],true);
  await click('child');assert.deepEqual(state.observed().selected,['c']);assert.equal(button('parent').props['data-on'],true);assert.equal(button('child').props['data-on'],false);
  await h.act(()=>h.root.findByProps({role:'switch'}).props.onClick(event()));assert.deepEqual(state.observed().selected,['c','a']);assert.equal(button('parent').props['data-on'],true);assert.equal(button('child').props['data-on'],false);
  await h.act(()=>state.observed().setView(true));assert.equal(button('parent').props['data-on'],true);assert.equal(button('child').props['data-on'],false);
  await click('parent');assert.deepEqual(state.observed().selected,[]);assert.equal(button('parent').props['data-on'],false);
  await click('parent');assert.deepEqual(state.observed().selected,['a','b','c']);assert.equal(button('child').props['data-on'],true);
  await click('global-off');assert.deepEqual(state.observed().selected,[]);assert.equal(button('parent').props['data-on'],false);
  await click('global-on');assert.equal(button('parent').props['data-on'],true);assert.equal(button('child').props['data-on'],true);
  await h.render(state.Owner,{revision:1});assert.equal(button('parent').props['data-on'],false,'changed read scope cannot reuse branch command');
 }finally{await h.close();}
});
test('late branch read cannot overwrite individual or global commands; failed complete read is atomic',async()=>{
 const h=await createWorkflowHarness();let release;
 try{
  const state=setup(h,await h.module('incoming-workbench/ui/IncomingTreeSelection.jsx'));await h.mount(state.Owner);
  const button=id=>h.root.findByProps({id});
  const delayed=()=>{h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?new Promise(resolve=>{release=()=>resolve(response(JSON.parse(options.body)));}):fallback();};
  delayed();let pending;await h.act(()=>{pending=button('child').props.onClick(event());});
  await h.act(()=>state.observed().setSelected(['c']));
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?response(JSON.parse(options.body)):fallback();
  await h.act(async()=>{release();await pending;});assert.deepEqual(state.observed().selected,['c']);assert.equal(state.observed().intent,null);
  await h.act(()=>state.observed().setSelected([]));delayed();await h.act(()=>{pending=button('child').props.onClick(event());});
  await h.act(()=>button('global-off').props.onClick());
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?response(JSON.parse(options.body)):fallback();
  await h.act(async()=>{release();await pending;});assert.deepEqual(state.observed().selected,[]);assert.equal(button('child').props['data-on'],false,'same-empty UUID set global off still retires pending on');
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?{...response(JSON.parse(options.body)),revision:'b'.repeat(64)}:fallback();
  await h.act(()=>button('child').props.onClick(event()));assert.deepEqual(state.observed().selected,[]);assert.equal(button('child').props['data-on'],false);
 }finally{await h.close();}
});

test('oversized or overflowing branch commands leave both UUIDs and switch intent unchanged',async()=>{
 const h=await createWorkflowHarness();
 try{
  const state=setup(h,await h.module('incoming-workbench/ui/IncomingTreeSelection.jsx'));await h.mount(state.Owner);
  const button=id=>h.root.findByProps({id});
  const before=h.fixture.requests.length;
  await h.act(()=>button('oversize').props.onClick(event()));
  assert.equal(h.fixture.requests.length,before,'oversized command refuses before fetching');
  assert.deepEqual(state.observed().selected,[]);assert.equal(state.observed().intent,null);
  const selected=Array.from({length:999},(_,index)=>`external-${index}`);
  await h.act(()=>state.observed().setSelected(selected));
  await h.act(()=>button('child').props.onClick(event()));
  assert.deepEqual(state.observed().selected,selected);assert.equal(state.observed().intent,null);
  assert.equal(button('child').props['data-on'],false);
 }finally{await h.close();}
});

test('legacy additive cell selection keeps its Select action unless binary state is supplied',async()=>{
 const h=await createWorkflowHarness();let selected=0;
 try{
  const {TreeGroupTagButton}=await h.module('annotations/ui/TreeGroupTags.jsx');
  const props={count:3,onSelect:()=>selected++,onClick:()=>{}};
  await h.mount(TreeGroupTagButton,props);
  assert.equal(h.root.findAllByProps({role:'switch'}).length,0);
  const additive=h.root.findByProps({className:'incoming-explicit-select'});
  assert.equal(additive.props['aria-checked'],undefined);
  assert.equal(additive.findByType('span').children.join(''),'Select');
  await h.act(()=>additive.props.onClick());assert.equal(selected,1);
  await h.render(TreeGroupTagButton,{...props,selectionOn:false});
  assert.equal(h.root.findAllByProps({className:'incoming-explicit-select'}).length,0);
  assert.equal(h.root.findByProps({role:'switch'}).props['aria-checked'],false);
 }finally{await h.close();}
});
