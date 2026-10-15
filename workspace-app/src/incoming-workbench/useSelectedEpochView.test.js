import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {useSelectedEpochView} from './useSelectedEpochView.js';
import {frozenPresentationScope,frozenReadQuery} from '../epoch-browser/frozenReadContext.js';

const context={root:'/protocols/p/workbench/candidates/c',actor:'author',cohort_key:'sealed-cohort',
  candidate_scope_revision:'scope-1',expected_binding_version:1,selection_manifests:true};
const props={projectId:'project',protocolId:'p',context,filters:{},selected:['e1','e2']};
const receipt=body=>({selection_token:body.upload_uuid,count:body.offset+body.epoch_uuids.length,total:body.total,
  complete:true,candidate_scope_revision:body.candidate_scope_revision,query_revision:body.candidate_scope_revision,
  expected_binding_version:1,selection_sha256:createHash('sha256').update(JSON.stringify(body.epoch_uuids)).digest('hex')});
async function harness(){
  let root,value;const calls=[];
  const request=(path,options)=>new Promise((resolve,reject)=>calls.push({path,...options,resolve:()=>resolve(receipt(options.body)),reject}));
  function Holder(next){value=useSelectedEpochView({...next,request});return null;}
  const render=async next=>act(async()=>{const element=React.createElement(Holder,next);if(root)root.update(element);else root=TestRenderer.create(element);});
  return {calls,get value(){return value;},render,async toggle(){await act(()=>value.toggle());},
    async waitCalls(count){for(let i=0;i<50&&calls.length<count;i++)await act(()=>new Promise(resolve=>setTimeout(resolve,5)));assert.equal(calls.length,count);},
    async resolve(index){await act(()=>calls[index].resolve());},async reject(index){await act(()=>calls[index].reject(Error('fixture offline')));},
    async close(){await act(()=>root?.unmount());}};
}

test('selected view survives pause and renews its exact manifest before reads resume',async()=>{
  const h=await harness();try{
    await h.render(props);await h.toggle();await h.waitCalls(1);assert.equal(h.value.pending,true);
    assert.deepEqual(h.calls[0].body.epoch_uuids,props.selected);await h.resolve(0);
    const before=h.value.context,scope=frozenPresentationScope(before,'p',frozenReadQuery(before));
    assert.equal(h.value.selected,true);assert.equal(h.value.pending,false);
    await h.render({...props,paused:true});assert.equal(h.value.selected,true);assert.equal(h.value.pending,true);assert.equal(h.calls.length,1);
    const next={...props,context:{...context,candidate_scope_revision:'scope-2'}};
    await h.render(next);await h.waitCalls(2);
    assert.equal(h.value.context.selection_token,before.selection_token);
    assert.equal(h.value.context.candidate_scope_revision,'scope-1','old token remains paired with its old, inert scope');
    assert.equal(h.calls[1].body.candidate_scope_revision,'scope-2');assert.deepEqual(h.calls[1].body.epoch_uuids,props.selected);
    await h.resolve(1);assert.equal(h.value.pending,false);
    assert.notEqual(h.value.context.selection_token,before.selection_token);
    assert.equal(h.value.context.candidate_scope_revision,'scope-2');
    assert.equal(frozenPresentationScope(h.value.context,'p',frozenReadQuery(h.value.context)),scope,'new token does not reset expansion/scroll');
  }finally{await h.close();}
});

test('failed renewal retains selected intent and offers an explicit retry or return to all',async()=>{
  const h=await harness();try{
    await h.render(props);await h.toggle();await h.waitCalls(1);await h.resolve(0);const token=h.value.context.selection_token;
    await h.render({...props,context:{...context,candidate_scope_revision:'scope-2'}});await h.waitCalls(2);await h.reject(1);
    assert.equal(h.value.selected,true);assert.equal(h.value.pending,true);assert.equal(h.value.context.selection_token,token);assert.match(h.value.error,/offline/);
    await act(()=>h.value.retry());await h.waitCalls(3);await h.resolve(2);assert.equal(h.value.pending,false);assert.equal(h.value.error,null);
    await h.render({...props,paused:true});await h.toggle();assert.equal(h.value.selected,false);assert.equal(h.value.pending,false);
  }finally{await h.close();}
});

for(const boundary of ['project','actor','cohort','filter','selection'])test(`late selected-view completion cannot cross ${boundary} or A-B-A`,async()=>{
  const h=await harness();try{
    await h.render(props);await h.toggle();await h.waitCalls(1);
    const changes={project:{projectId:'other'},actor:{context:{...context,actor:'other'}},cohort:{context:{...context,cohort_key:'other'}},filter:{filters:{cell_type:'ON'}},selection:{selected:['e3']}};
    await h.render({...props,...changes[boundary]});assert.equal(h.value.selected,false);assert.equal(h.calls[0].signal.aborted,true);
    await h.render(props);await h.resolve(0);assert.equal(h.value.selected,false);assert.equal(h.value.context.selection_token,undefined);
  }finally{await h.close();}
});

test('a pause aborts a pending upload; its late response cannot satisfy the resumed request',async()=>{
  const h=await harness();try{
    await h.render(props);await h.toggle();await h.waitCalls(1);
    await h.render({...props,paused:true});assert.equal(h.calls[0].signal.aborted,true);
    await h.render(props);await h.waitCalls(2);await h.resolve(0);assert.equal(h.value.pending,true);
    await h.resolve(1);assert.equal(h.value.pending,false);assert.equal(h.value.context.selection_token,h.calls[1].body.upload_uuid);
  }finally{await h.close();}
});

test('legacy selected filters retain intent through pauses without inventing manifest capability',async()=>{
  const h=await harness();try{
    const legacy={...props,context:{...context,selection_manifests:false}};
    await h.render(legacy);await h.toggle();const filters=h.value.filters;
    await h.render({...legacy,paused:true});assert.equal(h.value.selected,true);assert.deepEqual(h.value.filters,filters);assert.equal(h.calls.length,0);
  }finally{await h.close();}
});
