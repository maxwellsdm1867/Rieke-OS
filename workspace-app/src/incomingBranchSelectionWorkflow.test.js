import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useState,useCallback,useLayoutEffect,useRef} from 'react';
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
 function View({selected,intent,setSelected,setIntent,revision,actionsDisabled}){
  const props={...scopeProps,revision,actionsDisabled,selectedEpochs:selected,setSelectedEpochs:setSelected,treeSelectionIntent:intent,onTreeSelectionIntentChange:setIntent};
  const state=useIncomingTreeSelection(props,rootPage);
  return createElement('div',null,...[['parent',parent],['child',child],['other',other],['oversize',{path:['p'],count:1001}]].map(([id,item])=>createElement('button',{key:id,id,disabled:state.working,'data-on':state.on(item,rootPage),onClick:()=>state.select(item,rootPage) },id)),createElement(IncomingEpochSelect,{epoch:{epoch_uuid:'a'},selected,onSelect:setSelected}),state.feedback);
 }
 function Owner({revision=0,actionsDisabled=false}){
  const [selected,setSelected]=useState([]),[intent,setIntent]=useState(null),[view,setView]=useState(false);
  observed={selected,intent,setSelected,setIntent,setView};
  return createElement('div',null,createElement(View,{key:String(view),selected,intent,setSelected,setIntent,revision,actionsDisabled}),
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
  assert.equal(h.root.findByProps({role:'switch'}).findAllByType('span').at(-1).children.join(''),'Select');
  await h.render(TreeGroupTagButton,{...props,selectionOn:true});
  assert.equal(h.root.findByProps({role:'switch'}).findAllByType('span').at(-1).children.join(''),'Selected');
 }finally{await h.close();}
});

for(const replacement of [{revision:1},{actionsDisabled:true}])test(`interrupted branch selection reports retry after ${Object.keys(replacement)[0]} and ignores its late read`,async()=>{
 const h=await createWorkflowHarness();let release,pending;
 try{
  const state=setup(h,await h.module('incoming-workbench/ui/IncomingTreeSelection.jsx'));await h.mount(state.Owner);
  const button=id=>h.root.findByProps({id});
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?new Promise(resolve=>{release=()=>resolve(response(JSON.parse(options.body)));}):fallback();
  await h.act(()=>{pending=button('child').props.onClick(event());});
  await h.render(state.Owner,replacement);
  assert.deepEqual(state.observed().selected,[]);assert.equal(state.observed().intent,null);
  assert.match(h.root.findByProps({role:'alert'}).children.join(''),/The view refreshed before this selection finished\. Switch the branch again\./);
  assert.equal(h.root.findAllByProps({role:'status'}).length,0);
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/candidate/tree/page')?response(JSON.parse(options.body)):fallback();
  await h.render(state.Owner,{...replacement,actionsDisabled:false});
  await h.act(()=>button('child').props.onClick(event()));
  assert.deepEqual(state.observed().selected,['a','b']);assert.equal(button('child').props['data-on'],true);
  assert.equal(h.root.findAllByProps({role:'alert'}).length,0);
  await h.act(async()=>{release();await pending;});
  assert.deepEqual(state.observed().selected,['a','b']);assert.equal(button('child').props['data-on'],true);
  assert.equal(h.root.findAllByProps({role:'alert'}).length,0,'retired response cannot overwrite a later successful retry');
 }finally{await h.close();}
});

test('actual retained wrapper eviction preserves owner feedback and late branch work cannot publish',async()=>{
 const h=await createWorkflowHarness();let release,pending,selected=[],feedback='',notifications=0;
 try{
  const Host=await h.component('RetainedTreePresentation'),Paged=await h.component('PagedTree');
  const decorate=page=>({...page,depth:page.path.length,count:3,total_epochs:3,cells:2,duration_seconds:0,split_order:['date','cell'],levels:[{field:'date',label:'Date'},{field:'cell',label:'Cell'}],epochs:page.epochs||[],branches:page.branches.map((branch,index)=>({...branch,key:branch.path.at(-1),label:`Group ${index}`,value:branch.path.at(-1),cells:1,duration_seconds:0}))});
  let holdNext=false;
  h.fixture.respond=(url,options,fallback)=>{
   if(!url.pathname.endsWith('/candidate/tree/page'))return fallback();
   const body=JSON.parse(options.body),page=decorate(response(body));
   if(holdNext&&body.path.length){holdNext=false;return new Promise(resolve=>{release=()=>resolve(page);});}
   return page;
  };
  function Owner({revision=0}){
   const [ids,setIds]=useState([]),[intent,setIntent]=useState(null),[message,setMessage]=useState(''),mounted=useRef(false);
   selected=ids;feedback=message;
   useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
   const report=useCallback(value=>{if(mounted.current){notifications++;setMessage(value);}},[]);
   return createElement('section',null,message&&createElement('p',{role:'alert'},message),createElement(Host,{active:true,tree:{...scopeProps,revision,selectedEpochs:ids,setSelectedEpochs:setIds,treeSelectionIntent:intent,onTreeSelectionIntentChange:setIntent,onTreeSelectionFeedback:report}}));
  }
  await h.mount(Owner);
  const toggle=()=>h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('tp-branch'))[0].parent.findByProps({role:'switch'});
  await h.waitFor(()=>h.root.findAllByProps({role:'switch'}).length>0&&!toggle().props.disabled);
  const old=h.root.findByType(Paged);
  holdNext=true;await h.act(()=>{pending=toggle().props.onClick(event());});
  await h.waitFor(()=>!!release);
  await h.render(Owner,{revision:1});
  assert.notEqual(h.root.findByType(Paged),old,'real retained wrapper must evict the old PagedTree');
  assert.deepEqual(selected,[]);assert.match(feedback,/The view refreshed before this selection finished/);
  assert.match(h.root.findByProps({role:'alert'}).children.join(''),/Switch the branch again/);
  await h.waitFor(()=>!toggle().props.disabled);
  await h.act(()=>toggle().props.onClick(event()));
  assert.deepEqual(selected,['a','b','c']);assert.equal(feedback,'');
  await h.act(async()=>{release();await pending;});assert.deepEqual(selected,['a','b','c']);assert.equal(feedback,'');
  holdNext=true;release=null;await h.act(()=>{pending=toggle().props.onClick(event());});await h.waitFor(()=>!!release);
  const prior=notifications;await h.render(()=>null,{});assert.equal(notifications,prior,'whole owner unmount ignores child cleanup notifications');
  await h.act(async()=>{release();await pending;});assert.equal(notifications,prior);
 }finally{await h.close();}
});
