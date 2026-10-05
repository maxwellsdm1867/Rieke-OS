import test from 'node:test';
import assert from 'node:assert/strict';
import {epochListScrollTop,revealEpochRow} from './epochListScroll.js';
test('visible epoch rows do not move the list',()=>{
 assert.equal(epochListScrollTop({scrollTop:250,height:500,rowTop:180,rowBottom:210}),250);
});
test('hidden rows are revealed within the list below its sticky cell heading',()=>{
 assert.equal(epochListScrollTop({scrollTop:250,height:500,rowTop:20,rowBottom:50}),234);
 assert.equal(epochListScrollTop({scrollTop:250,height:500,rowTop:490,rowBottom:520}),270);
 assert.equal(epochListScrollTop({scrollTop:0,height:500,rowTop:0,rowBottom:30}),0);
});
test('revealing an epoch only changes its containing list scroll position',()=>{
 const container={scrollTop:250,clientHeight:500,getBoundingClientRect:()=>({top:100}),
  querySelector:()=>({getBoundingClientRect:()=>({top:590,bottom:620}),scrollIntoView:()=>assert.fail('Must not scroll workspace ancestors')})};
 revealEpochRow(container);
 assert.equal(container.scrollTop,270);
 revealEpochRow(null);
});

test('tree reveal adjusts only the chosen scroll axes, never an ancestor',async()=>{
 const {revealWithin}=await import('./epochListScroll.js');
 const container={scrollTop:100,scrollLeft:40,clientHeight:300,clientWidth:250,getBoundingClientRect:()=>({top:100,left:80})};
 const node={getBoundingClientRect:()=>({top:420,bottom:450,left:370,right:400}),scrollIntoView:()=>assert.fail('No ancestor scrolling')};
 revealWithin(container,node);
 assert.equal(container.scrollTop,150);assert.equal(container.scrollLeft,40);
 revealWithin(container,node,{horizontal:true,vertical:false});
 assert.equal(container.scrollTop,150);assert.equal(container.scrollLeft,110);
});
