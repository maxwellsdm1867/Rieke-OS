import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
import {createServer} from './test-support/isolatedVite.js';

const serverOptions={root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error'};
test('actual annotation and candidate export controls retain unfinished text and format across Activity reconnect',async()=>{
 const server=await createServer(serverOptions);let tree;
 const [{default:Tags},{default:Export}]=await Promise.all([server.ssrLoadModule('/src/annotations/ui/AnnotationTags.jsx'),server.ssrLoadModule('/src/exports/ui/CandidateExportPanel.jsx')]);
 const epoch=id=>({epoch_uuid:id,cell_uuid:'cell',annotations:{cell_tags:[],epoch_tags:[]}});
 const render=async(mode,id='a')=>act(async()=>{const element=React.createElement(React.Activity,{mode},React.createElement(Tags,{epoch:epoch(id)}),React.createElement(Export,{candidate:{revision_uuid:id,recipe:{epoch_count:1,full_recipe_sha256:'sha'}}}));tree?tree.update(element):tree=TestRenderer.create(element);});
 try{await render('visible');const tag=()=>tree.root.findAllByType('input').find(n=>n.props.placeholder?.includes('tag'));const name=()=>tree.root.findAllByType('input').find(n=>n.props.maxLength===120);
  assert.ok(tag());await act(()=>{tag().props.onChange({target:{value:'unfinished annotation'}});name().props.onChange({target:{value:'My export'}});tree.root.findByProps({value:'matlab-mat'}).props.onChange();});
  await render('hidden');await render('visible');assert.equal(tag().props.value,'unfinished annotation');assert.equal(name().props.value,'My export');assert.equal(tree.root.findByProps({value:'matlab-mat'}).props.checked,true);
  await render('visible','b');assert.equal(tag().props.value,'');assert.equal(name().props.value,'');assert.equal(tree.root.findByProps({value:'wheeler-sqlite'}).props.checked,true);
 }finally{await act(()=>tree?.unmount());await server.close();}
});

test('pending hidden panels keep owners mounted while their real portals are hidden and inert',async()=>{
 const portalServer=await createServer(serverOptions);const {EpochBrowserToolbar}=await portalServer.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');
 const {RetainedWorkspaceViews,RetainedWorkspacePanel,useRetainedViewProtection}=await portalServer.ssrLoadModule('/src/retainedWorkspaceViews.js');
 const css=await readFile(new URL('./WorkspaceNavigation.css',import.meta.url),'utf8');
 const dom=new JSDOM('<style>'+css+'</style><main></main><header class="protocol-inspector-controls"></header>'),prior={window:globalThis.window,document:globalThis.document};Object.assign(globalThis,{window:dom.window,document:dom.window.document});
 const root=createRoot(document.querySelector('main')),target=document.querySelector('header');let cleanups=0,finish;const pending=new Promise(resolve=>{finish=resolve;});
 function Panel({name}){useRetainedViewProtection({busy:true});useEffect(()=>{pending.then(()=>{});return()=>cleanups++;},[]);return React.createElement(EpochBrowserToolbar,{portalTarget:target},React.createElement('button',{'data-owner':name},name));}
 const render=tab=>act(()=>root.render(React.createElement(RetainedWorkspaceViews,{route:{page:'protocol',protocol:'p',key:'p'},projectId:'p',projectPath:'/p',presentation:{remember(){}},render:()=>React.createElement(React.Fragment,null,...['inspect','workbench'].map(name=>React.createElement(RetainedWorkspacePanel,{key:name,name,visible:tab===name},React.createElement(Panel,{name}))))})));
 try{await render('inspect');await render('workbench');assert.equal(cleanups,0);assert.equal(target.querySelectorAll('[data-owner]').length,2);
  const old=target.querySelector('[data-owner="inspect"]').closest('[data-retained-portal-active]'),current=target.querySelector('[data-owner="workbench"]').closest('[data-retained-portal-active]');
  assert.equal(old.hidden,true);assert.equal(old.hasAttribute('inert'),true);assert.equal(old.style.display,'none');assert.equal(current.hidden,false);assert.equal(current.hasAttribute('inert'),false);
  const toolbar=current.querySelector('.compact-inspector-toolbar'),style=dom.window.getComputedStyle(toolbar);assert.equal(style.padding,'0px');assert.equal(style.gap,'7px');assert.equal(style.zIndex,'40');
  await render('inspect');assert.equal(cleanups,0);assert.equal(old.hidden,false);assert.equal(current.hidden,true);finish();await pending;
 }finally{await act(()=>root.unmount());Object.assign(globalThis,prior);dom.window.close();await portalServer.close();}
});

test('actual trace window input retains unfinished edits across hide/reveal and resets for another epoch',async()=>{
 const server=await createServer(serverOptions);let tree;
 const [{default:Trace},{WorkspaceRequestProvider}]=await Promise.all([server.ssrLoadModule('/src/traces/ui/TraceViewer.jsx'),server.ssrLoadModule('/src/workspaceRequest.js')]);
 const port={identity:'retained-trace-test',request:async path=>{const query=new URLSearchParams(path.split('?')[1]),start=+query.get('start'),count=+query.get('count');return {epoch_uuid:path.split('/')[2],stream_uuid:'s',start,count,total_samples:1000,sample_rate:1000,units:'pA',source_sha256:'source',decimated:false,values:Array(count).fill(1)};}};
 const render=(mode,id='a')=>act(async()=>{const element=React.createElement(WorkspaceRequestProvider,{port},React.createElement(React.Activity,{mode},React.createElement(Trace,{epoch:{epoch_uuid:id,streams:[{kind:'responses',uuid:'s',sample_count:1000,sample_rate:1000,units:'pA'}]},viewPreference:{kind:'sample',start:0,count:200}})));tree?tree.update(element):tree=TestRenderer.create(element);});
 try{await render('visible');await act(()=>tree.root.findAllByType('button').find(node=>node.props.children==='Sample').props.onClick());const start=()=>tree.root.findByProps({'aria-label':'Start sample'}),count=()=>tree.root.findByProps({'aria-label':'Sample count'});await act(()=>{start().props.onChange({target:{value:'123'}});count().props.onChange({target:{value:''}});});
  await render('hidden');await render('visible');assert.equal(start().props.value,'123');assert.equal(count().props.value,'');await render('visible','b');assert.equal(start().props.value,'0');assert.equal(count().props.value,'200');
 }finally{await act(()=>tree?.unmount());await server.close();}
});

test('saved candidate hydration runs once per identity and preserves later search edits on reveal',async()=>{
 const previousFetch=globalThis.fetch,previousWindow=globalThis.window,calls=[];let tree,snapshot;const dom=new JSDOM('');globalThis.window=dom.window;
 globalThis.fetch=async(path,options={})=>{calls.push(path);const body=path.includes('/explore/revisions/candidate-a?')?{revision_uuid:'candidate-a',recipe:{predicate:{all:[]},name:'Original candidate',splits:'date,cell'}}:path.includes('/explore/preview')?{matched_count:3,tree_revision:'tree',catalog:{fields:[]},tree:{count:3},last_run:{cell_count:1}}:path.includes('/fields')?{fields:[],tree_fields:[]}:{};return new Response(JSON.stringify(body),{status:200});};
 const server=await createServer({...serverOptions,plugins:[{name:'retained-search-controls',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/metadata-explorer/ui/MetadataExplorer.jsx')){if(id.endsWith('/MatchingEpochs.jsx'))return '\0retained-matching';if(id.endsWith('/QueryPresetDialog.jsx'))return '\0retained-preset';if(id.endsWith('/PredicateDialog.jsx'))return '\0retained-predicate';}},load(id){if(id==='\0retained-matching')return "export default 'retained-matching';";if(id==='\0retained-preset')return "export default 'retained-preset';";if(id==='\0retained-predicate')return "export default 'retained-predicate';";}}]});
 const {default:Explorer}=await server.ssrLoadModule('/src/metadata-explorer/ui/MetadataExplorer.jsx');
 const render=mode=>act(async()=>{const element=React.createElement(React.Activity,{mode},React.createElement(Explorer,{projectId:'p',initialRevisionId:'candidate-a',onSession:value=>{snapshot=value;}}));tree?tree.update(element):tree=TestRenderer.create(element);});
 try{await render('visible');const matching=()=>tree.root.findByType('retained-matching');assert.equal(snapshot.name,'Original candidate');
  await act(()=>matching().props.actions.find(item=>item?.label==='Save query preset').run());
  await act(()=>tree.root.findByType('retained-preset').props.onSaved({preset_uuid:'preset',name:'My revised name'}));
  await act(()=>matching().props.onTagFilter({all:[{field:'annotations/epoch/tags',operator:'contains',value:'new draft'}]}));
  const draft=structuredClone(snapshot.draft);await render('hidden');await render('visible');assert.equal(snapshot.name,'My revised name');assert.deepEqual(snapshot.draft,draft);
  assert.equal(calls.filter(path=>path.includes('/explore/revisions/candidate-a?')).length,1,'immutable candidate recipe is not reapplied over edits');assert.ok(calls.filter(path=>path.includes('/explore/preview')).length>=2,'current result authority still refreshes on reveal');
 }finally{await act(()=>tree?.unmount());await server.close();globalThis.fetch=previousFetch;globalThis.window=previousWindow;dom.window.close();}
});

test('hidden search local undo remains unavailable while an unrelated desktop write keeps Activity mounted',async()=>{
 const previousFetch=globalThis.fetch,previousWindow=globalThis.window;let tree,snapshot,finish;
 const dom=new JSDOM('');globalThis.window=dom.window;
 globalThis.fetch=async path=>new Response(JSON.stringify(path.includes('/explore/revisions/candidate-a?')?{revision_uuid:'candidate-a',recipe:{predicate:{all:[]},name:'Candidate',splits:'date,cell'}}:path.includes('/explore/preview')?{matched_count:3,tree_revision:'tree',catalog:{fields:[]},tree:{count:3},last_run:{cell_count:1}}:path.includes('/fields')?{fields:[],tree_fields:[]}:{}),{status:200});
 const server=await createServer({...serverOptions,plugins:[{name:'retained-undo-control',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/metadata-explorer/ui/MetadataExplorer.jsx')&&id.endsWith('/MatchingEpochs.jsx'))return '\0retained-undo-matching';},load(id){if(id==='\0retained-undo-matching')return "export default 'retained-undo-matching';";}}]});
 const [{default:Explorer},{RetainedWorkspaceViews},{mutationUndo},{trackWrite}]=await Promise.all([server.ssrLoadModule('/src/metadata-explorer/ui/MetadataExplorer.jsx'),server.ssrLoadModule('/src/retainedWorkspaceViews.js'),server.ssrLoadModule('/src/undo/mutationUndo.js'),server.ssrLoadModule('/src/desktopLifecycle.js')]);mutationUndo.project('undo-project');
 const presentation={remember(){}},render=key=>act(async()=>{const node=React.createElement(RetainedWorkspaceViews,{route:{page:key==='search'?'explore':'overview',key},projectId:'undo-project',projectPath:'/undo-project',presentation,render:route=>route.page==='explore'?React.createElement(Explorer,{projectId:'undo-project',undoScopeId:'viewer',initialRevisionId:'candidate-a',onSession:value=>{snapshot=value;}}):null});tree?tree.update(node):tree=TestRenderer.create(node);});
 try{await render('search');await act(()=>tree.root.findByType('retained-undo-matching').props.onToggleInclusion({epoch_uuid:'epoch'},false));assert.deepEqual(snapshot.excludedEpochs,['epoch']);assert.equal(mutationUndo.view().count,1);
  const write=trackWrite(new Promise(resolve=>{finish=resolve;}));await render('other');assert.equal(tree.root.findAllByType('retained-undo-matching').length,1,'busy hidden owner is still mounted');let undone;await act(async()=>{undone=await mutationUndo.undo(()=>assert.fail('local undo must never become a scientific request'));});assert.equal(undone,false);assert.deepEqual(snapshot.excludedEpochs,['epoch']);assert.equal(mutationUndo.view().count,1);
  await render('search');await act(async()=>{undone=await mutationUndo.undo(()=>assert.fail('expected local undo'));});assert.equal(undone,true);assert.deepEqual(snapshot.excludedEpochs,[]);finish();await write;
 }finally{finish?.();await act(()=>tree?.unmount());mutationUndo.project(null);await server.close();globalThis.fetch=previousFetch;globalThis.window=previousWindow;dom.window.close();}
});
