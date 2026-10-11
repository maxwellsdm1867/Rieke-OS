import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

test('protocol sections collapse independently and organize temporarily reveals them',async()=>{
 const h=await createWorkflowHarness();
 try {
  const Sidebar=await h.component('ProtocolSidebar');
  const props={protocols:[{protocol_uuid:'a',name:'Noise'},{protocol_uuid:'b',name:'SingleSpot'}],onNavigate(){}};
  await h.mount(Sidebar,props);
  const toggle=label=>h.root.findByProps({'aria-label':`${label} section`});
  const rows=()=>h.root.findAll(node=>node.type==='div'&&node.props['data-protocol-shortcut']).map(node=>node.props['data-protocol-shortcut']);
  assert.deepEqual(rows(),['a']);
  await h.act(()=>toggle('Protocols').props.onClick());assert.deepEqual(rows(),[]);
  await h.act(()=>toggle('Typing & backtracking').props.onClick());assert.deepEqual(rows(),['b']);
  await h.act(()=>h.root.findByProps({'aria-label':'Organize protocols'}).props.onClick());assert.deepEqual(rows(),['a','b']);
  await h.act(()=>h.root.findByProps({'aria-label':'Done organizing protocols'}).props.onClick());assert.deepEqual(rows(),['b']);
 }finally{await h.close();}
});

test('mixed pinned creation requires explicit review and submits every recorded ID',async()=>{
 const h=await createWorkflowHarness(),requests=[];
 try {
  globalThis.fetch=async(input,options={})=>{
   requests.push({url:String(input),body:options.body&&JSON.parse(options.body)});
   return new Response(JSON.stringify(options.method==='POST'?{protocol_uuid:'combined'}:{protocols:[{protocol_id:'A',epoch_count:2},{protocol_id:'B',epoch_count:3}],epoch_count:5,cell_count:2,expected_recipe_sha256:'seal'}),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const New=await h.component('NewPinnedProtocol'),created=[];
  await h.mount(New,{candidate:{revision_uuid:'revision'},defaultName:'Combined',onCreated:id=>created.push(id)});
  await h.settle();
  const submit=()=>h.root.findByProps({type:'submit'});
  assert.equal(submit().props.disabled,true);
  await h.act(()=>h.root.findByProps({type:'checkbox'}).props.onChange({target:{checked:true}}));
  assert.equal(submit().props.disabled,false);
  await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.deepEqual(requests.at(-1).body,{name:'Combined',protocol_ids:['A','B'],expected_recipe_sha256:'seal'});
  assert.deepEqual(created,['combined']);
 }finally{await h.close();}
});

test('pinned rename retains UUID and sends the original name for conflict checks',async()=>{
 const h=await createWorkflowHarness(),requests=[],changed=[];
 try {
  globalThis.fetch=async(input,options={})=>{
   requests.push({url:String(input),body:options.body&&JSON.parse(options.body)});
   const result=options.method==='POST'?{protocol_uuid:'pin',name:'Combined'}:{format:'rieke-project-preferences',version:1,project_uuid:'project',revisions:{protocol_shortcuts:1,recent_searches:0},state:{protocol_shortcuts:{pin:{section:'pinned',rank:0}},recent_searches:[]}};
   return new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const Sidebar=await h.component('ProtocolSidebar');
  await h.mount(Sidebar,{projectId:'project',protocols:[{protocol_uuid:'pin',name:'Original'}],onChanged:()=>changed.push(true)});
  await h.settle();
  await h.act(()=>h.root.findByProps({'aria-label':'Pinned section'}).props.onClick());
  assert.equal(h.root.findAll(node=>node.type==='div'&&node.props['data-protocol-shortcut']).length,0);
  await h.act(()=>h.root.findByProps({'aria-label':'Organize protocols'}).props.onClick());
  await h.act(()=>h.root.findByProps({'aria-label':'Rename Original'}).props.onClick());
  await h.act(()=>h.root.findByProps({'aria-label':'Pinned protocol name'}).props.onChange({target:{value:'Combined'}}));
  await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.ok(requests.at(-1).url.endsWith('/protocols/pin/display-name'));
  assert.deepEqual(requests.at(-1).body,{name:'Combined',expected_name:'Original'});
  assert.deepEqual(changed,[true]);
 }finally{await h.close();}
});
