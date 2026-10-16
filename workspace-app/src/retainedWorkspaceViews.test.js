import test from 'node:test';
import assert from 'node:assert/strict';
import React,{useEffect,useRef,useState} from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {RetainedWorkspaceViews,useRetainedViewProtection,useRetainedModal,RetainedWorkspacePanel} from './retainedWorkspaceViews.js';
import {useResource} from './api.js';
import {useUnmountGuard} from './useUnmountGuard.js';
import {beginProjectUnmount} from './desktopLifecycle.js';

const route=(key,page='overview')=>({key,page});
const sessionOwner=()=>{const saved=new Map();return {saved,remember:(route,value)=>saved.set(route.key,value)};};

test('retained destinations preserve state and bind late callbacks to their own routes',async()=>{
 const owner=sessionOwner(),callbacks={},instances={};let tree;
 function Page({destination,remember}){
  const [instance]=useState(()=>instances[destination.key]=(instances[destination.key]||0)+1);
  const [text,setText]=useState('');callbacks[destination.key]={remember,setText};
  return React.createElement('input',{value:text,'data-instance':instance});
 }
 const render=async destination=>act(()=>{const element=React.createElement(RetainedWorkspaceViews,{route:destination,projectId:'p',projectPath:'/p',presentation:owner,
  render:(destination,{remember})=>React.createElement(Page,{destination,remember})});tree?tree.update(element):tree=TestRenderer.create(element);});
 try{
  await render(route('a'));await act(()=>callbacks.a.setText('unfinished'));const old=callbacks.a.remember;
  await render(route('b'));await act(()=>old({draft:'a'}));assert.deepEqual(owner.saved.get('a'),{draft:'a'});assert.equal(owner.saved.has('b'),false);
  await render(route('a'));const active=tree.root.findAllByType('div').find(node=>node.props['data-workspace-active']==='true');
  assert.equal(active.findByType('input').props.value,'unfinished');assert.equal(instances.a,1);
 }finally{await act(()=>tree.unmount());}
});

test('the cap evicts clean destinations but preserves dirty views and busy effect ownership',async()=>{
 const owner=sessionOwner(),instances={},cleanups={};let tree,dirty=true,busy=true;
 function Page({destination}){
  useRetainedViewProtection({dirty:destination.key==='a'&&dirty,busy:destination.key==='a'&&busy});
  useState(()=>instances[destination.key]=(instances[destination.key]||0)+1);
  useEffect(()=>()=>{cleanups[destination.key]=(cleanups[destination.key]||0)+1;},[]);
  return React.createElement('span',null,destination.key);
 }
 const render=async destination=>act(()=>{const element=React.createElement(RetainedWorkspaceViews,{route:destination,limit:1,projectId:'p',projectPath:'/p',presentation:owner,render:destination=>React.createElement(Page,{destination})});tree?tree.update(element):tree=TestRenderer.create(element);});
 try{
  await render(route('a'));await render(route('b'));assert.equal(cleanups.a||0,0,'a pending operation stays mounted while its view is hidden');
  assert.equal(tree.root.findAllByProps({'data-workspace-view':'a'}).length,1);
  await render(route('a'));assert.equal(instances.a,1);
  dirty=false;busy=false;await render(route('a'));await render(route('c'));
  assert.equal(tree.root.findAllByProps({'data-workspace-view':'a'}).length,0);assert.ok(cleanups.a>0);
 }finally{await act(()=>tree.unmount());}
});

test('completed display reads survive reveal while revision changes and scientific page witnesses reread',async()=>{
 const owner=sessionOwner(),oldFetch=globalThis.fetch,reads=[];let tree,revision=0,current;
 globalThis.fetch=async path=>{reads.push(path);return new Response(JSON.stringify({items:[],generation:reads.length}),{status:200});};
 function Page({destination}){current=useResource(destination.page==='stores'?'/protocols/p/epochs?limit=10':'/events',revision);return null;}
 const render=async destination=>act(async()=>{const element=React.createElement(RetainedWorkspaceViews,{route:destination,projectId:'p',projectPath:'/p',presentation:owner,render:destination=>React.createElement(Page,{destination})});tree?tree.update(element):tree=TestRenderer.create(element);});
 try{
  await render(route('a'));await render(route('b','stores'));await render(route('a'));
  assert.equal(reads.filter(path=>path==='/api/events').length,1);
  await render(route('b','stores'));assert.equal(reads.filter(path=>path.includes('/epochs?')).length,2,'fresh scientific reads are not treated as display cache');
  revision=1;await render(route('a'));assert.equal(reads.filter(path=>path==='/api/events').length,2);
  assert.equal(current.loading,false);
 }finally{await act(()=>tree.unmount());globalThis.fetch=oldFetch;}
});

test('hidden nested dirty guards remain registered and busy modals close without tearing down their operation owner',async()=>{
 const owner=sessionOwner();let tree,blocked=true,shows=0,closes=0,operationCleanups=0;
 function Editor(){
  const dialog=useRef(null);useUnmountGuard(blocked,'Unsaved hidden annotation');useRetainedViewProtection({dirty:blocked,busy:true});useRetainedModal(dialog);
  useEffect(()=>()=>operationCleanups++,[]);
  return React.createElement('dialog',{ref:dialog});
 }
 const render=async destination=>act(()=>{const element=React.createElement(RetainedWorkspaceViews,{route:destination,projectId:'p',projectPath:'/p',presentation:owner,
  render:destination=>destination.key==='a'?React.createElement(RetainedWorkspacePanel,{name:'inspect',visible:true},React.createElement(Editor)):null});tree?tree.update(element):tree=TestRenderer.create(element,{createNodeMock:element=>element.type==='dialog'?{showModal(){shows++;},close(){closes++;}}:null});});
 try{
  await render(route('a'));assert.equal(shows,1);await render(route('b'));
  assert.equal(closes,1,'a hidden busy modal leaves the active route usable');assert.equal(operationCleanups,0);
  assert.throws(()=>beginProjectUnmount(),/Unsaved hidden annotation/);
  blocked=false;await render(route('a'));const release=beginProjectUnmount();release();
 }finally{await act(()=>tree?.unmount());}
});

test('guard-only unsaved text survives clean-route eviction pressure',async()=>{
 const owner=sessionOwner();let tree,setText,instances=0;
 function Editor(){const [text,update]=useState('');setText=update;useState(()=>instances++);useUnmountGuard(!!text,'unfinished tag');return React.createElement('input',{value:text});}
 const render=async key=>act(()=>{const element=React.createElement(RetainedWorkspaceViews,{route:route(key),projectId:'p',projectPath:'/p',presentation:owner,limit:2,render:destination=>destination.key==='draft'?React.createElement(Editor):null});tree?tree.update(element):tree=TestRenderer.create(element);});
 try{await render('draft');await act(()=>setText('unfinished annotation'));for(let i=0;i<10;i++)await render(`clean-${i}`);await render('draft');assert.equal(instances,1);assert.equal(tree.root.findByType('input').props.value,'unfinished annotation');}finally{await act(()=>tree.unmount());}
});

test('a copied project with the same UUID and a new physical path discards every retained destination',async()=>{
 const owner=sessionOwner(),updates={},instances=[],cleaned=[];let tree;
 function Page({destination}){
  const [instance]=useState(()=>{const value=instances.length+1;instances.push(value);return value;});
  const [text,setText]=useState('');updates[destination.key]=setText;
  useEffect(()=>()=>cleaned.push(instance),[instance]);
  return React.createElement('input',{'data-instance':instance,value:text});
 }
 const render=async(projectPath,key)=>act(()=>{
  const element=React.createElement(RetainedWorkspaceViews,{route:route(key),projectId:'same-uuid',projectPath,presentation:owner,render:destination=>React.createElement(Page,{destination})});
  tree?tree.update(element):tree=TestRenderer.create(element);
 });
 const active=()=>tree.root.findAllByType('div').find(node=>node.props['data-workspace-active']==='true').findByType('input');
 try{
  await render('/owned/original','a');await act(()=>updates.a('original-a'));const first=active().props['data-instance'];
  await render('/owned/original','b');await act(()=>updates.b('original-b'));const second=active().props['data-instance'];
  await render('/owned/copied','a');assert.equal(active().props.value,'');assert.notEqual(active().props['data-instance'],first);
  assert.ok(cleaned.includes(first));assert.ok(cleaned.includes(second));
  assert.equal(tree.root.findAllByProps({'data-workspace-view':'b'}).length,0,'Hidden destinations from the prior physical project are discarded too');
  await render('/owned/copied','b');assert.equal(active().props.value,'');assert.notEqual(active().props['data-instance'],second);
 }finally{await act(()=>tree?.unmount());}
});
