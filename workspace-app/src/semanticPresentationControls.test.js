import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {fileURLToPath} from 'node:url';
import {createServer} from './test-support/isolatedVite.js';

async function harness(){
 const prior={window:globalThis.window,document:globalThis.document,fetch:globalThis.fetch};let tree,respond=()=>({});const requests=[],focuses=[],listeners=new Map();
 const listen=(name,fn)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);},unlisten=(name,fn)=>listeners.get(name)?.delete(fn);
 globalThis.window={innerWidth:1400,innerHeight:1000,addEventListener(){},removeEventListener(){}};
 globalThis.document={body:{},getElementById:()=>({scrollIntoView(){}}),addEventListener:listen,removeEventListener:unlisten};
 globalThis.fetch=async(path,options={})=>{requests.push(path);return new Response(JSON.stringify(await respond(path,options)),{status:200});};
 const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',plugins:[{name:'semantic-presentation-portals',enforce:'pre',resolveId(id){if(id==='virtual:semantic-portals')return '\0semantic-portals';},transform(source,id){if(['/TreeBuilder.jsx','/PredicateBuilder.jsx','/PredicateValueInput.jsx'].some(file=>id.endsWith(file)))return source.replace("from 'react-dom'","from 'virtual:semantic-portals'");},load(id){if(id==='\0semantic-portals')return 'export const createPortal=children=>children;';}}]});
 return {requests,focuses,listeners,module:path=>server.ssrLoadModule(path),set respond(fn){respond=fn;},async component(path){return (await server.ssrLoadModule(path)).default;},get root(){return tree.root;},async render(Component,props,mode='visible'){await act(async()=>{const node=React.createElement(React.Activity,{mode},React.createElement(Component,props));tree?tree.update(node):tree=TestRenderer.create(node,{createNodeMock:node=>({focus(){focuses.push(node.props['aria-label']||node.type);},getBoundingClientRect:()=>({left:20,top:20,bottom:50,width:200}),contains:()=>false,closest:()=>null,showModal(){},close(){},querySelector(){return null;}})});});},act,async close(){await act(()=>tree?.unmount());await server.close();Object.assign(globalThis,prior);}};
}
const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):node?.children?text(node.children):'';

test('metadata pagination and cell disclosures survive same-identity reveal and follow real identity changes',async()=>{
 const h=await harness();try{const Metadata=await h.component('/src/epoch-browser/ui/MetadataTable.jsx'),data=Object.fromEntries(Array.from({length:170},(_,i)=>[`field-${i}`,i]));
  await h.render(Metadata,{data});await h.act(()=>h.root.findByProps({className:'metadata-show-more'}).props.onClick());assert.equal(h.root.findAllByProps({className:'metadata-value-row'}).length,160);
  await h.render(Metadata,{data},'hidden');await h.render(Metadata,{data});assert.equal(h.root.findAllByProps({className:'metadata-value-row'}).length,160);
  await h.render(Metadata,{data:{...data,other:1}});assert.equal(h.root.findAllByProps({className:'metadata-value-row'}).length,80);
  const Cells=await h.component('/src/cell-qc/ui/CellTypeAccordions.jsx'),props={cells:[{cell_uuid:'c',cell_type:'ON parasol',epochs:2}],revealKey:'filter-a'};
  await h.render(Cells,props);const toggle=()=>h.root.findByProps({className:'cell-type-toggle'});assert.equal(toggle().props['aria-expanded'],true);await h.act(()=>toggle().props.onClick());
  await h.render(Cells,props,'hidden');await h.render(Cells,props);assert.equal(toggle().props['aria-expanded'],false);await h.render(Cells,{...props,revealKey:'filter-b'});assert.equal(toggle().props['aria-expanded'],true);
 }finally{await h.close();}
});

test('skim manual collapse is stable until focused epoch changes, and repeated tag focus is not replayed',async()=>{
 const h=await harness();try{const Skim=await h.component('/src/epoch-browser/ui/EpochSkimList.jsx'),epochs=[{epoch_uuid:'a',cell_uuid:'c',date:'day',cell_label:'Cell'},{epoch_uuid:'b',cell_uuid:'c',date:'day',cell_label:'Cell'}],props={epochs,offset:0,focused:'a',onFocus(){}};
  await h.render(Skim,props);const heading=()=>h.root.findByProps({className:'epoch-skim-heading'});await h.act(()=>heading().props.onClick());assert.equal(heading().props['aria-expanded'],false);
  await h.render(Skim,props,'hidden');await h.render(Skim,{...props,epochs:epochs.map(epoch=>({...epoch}))});assert.equal(heading().props['aria-expanded'],false);await h.render(Skim,{...props,focused:'b'});assert.equal(heading().props['aria-expanded'],true);
  const Tags=await h.component('/src/annotations/ui/EpochTags.jsx'),tagProps={value:'',onValue(){},onAdd(){},onRemove(){},focusRequest:1};h.respond=()=>({tags:[]});await h.render(Tags,tagProps);const input=()=>h.root.findByProps({role:'combobox'});const firstFocus=h.focuses.length;
  await h.act(()=>h.root.findByProps({'aria-label':'Close tag suggestions'}).props.onClick());await h.render(Tags,tagProps,'hidden');await h.render(Tags,tagProps);assert.equal(input().props['aria-expanded'],false);assert.equal(h.focuses.length,firstFocus);
  await h.render(Tags,{...tagProps,focusRequest:2});assert.equal(input().props['aria-expanded'],true);assert.equal(h.focuses.length,firstFocus+1);
 }finally{await h.close();}
});

test('source-event pagination survives route reveal and changes only for another source',async()=>{
 const h=await harness();const source=sha=>({source_sha256:sha,filename:`${sha}.h5`,source_path:`/${sha}.h5`,state:{version:1,archived:false,included:true},counts:{cells:0,epochs:0},file_status:'available'});
 h.respond=path=>path==='/api/data-stores'?{data_stores:[source('a'),source('b')]}:path.includes('/events?')?{events:[{event_uuid:'e',action:'import',occurred_at:'2026-10-13'}],has_more:true}:source(path.split('/').at(-1));
 try{const Stores=await h.component('/src/project-workspace/ui/DataStores.jsx'),props={session:{selected:'a'}};await h.render(Stores,props);await h.act(()=>h.root.findByProps({'aria-label':'Next source events'}).props.onClick());assert.ok(h.requests.some(path=>path.includes('/a/events?limit=50&offset=50')));
  h.requests.length=0;await h.render(Stores,props,'hidden');await h.render(Stores,props);assert.ok(h.requests.some(path=>path.includes('/a/events?limit=50&offset=50')));assert.ok(!h.requests.some(path=>path.includes('/a/events?limit=50&offset=0')));
 }finally{await h.close();}
});

test('protocol application preserves chosen target and disclosure but retires removal consent on reconnect',async()=>{
 const h=await harness();h.respond=()=>({compatibility:{compatible:true,epoch_count:3,protocols:[],expected_protocol_ids:['p']},diff_counts:{added:0,removed:1,unchanged:2},expected_binding_version:2,expected_query_revision:'query'});
 try{const Apply=await h.component('/src/protocol-overview/ui/ProtocolApplyPanel.jsx'),props={candidate:{revision_uuid:'c'},protocols:[{protocol_uuid:'p1',name:'First'},{protocol_uuid:'p2',name:'Second'}],initialProtocolId:'p1'};
  await h.render(Apply,props);await h.act(()=>h.root.findByProps({'aria-label':'Target protocol'}).props.onChange({target:{value:'p2'}}));await h.act(()=>h.root.findByProps({className:'protocol-diff-toggle'}).props.onClick());const consent=()=>h.root.findAllByType('input').find(node=>node.props.type==='checkbox');await h.act(()=>consent().props.onChange({target:{checked:true}}));
  const comparisons=h.requests.length;await h.render(Apply,props,'hidden');await h.render(Apply,props);assert.equal(h.root.findByProps({'aria-label':'Target protocol'}).props.value,'p2');assert.equal(h.root.findByProps({className:'protocol-diff-toggle'}).props['aria-expanded'],false);assert.equal(consent().props.checked,false);assert.ok(h.requests.length>comparisons,'fresh comparison is still requested');
 }finally{await h.close();}
});

test('field and split chooser pagination and keyboard position survive Activity reconnect',async()=>{
 const h=await harness(),fields=Array.from({length:120},(_,i)=>({id:`metadata/field${i}`,label:`Recorded field ${String(i).padStart(3,'0')}`,path:`field${i}`,category:'Epoch',value_types:['string'],operators:['eq']}));
 h.respond=()=>({fields,tree_fields:fields});
 try{const Predicate=await h.component('/src/typed-query/ui/PredicateBuilder.jsx'),props={draft:{id:'g',kind:'group',operator:'all',children:[{id:'c',kind:'condition',field:fields[0].id,operator:'eq',valueType:'string',valueText:'value'}]},fields,onChange(){}};
  await h.render(Predicate,props);await h.act(()=>h.root.findByProps({className:'pb-field-button'}).props.onClick());const fieldSearch=()=>h.root.findByProps({'aria-label':'Find predicate field'});
  await h.act(()=>h.root.findAllByType('button').find(node=>text(node)==='Show more').props.onClick());assert.equal(h.root.findAllByProps({role:'option'}).length,100);await h.act(()=>fieldSearch().props.onKeyDown({key:'ArrowDown',preventDefault(){}}));const selected=fieldSearch().props['aria-activedescendant'];
  await h.render(Predicate,props,'hidden');await h.render(Predicate,props);assert.equal(h.root.findAllByProps({role:'option'}).length,100);assert.equal(fieldSearch().props['aria-activedescendant'],selected);
  await h.act(()=>fieldSearch().props.onChange({target:{value:'Recorded'}}));assert.equal(h.root.findAllByProps({role:'option'}).length,50);
  const Tree=await h.component('/src/typed-query/ui/TreeBuilder.jsx'),treeProps={value:[],onChange(){},catalogData:{fields},summaryEnabled:false,loading:false};await h.render(Tree,treeProps);await h.act(()=>h.root.findByProps({className:'tb-add-split'}).props.onClick());const splitSearch=()=>h.root.findByProps({'aria-label':'Find a split field'});await h.act(()=>splitSearch().props.onChange({target:{value:'Recorded'}}));
  await h.act(()=>h.root.findByProps({className:'tb-more'}).props.onClick());assert.equal(h.root.findAllByProps({role:'option'}).length,80);await h.act(()=>splitSearch().props.onKeyDown({key:'ArrowDown',preventDefault(){}}));const selectedSplit=splitSearch().props['aria-activedescendant'];
  await h.render(Tree,treeProps,'hidden');await h.render(Tree,treeProps);assert.equal(h.root.findAllByProps({role:'option'}).length,80);assert.equal(splitSearch().props['aria-activedescendant'],selectedSplit);
  await h.act(()=>splitSearch().props.onChange({target:{value:'field'}}));assert.equal(h.root.findAllByProps({role:'option'}).length,40);
 }finally{await h.close();}
});

for(const kind of ['field','split','value'])test(`a busy hidden ${kind} chooser detaches global handlers and hides its portal`,async()=>{
 const h=await harness();let finish;const fields=Array.from({length:60},(_,i)=>({id:`metadata/field${i}`,label:`Field ${i}`,path:`field${i}`,category:'Epoch',value_types:['string'],operators:['eq']}));h.respond=()=>({fields,tree_fields:fields});
 try{const {RetainedWorkspaceViews}=await h.module('/src/retainedWorkspaceViews.js'),{trackWrite}=await h.module('/src/desktopLifecycle.js');
  const Component=await h.component(kind==='field'?'/src/typed-query/ui/PredicateBuilder.jsx':kind==='split'?'/src/typed-query/ui/TreeBuilder.jsx':'/src/typed-query/ui/PredicateValueInput.jsx');
  const props=kind==='field'?{draft:{id:'g',kind:'group',operator:'all',children:[{id:'c',kind:'condition',field:fields[0].id,operator:'eq',valueType:'string',valueText:''}]},fields,onChange(){}}:kind==='split'?{value:[],onChange(){},catalogData:{fields},summaryEnabled:false,loading:false}:{node:{field:'protocol',valueText:''},choices:[{type:'string',value:'test'}],pinnedProtocols:[],onChange(){}};
  const presentation={remember(){}};function Host({show}){return React.createElement(RetainedWorkspaceViews,{route:{page:show?'explore':'overview',key:show?'editor':'other'},projectId:'p',projectPath:'/p',presentation,render:route=>route.page==='explore'?React.createElement(Component,props):null});}
  await h.render(Host,{show:true});const trigger=()=>kind==='field'?h.root.findByProps({className:'pb-field-button'}):kind==='split'?h.root.findByProps({className:'tb-add-split'}):h.root.findByProps({'aria-label':'Show value suggestions'});await h.act(()=>trigger().props.onClick());const popupClass=kind==='field'?'pb-field-popup pb-field-portal':kind==='split'?'tb-popup':'pb-value-popup';assert.equal(h.root.findAllByProps({className:popupClass}).length,1);assert.equal(h.listeners.get('pointerdown')?.size,1);
  const pending=trackWrite(new Promise(resolve=>{finish=resolve;}));await h.render(Host,{show:false});assert.equal(h.root.findAllByProps({className:popupClass}).length,0);assert.equal(h.listeners.get('pointerdown')?.size,0);
  await h.render(Host,{show:true});assert.equal(h.root.findAllByProps({className:popupClass}).length,1);assert.equal(h.listeners.get('pointerdown')?.size,1);finish();await pending;
 }finally{finish?.();await h.close();}
});

test('dismissed import auto-open intent is not replayed on Activity reconnect',async()=>{
 const h=await harness();h.respond=()=>({});
 try{const {ImportSuggestions}=await h.module('/src/protocol-overview/ui/ProtocolSuggestion.jsx'),props={projectId:'p',autoOpenJobUuid:'job-a',jobs:[{job_uuid:'job-a',status:'complete',filename:'source.h5'}]};
  await h.render(ImportSuggestions,props);const summary=()=>h.root.findAllByProps({className:'import-readiness'});assert.equal(summary().length,1);await h.act(()=>h.root.findByProps({'aria-label':'Close import review'}).props.onClick());assert.equal(summary().length,0);
  await h.render(ImportSuggestions,props,'hidden');await h.render(ImportSuggestions,props);assert.equal(summary().length,0);await h.render(ImportSuggestions,{...props,autoOpenJobUuid:'job-b',jobs:[{job_uuid:'job-b',status:'complete',filename:'next.h5'}]});assert.equal(summary().length,1);
 }finally{await h.close();}
});

test('collapsed import attention details reopen only for a new attention transition',async()=>{
 const h=await harness();try{const History=await h.component('/src/recording-import/ui/ImportHistory.jsx'),job={job_uuid:'j',status:'failed',error:'Import failed',filename:'source.h5'},props={jobs:[job]};await h.render(History,props);const row=()=>h.root.findAllByType('details').find(node=>node.props.className?.startsWith('import-history-row'));
  assert.equal(row().props.open,true);await h.act(()=>{const target={open:false};row().props.onToggle({target,currentTarget:target});});await h.render(History,props,'hidden');await h.render(History,props);assert.equal(row().props.open,false);
  await h.render(History,{jobs:[{...job,status:'complete',error:undefined}]});assert.equal(row().props.open,false);await h.render(History,props);assert.equal(row().props.open,true);
 }finally{await h.close();}
});

test('metadata copy feedback reconnects its expiry timer instead of persisting indefinitely',async()=>{
 const h=await harness(),priorNavigator=Object.getOwnPropertyDescriptor(globalThis,'navigator'),originalTimeout=globalThis.setTimeout,originalClear=globalThis.clearTimeout,timers=new Map();
 try{const Metadata=await h.component('/src/epoch-browser/ui/MetadataTable.jsx'),props={data:{field:'value'},copyable:true};Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async()=>{}}}});
  globalThis.setTimeout=(callback,delay,...args)=>{if(delay!==6000)return originalTimeout(callback,delay,...args);const id={};timers.set(id,callback);return id;};globalThis.clearTimeout=id=>timers.has(id)?timers.delete(id):originalClear(id);
  await h.render(Metadata,props);await h.act(()=>h.root.findByProps({'aria-label':'Copy setting value field'}).props.onClick());assert.equal(timers.size,1);assert.equal(h.root.findAllByProps({className:'metadata-copy-feedback '}).length,1);
  await h.render(Metadata,props,'hidden');assert.equal(timers.size,0);await h.render(Metadata,props);assert.equal(timers.size,1);await h.act(()=>{for(const callback of [...timers.values()])callback();});assert.equal(h.root.findAllByProps({className:'metadata-copy-feedback '}).length,0);
 }finally{await h.close();globalThis.setTimeout=originalTimeout;globalThis.clearTimeout=originalClear;if(priorNavigator)Object.defineProperty(globalThis,'navigator',priorNavigator);else delete globalThis.navigator;}
});


test('combined fields reuse the split chooser with search, pagination and an explicit apply',async()=>{
 const h=await harness(),changes=[];
 const fields=[...Array.from({length:55},(_,i)=>({id:`properties/field${i}`,label:`Other ${i}`,category:'Properties'})),
  ...['history1','history2','target'].map(id=>({id:`parameters/${id}`,label:id,category:'Parameters',examples:['[0,1]']}))];
 h.respond=()=>({fields});
 try{
  const Tree=await h.component('/src/typed-query/ui/TreeBuilder.jsx');
  await h.render(Tree,{value:['parameters/history1'],onChange:value=>changes.push(value),catalogData:{fields},summaryEnabled:false});
  const openField=async()=>{const button=h.root.findAllByType('button').find(node=>['Add a field','Add another field'].includes(text(node)));await h.act(()=>button.props.onClick({currentTarget:{focus(){},contains:()=>false,getBoundingClientRect:()=>({left:20,top:100,bottom:130,width:200})}}));};
  await openField();
  assert.equal(h.root.findAllByProps({role:'option'}).length,3,'protocol settings come first, including an existing separate level');
  const search=()=>h.root.findByProps({'aria-label':'Find a split field'});
  await h.act(()=>search().props.onChange({target:{value:'history1'}}));
  assert.equal(h.root.findAllByProps({role:'option'}).length,1);
  await h.act(()=>search().props.onKeyDown({key:'Enter',preventDefault(){}}));
  assert.equal(changes.length,0,'choosing a component does not change the tree');
  assert.match(text(h.root.findByProps({'aria-label':'Fields to combine'})),/History 1/);
  assert.equal(h.root.findAll(node=>typeof node.children?.[0]==='string'&&/Summary unavailable|Recorded examples unavailable/.test(node.children[0])).length,0);
  await openField();
  assert.equal(h.root.findAllByProps({role:'option'}).length,2,'selected components are omitted');
  await h.act(()=>search().props.onChange({target:{value:'Other'}}));
  assert.equal(h.root.findAllByProps({role:'option'}).length,40);
  await h.act(()=>h.root.findByProps({className:'tb-more'}).props.onClick());
  assert.equal(h.root.findAllByProps({role:'option'}).length,55,'the same show-more control reaches all fields');
  await h.act(()=>search().props.onChange({target:{value:'history2'}}));
  await h.act(()=>h.root.findByProps({role:'option'}).props.onClick());
  await h.act(()=>h.root.findByProps({className:'tb-joint-apply'}).props.onClick());
  assert.deepEqual(changes,[['joint/parameters%2Fhistory1+parameters%2Fhistory2']]);
  assert.equal(h.requests.filter(path=>path.includes('tree-pages')).length,0,'field choice sends no tree preparation');
  await h.act(()=>h.root.findByProps({className:'tb-add-split'}).props.onClick());
  assert.equal(h.root.findByProps({role:'dialog'}).props['aria-label'],'Add a split');
 }finally{await h.close();}
});
