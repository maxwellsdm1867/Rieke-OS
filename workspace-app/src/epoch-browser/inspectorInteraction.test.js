import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectorPaneSizes,epochShortcutDirection,nextEpochAction,resourceForPath} from './inspectorInteraction.js';

test('an old page failure cannot cancel a newly requested anchor navigation',()=>{
  const old={path:'/epochs?offset=60',error:'Temporary failure',data:null,loading:false};
  const fresh=resourceForPath(old,'/epochs?anchor_uuid=target');
  assert.equal(fresh.loading,true);assert.equal(fresh.error,null);assert.equal(fresh.data,null);
  assert.equal(resourceForPath(old,old.path),old);
});

test('pane bounds reserve plot space, restore sensible defaults and overlay on narrow windows',()=>{
  const wide=inspectorPaneSizes(1300,{tree:2000,metadata:2000},true,true);
  assert.ok(wide.tree<=wide.treeMax);assert.ok(wide.metadata<=wide.metadataMax);
  assert.ok(1300-wide.tree-wide.metadata-14>=300);
  assert.equal(wide.overlay,false);
  const narrow=inspectorPaneSizes(760,{tree:340,metadata:400},true,true);
  assert.equal(narrow.overlay,true);assert.equal(narrow.metadata,400);
  assert.equal(narrow.columns,'340px 7px minmax(0,1fr)');
  assert.equal(inspectorPaneSizes(1100,{},false,false).columns,'minmax(0,1fr)');
  assert.equal(inspectorPaneSizes(1100,{tree:NaN}).tree,270);
});
test('W/S navigation ignores typing, composition, modifiers and old arrow bindings',()=>{
  const event={key:'s',target:{closest:()=>null}};
  assert.equal(epochShortcutDirection(event),1);
  assert.equal(epochShortcutDirection({...event,key:'w'}),-1);
  for(const modifier of ['altKey','ctrlKey','metaKey','shiftKey','defaultPrevented','isComposing'])assert.equal(epochShortcutDirection({...event,[modifier]:true}),0);
  assert.equal(epochShortcutDirection({...event,target:{closest:()=>({})}}),0);
  for(const key of ['ArrowLeft','ArrowUp','ArrowDown','Tab','W','S'])assert.equal(epochShortcutDirection({...event,key}),0);
  assert.equal(epochShortcutDirection({...event,nativeEvent:{isComposing:true}}),0);
});
test('epoch navigation crosses chronological pages and locates a tree-selected offpage epoch',()=>{
  const epochs=Array.from({length:60},(_,i)=>({epoch_uuid:`e${60+i}`}));
  const scope={epochs,offset:60,total:1776};
  assert.deepEqual(nextEpochAction({...scope,focused:'e60',direction:-1}),{kind:'page',offset:0,edge:'last'});
  assert.deepEqual(nextEpochAction({...scope,focused:'e119',direction:1}),{kind:'page',offset:120,edge:'first'});
  assert.deepEqual(nextEpochAction({...scope,focused:'e90',direction:1}),{kind:'focus',epoch_uuid:'e91'});
  assert.deepEqual(nextEpochAction({...scope,focused:'e1500',direction:1}),{kind:'locate',epoch_uuid:'e1500',direction:1});
  assert.deepEqual(nextEpochAction({epochs:[{epoch_uuid:'last'}],offset:0,total:1,focused:'last',direction:1}),{kind:'none'});
  assert.deepEqual(nextEpochAction({...scope,focused:null,direction:-1}),{kind:'none'});
});

test('Tab advances epochs only in navigation regions and Shift+Tab goes back',()=>{
  const region={closest:()=>null};
  const event={key:'Tab',target:region,currentTarget:region};
  assert.equal(epochShortcutDirection(event),1);
  assert.equal(epochShortcutDirection({...event,shiftKey:true}),-1);
  const row={closest:selector=>selector.includes('.epoch-row')?{}:null};
  assert.equal(epochShortcutDirection({...event,target:row}),1);
  const input={closest:selector=>selector.includes('input')?{}:null};
  assert.equal(epochShortcutDirection({...event,target:input}),0);
  assert.equal(epochShortcutDirection({...event,target:{closest:()=>null}}),0);
});
