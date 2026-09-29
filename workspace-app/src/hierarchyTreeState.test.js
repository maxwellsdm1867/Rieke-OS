import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeHierarchyPage,collapseHierarchy,expandHierarchy,hierarchySnapshot,hierarchyRestore,HIERARCHY_PAGE_LIMIT,cancelUnloadedExpansion} from './hierarchyTreeState.js';
const key=n=>n.toString(16).padStart(64,'0'),revision=key(999);
const page=(path,offset=0)=>({path,offset,revision,split_order:['date','cell','block'],kind:'branches',branches:[],epochs:[],total:100,total_epochs:500});
test('expanding one sibling retains the other hierarchy branch and collapse retains cache',()=>{
 let state={pages:[page([]),page([key(1)]),page([key(2)])],expanded:[[key(1)],[key(2)]]};
 state=mergeHierarchyPage(state,page([key(1),key(3)]));state=expandHierarchy(state,[key(1),key(3)]);
 assert.equal(state.pages.length,4);assert.deepEqual(state.expanded,[[key(1)],[key(2)],[key(1),key(3)]]);
 const closed=collapseHierarchy(state,[key(1)]);assert.deepEqual(closed.expanded,[[key(2)]]);assert.equal(closed.pages.length,4);
});
test('pagination removes only descendants of the changed group, preserving sibling pages',()=>{
 const state={pages:[page([]),page([key(1)]),page([key(1),key(3)]),page([key(2)])],expanded:[[key(1)],[key(1),key(3)],[key(2)]]};
 const changed=mergeHierarchyPage(state,page([key(1)],60));
 assert.ok(changed.pages.some(item=>item.path[0]===key(2)));
 assert.ok(!changed.pages.some(item=>item.path.length===2));
 assert.deepEqual(changed.expanded,[[key(1)],[key(2)]]);
});
test('cache is bounded and evicts older branch expansions, never requested ancestors',()=>{
 let state={pages:[page([])],expanded:[]};
 for(let i=1;i<80;i++){state=expandHierarchy(state,[key(i)]);state=mergeHierarchyPage(state,page([key(i)]));assert.ok(state.pages.length<=HIERARCHY_PAGE_LIMIT);}
 assert.ok(state.pages.some(item=>!item.path.length));assert.ok(state.pages.some(item=>item.path[0]===key(79)));
 assert.ok(!state.expanded.some(path=>path[0]===key(1)));assert.ok(state.expanded.length<HIERARCHY_PAGE_LIMIT);
});
test('snapshot restores exact expanded paths offsets and scroll without storing epoch payloads',()=>{
 const state={pages:[page([],60),page([key(1)],120)],expanded:[[key(1)]]};
 const saved=hierarchySnapshot(state,240,90);assert.equal(saved.hierarchy.scrollTop,240);assert.ok(!JSON.stringify(saved).includes('epochs'));
 const restored=hierarchyRestore(saved,'date,cell,block');assert.equal(restored.revision,revision);assert.deepEqual(restored.pages,[{path:[],offset:60},{path:[key(1)],offset:120}]);assert.deepEqual(restored.expanded,[[key(1)]]);assert.equal(restored.scrollTop,240);assert.equal(restored.scrollLeft,90);
 assert.equal(hierarchyRestore(saved,'cell,date'),null);
});
test('old column navigation restores its ancestry without widening scope',()=>{
 const saved={path:[key(1),key(2)],offset:60,revision,split_order:['date','cell','block'],scrollTop:5,columnPositions:[{offset:60},{offset:120}]};
 const restored=hierarchyRestore(saved,'date,cell,block');assert.deepEqual(restored.pages,[{path:[],offset:60},{path:[key(1)],offset:120},{path:[key(1),key(2)],offset:60}]);assert.deepEqual(restored.expanded,[[key(1)],[key(1),key(2)]]);
});

test('superseding a pending unloaded sibling collapses it instead of leaving an empty expansion',()=>{
 const state={pages:[page([])],expanded:[[key(1)],[key(2)]],loadingPath:[key(1)]};
 assert.deepEqual(cancelUnloadedExpansion(state,[key(2)]).expanded,[[key(2)]]);
 assert.deepEqual(cancelUnloadedExpansion({...state,pages:[...state.pages,page([key(1)])]},[key(2)]).expanded,state.expanded);
});
