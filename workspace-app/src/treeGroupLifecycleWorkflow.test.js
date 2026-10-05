import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const find=(h,label)=>h.root.findAllByType('button').find(row=>row.props['aria-label']===label||row.children.join('')===label);
async function openSaveClose(h){
 await h.act(()=>find(h,'Open group').props.onClick({preventDefault(){},stopPropagation(){},currentTarget:{isConnected:true,focus(){}}}));
 const editor=()=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag 1,857 selected epochs');
 await h.waitFor(()=>editor()&&!editor().props.disabled);
 await h.act(()=>editor().props.onChange({target:{value:'QA group'}}));
 await h.act(()=>editor().parent.props.onSubmit({preventDefault(){}}));
 await h.act(()=>find(h,'Close group tags').props.onClick());
}
function setup(h){
 let selected=true,release,first=true;const writes=[];
 h.fixture.respond=(url,options,fallback)=>{
  const route=url.pathname.replace('/api',''),body=options.body&&JSON.parse(options.body);
  if(route==='/annotations/group-preview')return {selection_uuid:'selection',profile_uuid:'author',count:1857,target_kind:'epoch',tree_revision:'a'.repeat(64)};
  if(route==='/annotations/group-preview-release'){selected=false;return {released:true};}
  if(route==='/annotations/group'){
   writes.push(body);
   const receipt=()=>({format:'rieke-group-annotation-receipt',version:1,action:'add',target_kind:'epoch',operation_uuid:body.operation_uuid,profile_uuid:'author',tag:'QA group',target_count:1857,changed:1857,unchanged:0,undo:{kind:'annotation_group',operation_uuid:body.operation_uuid,count:1857}});
   if(first){first=false;return new Promise(resolve=>{release=mode=>resolve(mode==='507'?{failure:507,saved:true,error:'SQL committed, recovery unconfirmed'}:selected?receipt():{failure:400,error:'selection missing'});});}
   return {...receipt(),replayed:true};
  }
  return fallback();
 };
 return {writes,release:mode=>release(mode),selected:()=>selected,ready:()=>!!release};
}
test('real tree hook and composer dismissal cannot release before apply captures selection',async()=>{
 const h=await createWorkflowHarness({portals:true,enableUndo:true});
 try{
  const Component=(await h.module('test-support/TreeGroupLifecycleHarness.jsx')).default,fixture=setup(h),changes=[];
  await h.mount(Component,{onChange:value=>changes.push(value)});await openSaveClose(h);await h.waitFor(fixture.ready);
  assert.equal(fixture.selected(),true);assert.equal(h.fixture.requests.filter(row=>row.path.endsWith('group-preview-release')).length,0);
  await h.act(()=>fixture.release('success'));await h.waitFor(()=>changes.length===1);
  await h.waitFor(()=>!fixture.selected());assert.equal(changes[0].changed,1857);assert.equal(fixture.writes.length,1);
 }finally{await h.close();}
});
test('dismissed committed507 refreshes globally and visible recovery replays exact operation once',async()=>{
 const h=await createWorkflowHarness({portals:true,enableUndo:true});
 try{
  const Component=(await h.module('test-support/TreeGroupLifecycleHarness.jsx')).default,fixture=setup(h),changes=[];
  await h.mount(Component,{onChange:value=>changes.push(value)});await openSaveClose(h);await h.waitFor(fixture.ready);
  await h.act(()=>fixture.release('507'));await h.waitFor(()=>changes.length===1&&find(h,'Retry original group save')&&!find(h,'Retry original group save').props.disabled);
  assert.equal(changes[0].kind,'annotations');assert.equal(fixture.selected(),true);
  const recovery=(await h.module('group-save/groupAnnotationRecovery.js')).groupAnnotationRecovery;
  assert.equal(recovery.view()[0].status,'unconfirmed');
  await h.act(()=>find(h,'Retry original group save').props.onClick());await h.waitFor(()=>changes.length===2&&recovery.view().length===0);
  assert.deepEqual(fixture.writes[0],fixture.writes[1]);assert.equal(fixture.writes.length,2);
  const history=(await h.module("undo/mutationUndo.js")).mutationUndo;
  assert.equal(history.view().count,1);assert.equal(changes[1].kind,'annotations');
 }finally{await h.close();}
});
