import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';

test('Inspector requests focus immediately for rows, buttons, repeated keys and page boundaries',async()=>{
 const h=await createInspectorHarness();
 const cells=[{cell_uuid:'cell-A',label:'Cell A',epochs:62,date:'2026-10-05'}];
 const epoch=index=>({epoch_uuid:`epoch-${index}`,cell_uuid:'cell-A',streams:[],curation:{included:true,tags:[]}});
 const protocol={definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',expected_binding_version:2,cells};
 h.fixture.resource=path=>{
  const result={path,loading:false,error:null,reload(){}};
  if(path?.includes('/epochs?')){
   const offset=Number(new URL(path,'http://fixture').searchParams.get('offset')||0);
   result.data={offset,total:62,epochs:Array.from({length:Math.min(60,62-offset)},(_,i)=>epoch(offset+i)),cells,query_revision:'query-A',expected_binding_version:2};
  }else if(path?.startsWith('/epochs/'))result.data=epoch(Number(path.match(/epoch-(\d+)/)[1]));
  else result.data={fields:[]};
  return result;
 };
 const focused=index=>{
  assert.equal(h.viewer.treePane.listProps.focused,`epoch-${index}`,'highlight follows intent without awaiting metadata');
  const read=h.fixture.resources.findLast(item=>item.path?.startsWith('/epochs/'));
  assert.match(read.path,new RegExp(`/epoch-${index}\\?`));assert.equal(read.delayMs,0);
 };
 try{
  await h.render({protocol,filters:{},revision:0,initialEpochUuid:'epoch-0'});focused(0);
  await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-3',epoch(3)));focused(3);
  await h.act(()=>h.viewer.navigation.onMove(1));focused(4);
  await h.act(()=>h.viewer.navigation.onMove(-1));focused(3);
  const target={closest:()=>null,hasAttribute:()=>true,focus(){}};
  for(let index=4;index<14;index++){
   await h.act(()=>h.viewer.onKeyDown({key:'s',repeat:true,target,currentTarget:target,preventDefault(){},stopPropagation(){}}));focused(index);
  }
  await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-59',epoch(59)));focused(59);
  await h.act(()=>h.viewer.onKeyDown({key:'ArrowDown',repeat:true,target,currentTarget:target,preventDefault(){},stopPropagation(){}}));focused(60);
  assert.equal(h.viewer.navigation.position,60);
  await h.act(()=>{const keys=h.viewer.onKeyDown;for(let i=0;i<10;i++)keys({key:'ArrowUp',repeat:true,target,currentTarget:target,preventDefault(){},stopPropagation(){}});});focused(50);
  assert.equal(h.viewer.navigation.position,50);
 }finally{await h.close();}
});
