import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';

test('counted selection bar exposes tag, exclude, include and clear with freshness gates',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {EpochSelectionBar}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');
 let root;const actions=[];const props={targets:['a','b','c'],onTags:()=>actions.push('tags'),onExclude:()=>actions.push('exclude'),onInclude:()=>actions.push('include'),onClear:()=>actions.push('clear'),scope:'protocol exports'};
 const render=async next=>act(()=>{if(root)root.update(React.createElement(EpochSelectionBar,next));else root=TestRenderer.create(React.createElement(EpochSelectionBar,next));});
 try{
  await render(props);assert.match(JSON.stringify(root.toJSON()),/epochs selected/);
  const buttons=root.root.findAllByType('button');assert.equal(buttons.length,4);
  for(const button of buttons){assert.equal(button.props.disabled,false);await act(()=>button.props.onClick());}
  assert.deepEqual(actions,['tags','exclude','include','clear']);
  await render({...props,disabled:true});assert.ok(root.root.findAllByType('button').every(button=>button.props.disabled));
  await render({...props,targets:[]});assert.equal(root.toJSON(),null);
 }finally{await act(()=>root?.unmount());await server.close();}
});

test('shared viewer renders bulk controls in list and tree modes without relying on a focused trace',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{name:'bulk-viewer-boundaries',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/epoch-browser/ui/EpochViewer.jsx')&&['./EpochBrowserLayout.jsx','../../typed-query/ui/TreeBuilder.jsx','../../tree-browser/ui/RetainedTreePresentation.jsx'].includes(id))return '\0bulk-empty';},load(id){if(id==='\0bulk-empty')return 'export default ()=>null;';}}]});
 const {default:Viewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');let root;
 try{
  for(const designMode of [false,true]){
   await act(()=>{const element=React.createElement(Viewer,{designMode,targets:['a','b'],selectionActions:{onInclude(){},onExclude(){}},metadata:{onClearSelection(){}},layout:{metadataOpen:false},toolbar:{actions:[],onTags(){}},columnTree:{},treePane:{}});if(root)root.update(element);else root=TestRenderer.create(element);});
   assert.equal(root.root.findAllByProps({className:'inspection-scope bulk-active compact-selection'}).length,1);
   const labels=root.root.findAllByType('button').map(button=>button.children.filter(child=>typeof child==='string').join(''));
   assert.ok(labels.some(label=>label.includes('Exclude selected')));assert.ok(labels.some(label=>label.includes('Include selected')));
  }
 }finally{await act(()=>root?.unmount());await server.close();}
});
