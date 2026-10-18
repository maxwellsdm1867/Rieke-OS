import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const editor=h=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag 2 selected epochs');
const props={epoch:{epoch_uuid:'epoch-0',cell_uuid:'cell-0',annotations:{cell_tags:[],epoch_tags:[],revisions:{cell:{},epoch:{}}}},selectedEpochs:['epoch-0','epoch-1'],targetScope:'selected',revision:0};
test('viewer-owned unsaved tag drafts survive remount and remain isolated by exact target identity',async()=>{
 const h=await createWorkflowHarness(),values={};
 try{
  const Tags=await h.component('AnnotationTags'),composer={values,onChange:(key,value)=>{if(value)values[key]=value;else delete values[key];}};
  const a={...props,composer,targetScope:'epoch',selectedEpochs:[]};
  const input=()=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag this epoch');
  await h.mount(Tags,a);await h.waitFor(()=>input()&&!input().props.disabled);
  await h.act(()=>input().props.onChange({target:{value:'unfinished A'}}));await h.render(Tags,a);
  assert.equal(input().props.value,'unfinished A');await h.render(()=>null,{});await h.render(Tags,a);assert.equal(input().props.value,'unfinished A');
  const b={...a,epoch:{...props.epoch,epoch_uuid:'epoch-2'}};await h.render(Tags,b);assert.equal(input().props.value,'');
  await h.act(()=>input().props.onChange({target:{value:'unfinished B'}}));await h.render(Tags,b);assert.equal(input().props.value,'unfinished B');
  await h.render(Tags,a);assert.equal(input().props.value,'unfinished A');assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations').length,0);
 }finally{await h.close();}
});
async function save(h){
  await h.waitFor(()=>editor(h)&&!editor(h).props.disabled);
  await h.act(()=>editor(h).props.onChange({target:{value:'group tag'}}));
  await h.act(()=>editor(h).parent.props.onSubmit({preventDefault(){}}));
}
test('stale group verification after native per-target read preserves draft and submits no write',async()=>{
  const h=await createWorkflowHarness();
  try{
    const Tags=await h.component('AnnotationTags');let verified=0;
    await h.mount(Tags,{...props,verifyTarget:async()=>{verified++;throw Error('Tree changed. Reopen group.');}});await save(h);
    await h.waitFor(()=>verified===1&&!editor(h).props.disabled);
    assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations/read').length,1);
    assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations').length,0);assert.equal(editor(h).props.value,'group tag');
  }finally{await h.close();}
});
test('scope change cancels delayed group verification before durable submit',async()=>{
  const h=await createWorkflowHarness();
  try{
    const Tags=await h.component('AnnotationTags');let release,signal;
    const verifyTarget=({signal:current})=>{signal=current;return new Promise(resolve=>{release=resolve;});};
    await h.mount(Tags,{...props,verifyTarget});await save(h);await h.waitFor(()=>release);
    await h.render(Tags,{...props,revision:1,selectedEpochs:['epoch-2','epoch-3'],verifyTarget});
    await h.act(async()=>release());assert.equal(signal.aborted,true);assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations').length,0);
  }finally{await h.close();}
});
test('successful group verification retains exact initial IDs and native per-actor revision body',async()=>{
  const h=await createWorkflowHarness();
  try{
    const Tags=await h.component('AnnotationTags');let confirmed;
    await h.mount(Tags,{...props,reconcileReceipt:true,verifyTarget:async()=>{},onChange:(_,receipt)=>{confirmed=receipt;}});await save(h);await h.waitFor(()=>confirmed);
    const write=h.fixture.requests.find(row=>row.path==='/annotations');assert.deepEqual(write.body.target_uuids,['epoch-0','epoch-1']);assert.deepEqual(write.body.expected_revisions,{'epoch-0':0,'epoch-1':0});assert.equal(write.body.profile_uuid,'author');assert.equal(confirmed.targets.length,2);
  }finally{await h.close();}
});

test('query group composer submits compact server operation for all 1857 without explicit-target reads',async()=>{
 const h=await createWorkflowHarness();
 try{
  const Tags=await h.component('AnnotationTags');const submitted=[];let changed;
  const groupMutation={selectionUuid:'selection',count:1857,profileUuid:'author',save:async body=>{submitted.push(body);return {changed:1857};}};
  await h.mount(Tags,{...props,selectedEpochs:[],groupMutation,onChange:(result,confirmed)=>{changed={result,confirmed};}});
  const input=()=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag 1,857 selected epochs');
  await h.waitFor(()=>input()&&!input().props.disabled);
  await h.act(()=>input().props.onChange({target:{value:'group tag'}}));
  await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));await h.waitFor(()=>changed);
  assert.deepEqual(submitted,[{tag:'group tag',profileUuid:'author'}]);assert.equal(changed.confirmed,null);
  assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations/read'||row.path==='/annotations').length,0);
 }finally{await h.close();}
});


test('dismissed query composer still publishes a submitted durable receipt',async()=>{
 const h=await createWorkflowHarness();
 try{
  const Tags=await h.component('AnnotationTags');await h.component('TreeGroupTags');let release,changed;
  const groupMutation={selectionUuid:'selection',count:1857,profileUuid:'author',save:()=>new Promise(resolve=>{release=resolve;})};
  await h.mount(Tags,{...props,selectedEpochs:[],groupMutation,onChange:result=>{changed=result;}});
  const input=()=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag 1,857 selected epochs');
  await h.waitFor(()=>input()&&!input().props.disabled);
  await h.act(()=>input().props.onChange({target:{value:'submitted'}}));
  await h.act(()=>input().parent.props.onSubmit({preventDefault(){}}));await h.waitFor(()=>release);
  await h.render(()=>null,{});await h.act(()=>release({changed:1857}));
  assert.equal(changed.changed,1857);
 }finally{await h.close();}
});

test('multi-selection tags show pending on every selected epoch before the write returns, then confirm',async()=>{
  const h=await createWorkflowHarness();
  try{
    const Tags=await h.component('AnnotationTags'),{tagStore}=await h.module('annotations/tagStore.js');
    let hold=300;h.fixture.delay=record=>record.path==='/annotations'?hold:0;
    await h.mount(Tags,{...props,reconcileReceipt:true});
    await h.waitFor(()=>editor(h)&&!editor(h).props.disabled);
    await h.act(()=>editor(h).props.onChange({target:{value:'group tag'}}));
    await h.act(()=>editor(h).parent.props.onSubmit({preventDefault(){}}));
    for(const id of ['epoch-0','epoch-1'])assert.deepEqual(tagStore.read('epoch',id).pending.map(op=>op.tag),['group tag'],'Shown before the write returns');
    await h.waitFor(()=>['epoch-0','epoch-1'].every(id=>!tagStore.read('epoch',id).pending.length));
    for(const id of ['epoch-0','epoch-1'])assert.deepEqual(tagStore.read('epoch',id).confirmed.tags.map(chip=>chip.tag),['group tag']);
    assert.equal(h.fixture.requests.filter(row=>row.path==='/annotations').length,1);
  }finally{await h.close();}
});

test('group and confirmed epoch receipts do not tick the app clock; other annotation changes do',async()=>{
  const h=await createWorkflowHarness();
  try{
    const {useWorkspaceChanges}=await h.module('useWorkspaceChanges.js'),React=await import('react');let api;
    const Probe=()=>{api=useWorkspaceChanges();return null;};
    await h.mount(Probe,{});
    const receipt={version:1,targets:[{target_kind:'epoch',target_uuid:'epoch-0',revisions:{me:1},tags:[]}]};
    await h.act(()=>api.changed({kind:'annotations',tagChannel:true}));
    await h.act(()=>api.changed({kind:'annotations',confirmed:receipt}));
    assert.equal(api.revision,0);
    await h.act(()=>api.changed({kind:'annotations'}));
    assert.equal(api.revision,1);assert.equal(api.structureRevision,0);
    void React;
  }finally{await h.close();}
});

test('ghost completion shows the rest of an existing tag in grey; Tab accepts it without saving or navigating',async()=>{
  const h=await createWorkflowHarness();
  try{
    h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/annotation-tags'?{tags:[{tag:'branch-stim',count:4},{tag:'bright',count:1}],has_more:false}:fallback();
    const Tags=await h.component('AnnotationTags'),navigated=[];
    const single={...props,targetScope:'epoch',selectedEpochs:[],reconcileReceipt:true,onNavigateEpoch:direction=>navigated.push(direction)};
    const input=()=>h.root.findAllByType('input').find(row=>row.props['aria-label']==='Tag this epoch');
    await h.mount(Tags,single);await h.waitFor(()=>input()&&!input().props.disabled);
    await h.act(()=>input().props.onFocus());
    await h.waitFor(()=>h.fixture.requests.some(row=>row.path.startsWith('/annotation-tags')));await h.settle(20);
    const before=h.fixture.requests.length;
    await h.act(()=>input().props.onChange({target:{value:'bra'},nativeEvent:{}}));
    const ghost=h.root.findByProps({className:'tag-input-ghost'});
    assert.equal(ghost.children.at(-1),'nch-stim','Grey remainder of the most used match');
    assert.equal(input().props.value,'bra','The value stays as typed');
    const options=h.root.findAllByProps({role:'option'}).length;assert.equal(options,1);
    let prevented=false;
    await h.act(()=>input().props.onKeyDown({key:'Tab',shiftKey:false,currentTarget:{selectionStart:3,selectionEnd:3},preventDefault(){prevented=true;},stopPropagation(){}}));
    assert.equal(prevented,true);assert.equal(input().props.value,'branch-stim');
    assert.deepEqual(navigated,[]);
    assert.equal(h.fixture.requests.slice(before).length,0,'Suggestions and completion are local');
  }finally{await h.close();}
});
