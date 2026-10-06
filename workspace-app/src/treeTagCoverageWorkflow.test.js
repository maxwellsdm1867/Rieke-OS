import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement,useLayoutEffect} from 'react';
import {incomingTreeSelectionScope} from './incoming-workbench/incomingSelection.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} requests counts only, omits aggregate badges and clears stale selection on first paint`,async()=>{
 const h=await createWorkflowHarness();let release;
 const page={revision:'a'.repeat(64),candidate_scope_revision:'scope-1',kind:'branches',path:[],depth:0,offset:0,limit:60,total:3,total_epochs:9,count:9,cells:3,duration_seconds:0,selection:{count:9},split_order:['date'],levels:[{field:'date',label:'Recording date'}],ancestors:[],epochs:[],has_more:false,
  branches:[3,1,0].map((tagged,index)=>({key:`group-${index}`,path:[`group-${index}`],label:`Group ${index}`,value:`group-${index}`,count:3,cells:1,duration_seconds:0,shared_tag_coverage:{total_epochs:3,tagged_epochs:tagged}}))};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?(assert.equal(JSON.parse(options.body).counts_only,true),page):fallback();
 const props={setSelectedEpochs:()=>{},protocolId:'protocol-A',readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'},splits:'date',revision:0};
 const withClass=value=>h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes(value));
 try{
  const Tree=await h.component(name),firstCommit=[];
  function ObservedTree(current){
   useLayoutEffect(()=>{if(current.revision)firstCommit.push([withClass('tag-coverage-all').length,withClass('incoming-branch-on').length]);},[current.revision]);
   return createElement(Tree,current);
  }
  await h.mount(ObservedTree,props);
  await h.waitFor(()=>withClass('incoming-branch-off').length===3);
  assert.equal(h.root.findAllByProps({className:'tree-tag-coverage'}).length,0);
  assert.equal(h.root.findAllByProps({className:'tp-distribution'}).length,0);
  assert.equal(withClass('incoming-branch-on').length,0,'saved tags cannot turn a selection branch green');
  assert.equal(withClass('incoming-branch-off').length,3);
  await h.render(ObservedTree,{...props,treeSelectionIntent:{scope:incomingTreeSelectionScope(props),revision:page.revision,markers:[{path:['group-1'],on:true}]}});
  assert.equal(withClass('incoming-branch-on').length,1,'only explicit branch intent is green');
  assert.equal(h.root.findAll(node=>node.props.role==='switch'&&node.props['aria-checked']===true).length,1);
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?new Promise(resolve=>{release=resolve;}):fallback();
  await h.render(ObservedTree,{...props,revision:1});
  assert.deepEqual(firstCommit,[[0,0]],'same-candidate changed scope must drop green before passive loading effects');
  await h.waitFor(()=>!!release);assert.equal(withClass('tag-coverage-all').length,0,'retained response cannot paint current green');
  await h.act(()=>release({...page,candidate_scope_revision:'scope-1',branches:page.branches.map(row=>({...row,shared_tag_coverage:null}))}));
  await h.settle(20);assert.equal(withClass('tag-coverage-all').length,0,'unavailable coverage stays neutral');
  assert.equal(h.root.findAllByProps({className:'tree-tag-coverage'}).length,0);
  if(name==='HierarchyTree'){await h.render(ObservedTree,{...props,browseOnly:true});await h.settle(20);assert.equal(h.root.findAllByProps({className:'incoming-tree-actions'}).length,0);}
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`${name} keeps committed branch selection while expansion waits`,async()=>{
 const h=await createWorkflowHarness();let release;
 const revision='a'.repeat(64),item={key:'parent',path:['parent'],label:'Parent',value:'parent',count:2};
 const page={revision,candidate_scope_revision:'scope',kind:'branches',path:[],depth:0,offset:0,limit:60,total:1,total_epochs:2,selection:{count:2},split_order:['date'],levels:[{field:'date',label:'Date'}],ancestors:[],epochs:[],branches:[item],has_more:false};
 const child={...page,kind:'epochs',path:['parent'],depth:1,total:2,branches:[],epochs:[{epoch_uuid:'a',cell_uuid:'c'},{epoch_uuid:'b',cell_uuid:'c'}],ancestors:[{...item,parent_offset:0}]};
 const props={protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope'},splits:'date',revision:0,selectedEpochs:['a','b'],setSelectedEpochs:()=>assert.fail('Navigation must not change selection')};
 props.treeSelectionIntent={scope:incomingTreeSelectionScope(props),revision,markers:[{path:['parent'],on:true}]};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?(JSON.parse(options.body).path.length?new Promise(resolve=>{release=()=>resolve(child);}):page):fallback();
 try{
  const Tree=await h.component(name);await h.mount(Tree,props);
  const switches=()=>h.root.findAll(node=>node.type==='button'&&node.props.role==='switch');
  await h.waitFor(()=>switches().length===1&&switches()[0].props['aria-checked']===true);
  const branch=h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('incoming-branch-on'))[0];
  await h.act(()=>branch.props.onClick());await h.waitFor(()=>!!release);
  assert.equal(switches()[0].props['aria-checked'],true,'loading must not paint the committed switch off');
  assert.equal(switches()[0].props.disabled,true,'loading must keep selection inert');
  assert.ok(h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('incoming-branch-on')).length);
  await h.act(()=>release());await h.settle(25);
  assert.equal(switches()[0].props['aria-checked'],true);
  assert.equal(switches()[0].props.disabled,false);
 }finally{await h.close();}
});

test('ColumnTree replaces pending navigation, accumulates paging and fences old-scope handlers',async()=>{
 const h=await createWorkflowHarness(),held=[];let hold=false;
 const revision='b'.repeat(64),branches=['a','b'].map(key=>({key,path:[key],label:key,value:key,count:2}));
 const root={revision,candidate_scope_revision:'scope',kind:'branches',path:[],depth:0,offset:0,limit:60,total:180,total_epochs:180,selection:{count:180},split_order:['date'],levels:[{field:'date',label:'Date'}],ancestors:[],epochs:[],branches,has_more:true};
 const props={protocolId:'p',readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope',tree_column_pages:true},splits:'date',revision:0,design:true,selectedEpochs:[],setSelectedEpochs:()=>assert.fail('Navigation cannot select')};
 function response(body){const page={...root,path:body.path,offset:body.offset||0};if(body.path.length)Object.assign(page,{kind:'epochs',depth:1,total:2,epochs:[{epoch_uuid:body.path[0]+'1'},{epoch_uuid:body.path[0]+'2'}],branches:[],has_more:false,ancestors:[{...branches.find(x=>x.key===body.path[0]),parent_offset:0}]});const envelope={candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:0,generation:{id:'same'}};return {...page,...envelope,ancestor_pages:body.path.length?[{...root,...envelope}]:[]};}
 h.fixture.respond=(url,options,fallback)=>{if(!url.pathname.endsWith('/tree/page'))return fallback();const body=JSON.parse(options.body);if(!hold)return response(body);return new Promise(resolve=>held.push({body,resolve:()=>resolve(response(body)),signal:options.signal}));};
 const buttons=()=>h.root.findAll(node=>node.type==='button'&&node.props.className?.split(' ').includes('tp-branch'));
 try{
  const Tree=await h.component('ColumnTree');await h.mount(Tree,props);await h.waitFor(()=>buttons().length===2&&!buttons()[0].props.disabled);hold=true;
  const old=buttons()[0].props.onClick;
  await h.act(()=>buttons()[0].props.onClick());await h.waitFor(()=>held.length===1);
  assert.equal(buttons()[1].props.disabled,false,'navigation stays available');
  assert.equal(h.root.findAll(node=>node.type==='button'&&node.props.role==='switch')[0].props.disabled,true,'data actions stay blocked');
  await h.act(()=>buttons()[1].props.onClick());await h.waitFor(()=>held.length===2);
  await h.act(()=>buttons()[0].props.onClick());await h.waitFor(()=>held.length===3);
  assert.deepEqual(held.map(x=>x.body.path),[['a'],['b'],['a']]);
  await h.act(()=>held[2].resolve());await h.settle(15);await h.act(()=>{held[0].resolve();held[1].resolve();});await h.settle(15);
  assert.ok(h.root.findAll(node=>node.props['data-epoch-uuid']==='a1').length,'latest destination wins');
  await h.act(()=>buttons()[1].props.onClick());await h.waitFor(()=>held.length===4);
  await h.act(()=>buttons()[1].props.onClick());await h.waitFor(()=>held.length===5);
  assert.deepEqual(held[4].body.path,[],'second click closes the pending branch');
  await h.act(()=>held[4].resolve());await h.settle(15);await h.act(()=>held[3].resolve());await h.settle(15);
  const next=()=>h.root.findByProps({'aria-label':'Next page in column 1'});
  await h.act(()=>next().props.onClick());await h.waitFor(()=>held.length===6);
  await h.act(()=>next().props.onClick());await h.waitFor(()=>held.length===7);
  assert.deepEqual(held.slice(5).map(x=>x.body.offset),[60,120]);
  await h.act(()=>held[6].resolve());await h.settle(15);await h.act(()=>held[5].resolve());await h.settle(15);
  await h.render(Tree,{...props,presentationActivation:'new'});await h.waitFor(()=>held.length===8);
  await h.act(()=>old());assert.equal(held.length,8,'old activation handler is inert');
  await h.act(()=>held[7].resolve());await h.settle(15);
  await h.render(Tree,{...props,presentationActivation:'new',actionsDisabled:true});
  assert.equal(buttons()[0].props.disabled,true,'legacy external action gate also blocks navigation');
  await h.render(Tree,{...props,presentationActivation:'new',navigationDisabled:true});
  assert.equal(buttons()[0].props.disabled,true);const count=held.length;await h.act(()=>buttons()[0].props.onClick());assert.equal(held.length,count);
  await h.render(Tree,{...props,presentationActivation:'new',onSelectBranch:()=>{}});
  await h.act(()=>buttons()[0].props.onClick());await h.waitFor(()=>held.length===count+1);
  assert.equal(buttons()[1].props.disabled,true,'focus-producing navigation retains its existing pending gate');
  await h.act(()=>held[count].resolve());await h.settle(15);
 }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])for(const frozen of [false,true])test(`${name} ${frozen?'frozen':'live'} anchor shares one validated ancestor bundle`,async()=>{
 const priorFrame=globalThis.requestAnimationFrame,priorCancel=globalThis.cancelAnimationFrame;
 globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);globalThis.cancelAnimationFrame=clearTimeout;
 const h=await createWorkflowHarness(),calls=[];
 const revision='a'.repeat(64),key='b'.repeat(64),fence=frozen?{candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:1,generation:{metadata:'m'}}:{tree_column_pages:true,read_identity:{version:1,project_uuid:'project',project_path:'/fixture',protocol_uuid:'p',tree_revision:revision,generation:{metadata:'m',source:'s',annotation:'a',binding:'b',publication:'p',typed:null}}};
 const branch={key,path:[key],label:'Parent',value:'parent',count:1};
 const root={...fence,revision,kind:'branches',path:[],depth:0,offset:0,limit:60,total:1,total_epochs:1,selection:{count:1},split_order:['date'],levels:[{field:'date',label:'Date'}],ancestors:[],epochs:[],branches:[branch],has_more:false};
 const leaf={...root,kind:'epochs',path:[key],depth:1,branches:[],epochs:[{epoch_uuid:'target',cell_uuid:'c',epoch_number:1}],ancestors:[{...branch,parent_offset:0}],anchor:{epoch_uuid:'target',path:[key],index:0,offset:0},ancestor_pages:[root]};
 const props={protocolId:'p',splits:'date',browseOnly:true,...(frozen?{readContext:{root:'/protocols/p/workbench/candidates/c',candidate_scope_revision:'scope',tree_column_pages:true}}:{})};
 h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith(frozen?'/tree/page':'/tree-pages')?(calls.push(JSON.parse(options.body)),JSON.parse(options.body).anchor_uuid?leaf:JSON.parse(options.body).include_ancestors?{...root,ancestor_pages:[]}:root):fallback();
 try{
  const Tree=await h.component(name);await h.mount(Tree,props);
  await h.waitFor(()=>calls.length===1);await h.settle(30);
  await h.render(Tree,{...props,selected:'target'});
  await h.waitFor(()=>h.root.findAll(node=>node.props['data-epoch-uuid']==='target').length===1);
  assert.equal(calls.length,2);assert.equal(calls[1].include_ancestors,true);assert.equal(calls[1].anchor_uuid,'target');
 }finally{await h.close();if(priorFrame===undefined)delete globalThis.requestAnimationFrame;else globalThis.requestAnimationFrame=priorFrame;if(priorCancel===undefined)delete globalThis.cancelAnimationFrame;else globalThis.cancelAnimationFrame=priorCancel;}
});
