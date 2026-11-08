import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from '../test-support/isolatedVite.js';
import {fileURLToPath} from 'node:url';
import {createInspectorHarness} from '../test-support/inspectorHarness.js';

test('counted selection bar exposes tag, exclude and clear with freshness gates',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {EpochSelectionBar}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');
 let root;const actions=[];const props={targets:['a','b','c'],onTags:()=>actions.push('tags'),onExclude:()=>actions.push('exclude'),onInclude:()=>actions.push('include'),onClear:()=>actions.push('clear'),scope:'protocol exports'};
 const render=async next=>act(()=>{if(root)root.update(React.createElement(EpochSelectionBar,next));else root=TestRenderer.create(React.createElement(EpochSelectionBar,next));});
 try{
  await render({...props,cellCount:2});assert.match(JSON.stringify(root.toJSON()),/epochs selected/);
  assert.equal(root.root.findByProps({'aria-label':'2 selected cells'}).findByType('strong').children.join(''),'2');
  assert.equal(root.root.findByProps({'aria-label':'3 epochs selected'}).findByType('strong').children.join(''),'3');
  await render({...props,cellCount:null});
  assert.equal(root.root.findByProps({'aria-label':'Selected cell count unavailable'}).findByType('strong').children.join(''),'—');
  const buttons=root.root.findByProps({className:'epoch-selection-actions'}).findAllByType('button');assert.equal(buttons.length,3);
  for(const button of buttons){assert.equal(button.props.disabled,false);await act(()=>button.props.onClick());}
  assert.deepEqual(actions,['clear','tags','exclude']);
  await render({...props,onSelectAll:()=>actions.push('all'),onSelectCell:()=>actions.push('cell'),cellSelectDisabled:true});
  const all=root.root.findAllByType('button').find(button=>button.children.some(child=>typeof child==='string'&&child.trim()==='Select all'));
  const cell=root.root.findAllByType('button').find(button=>button.children.includes('Select focused cell'));
  assert.equal(all.props.disabled,false);assert.equal(cell,undefined);await act(()=>all.props.onClick());
  assert.equal(actions.at(-1),'all');
  await render({...props,scope:'search export'});
  assert.equal(root.root.findAllByType('button').filter(button=>button.children.some(child=>typeof child==='string'&&child.trim()==='Deselect all')).length,1,'Search keeps its shared clear action');
  await render({...props,disabled:true});assert.ok(root.root.findByProps({className:'epoch-selection-actions'}).findAllByType('button').every(button=>button.props.disabled));
  await render({...props,targets:[]});assert.equal(root.toJSON(),null);
 }finally{await act(()=>root?.unmount());await server.close();}
});

test('shared viewer renders bulk controls in list and tree modes without relying on a focused trace',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{name:'bulk-viewer-boundaries',enforce:'pre',resolveId(id,importer){if(importer?.endsWith('/epoch-browser/ui/EpochViewer.jsx')&&['./EpochBrowserLayout.jsx','../../typed-query/ui/TreeBuilder.jsx','../../tree-browser/ui/RetainedTreePresentation.jsx'].includes(id))return '\0bulk-empty';},load(id){if(id==='\0bulk-empty')return 'export default ()=>null;';}}]});
 const {default:Viewer}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochViewer.jsx');let root,removed=0;
 try{
  for(const [designMode,treeMode] of [[false,false],[false,true],[true,true]]){
   await act(()=>{const element=React.createElement(Viewer,{designMode,targets:['a','b'],selectionActions:{onInclude(){},onExclude(){},onRemove(){removed++;}},metadata:{onClearSelection(){}},layout:{metadataOpen:false},toolbar:{actions:[],onTags(){}},columnTree:{},treePane:{treeMode}});if(root)root.update(element);else root=TestRenderer.create(element);});
   assert.equal(root.root.findAllByProps({className:'inspection-scope bulk-active compact-selection'}).length,1);
   const labels=root.root.findAllByType('button').map(button=>button.children.filter(child=>typeof child==='string').join(''));
   assert.ok(labels.includes('Exclude'));assert.ok(!labels.some(label=>label.includes('Include selected')));
   const remove=root.root.findAllByType('button').find(button=>button.children.includes('Remove from pin'));
   assert.ok(remove);assert.equal(remove.props.disabled,false);await act(()=>remove.props.onClick());
  }
  assert.equal(removed,3);
 }finally{await act(()=>root?.unmount());await server.close();}
});

test('membership removal control requires its owner callback and obeys freshness and ordinary batch bounds',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {EpochSelectionBar}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');let root;
 const render=async props=>act(()=>{const element=React.createElement(EpochSelectionBar,props);if(root)root.update(element);else root=TestRenderer.create(element);});
 const remove=()=>root.root.findAllByType('button').filter(button=>button.children.includes('Remove from pin'));
 try{
  await render({targets:['a']});assert.equal(root.toJSON(),null);
  await render({targets:['a','b']});assert.equal(remove().length,0);
  await render({targets:['a','b'],onRemove(){},disabled:true});assert.equal(remove()[0].props.disabled,true);
  await render({targets:Array.from({length:1000},(_,i)=>String(i)),onRemove(){}});assert.equal(remove()[0].props.disabled,false);
  await render({targets:Array.from({length:1001},(_,i)=>String(i)),onRemove(){}});assert.equal(remove()[0].props.disabled,true);
  await render({targets:[],onRemove(){}});assert.equal(root.toJSON(),null);
 }finally{await act(()=>root?.unmount());await server.close();}
});


test('selection actions appear only for multiple epochs and collapse without changing selection',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {EpochSelectionBar}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');let root,cleared=0;
 const render=async targets=>act(()=>{const element=React.createElement(EpochSelectionBar,{targets,cellCount:2,onClear(){cleared++;}});if(root)root.update(element);else root=TestRenderer.create(element);});
 try{
  await render(['a']);assert.equal(root.toJSON(),null);
  await render(['a','b']);assert.equal(root.root.findByProps({'aria-label':'Hide selection actions'}).props['aria-expanded'],true);
  await act(()=>root.root.findByProps({'aria-label':'Hide selection actions'}).props.onClick());
  assert.equal(root.root.findAllByProps({className:'epoch-selection-actions'}).length,0);
  assert.equal(root.root.findByProps({'aria-label':'Show selection actions'}).props['aria-expanded'],false);
  assert.equal(root.root.findByProps({'aria-label':'2 epochs selected'}).findByType('strong').children.join(''),'2');assert.equal(cleared,0);
  await render(['a','b','c']);assert.equal(root.root.findAllByProps({className:'epoch-selection-actions'}).length,0);
  await act(()=>root.root.findByProps({'aria-label':'Show selection actions'}).props.onClick());assert.equal(root.root.findAllByProps({className:'epoch-selection-actions'}).length,1);
  await act(()=>root.root.findByProps({'aria-label':'Hide selection actions'}).props.onClick());
  await render(['a']);assert.equal(root.toJSON(),null);
  await render(['a','b']);assert.equal(root.root.findAllByProps({className:'epoch-selection-actions'}).length,1);assert.equal(cleared,0);
 }finally{await act(()=>root?.unmount());await server.close();}
});

test('incoming selection has one authoritative Deselect all, while Main and incoming fallbacks retain the shared action',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../..',import.meta.url)),configFile:false,server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'}});
 const {EpochSelectionBar}=await server.ssrLoadModule('/src/epoch-browser/ui/EpochBrowserChrome.jsx');
 const {default:IncomingSelectionTools}=await server.ssrLoadModule('/src/incoming-workbench/ui/IncomingSelectionTools.jsx');
 const children=(element,match)=>!element||typeof element!=='object'?[]:[...(match(element)?[element]:[]),...[element.props?.children].flat().flatMap(child=>children(child,match))];
 const label=node=>node.children.filter(child=>typeof child==='string').join('').trim();
 try{
  for(const mode of ['owned-list','owned-tree','no-portal','no-draft','main']){
   const h=await createInspectorHarness(),selected=['epoch-A','epoch-B'],changes=[];let root;
   const owned=mode.startsWith('owned');
   try{
    await h.render({protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',expected_binding_version:2,cells:[{cell_uuid:'cell-A',epochs:2}]},filters:{},revision:0,initialEpochUuid:'epoch-A',initialNavigation:{treeMode:mode==='owned-tree'},onSelectionChange:ids=>changes.push(ids),
      ...(mode!=='main'?{readContext:{root:'/protocols/protocol-A/workbench/candidates/candidate-A',candidate_scope_revision:'query-A'}}:{}),
      ...(mode!=='no-draft'?{draftSelection:{selected}}:{}),...(mode!=='no-portal'?{draftSelectionTarget:{}}:{})});
    if(mode==='no-draft'||mode==='main')await h.act(()=>h.viewer.treePane.listProps.setTargets(selected));
    changes.length=0;
    assert.equal(h.viewer.selectionActions.hideClear,owned,mode);
    const incoming=children(h.viewer.before,item=>item.props?.source?.readContext&&typeof item.props?.onViewSelected==='function')[0];
    assert.equal(!!incoming,owned,mode);
    await act(()=>{root=TestRenderer.create(React.createElement(React.Fragment,null,
      incoming&&React.createElement(IncomingSelectionTools,incoming.props),
      React.createElement(EpochSelectionBar,{...h.viewer.selectionActions,targets:h.viewer.targets,onClear:h.viewer.metadata.onClearSelection})));});
    const clear=root.root.findAllByType('button').filter(button=>label(button)==='Deselect all');
    assert.equal(clear.length,1,mode);assert.equal(clear[0].props.disabled,false,mode);
    await h.act(()=>clear[0].props.onClick());
    assert.deepEqual(changes,[[]],mode);
    if(owned)assert.deepEqual(h.viewer.treePane.treeProps.treeSelectionIntent.markers,[{path:[],on:false}],mode);
   }finally{await act(()=>root?.unmount());await h.close();}
  }
 }finally{await server.close();}
});
