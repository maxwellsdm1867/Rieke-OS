import test from 'node:test';
import assert from 'node:assert/strict';
import {epochIncluded,incomingReviewDecision} from './incoming-workbench/incomingReviewDecision.js';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const root='/protocols/protocol-A/workbench/candidates/revision-A';
const context={root,candidate_scope_revision:'candidate-a'};
const decision=(reviewed=false,excluded=false)=>({selected:true,reviewed,excluded});

test('incoming decisions stay separate from scientific curation and missing decisions are unavailable',()=>{
 const epoch={epoch_uuid:'epoch-0',curation:{included:true,review_state:'unreviewed',revision:0},review_decision:decision(true,true)};
 const before=structuredClone(epoch);
 assert.equal(epochIncluded(epoch,true),false);assert.equal(epochIncluded(epoch),true);assert.equal(incomingReviewDecision(epoch).reviewed,true);
 assert.deepEqual(epoch,before);
 for(const invalid of [undefined,{},decision('yes',false),{...decision(),valid:false}]){
  assert.equal(epochIncluded({...epoch,review_decision:invalid},true),null);
  assert.equal(epochIncluded({...epoch,review_decision:invalid}),true);
 }
});

function incomingFixture(h,state){
 h.fixture.respond=(url,options,fallback)=>{
  if(!url.pathname.startsWith('/api'+root))return fallback();
  assert.equal(url.searchParams.get('candidate_scope_revision'),context.candidate_scope_revision);
  const suffix=url.pathname.slice(('/api'+root).length);
  url.pathname=suffix.startsWith('/epochs/epoch-')?'/api'+suffix:'/api/protocols/protocol-A'+suffix;
  const value=fallback();
  const decorate=epoch=>({...epoch,curation:{...epoch.curation,included:true,review_state:'unreviewed',revision:0},review_decision:{...state}});
  return value.epochs?{...value,epochs:value.epochs.map(decorate)}:value.epoch_uuid?decorate(value):value;
 };
}
const props={protocol:{definition:{protocol_uuid:'protocol-A',name:'Frozen candidate'},counts:{epochs:10},cells:[]},projectId:'project',filters:{},revision:0,readContext:context,initialEpochUuid:'epoch-0',onChange(){}};
const reviewButton=h=>h.root.findAllByType('button').find(node=>node.children.some(child=>typeof child==='string'&&(child==='Mark incoming epoch reviewed'||child==='Clear incoming epoch review marker')));
const text=h=>h.root.findByProps({className:'optional-review incoming-epoch-review'}).findByType('summary').children.join('');

test('candidate save/reopen displays persisted proposal review and exclusion without changing main curation',async()=>{
 let saved=decision();const writes=[];
 for(const reopen of [false,true]){
  const h=await createWorkflowHarness({total:10});incomingFixture(h,saved);
  try{
   const Inspector=await h.component('Inspector');
   const currentProps={...props,revision:reopen?2:0,onReviewDecision:async body=>{writes.push(body);saved={...saved,...(typeof body.changes.reviewed==='boolean'?{reviewed:body.changes.reviewed}:{}),...(typeof body.changes.included==='boolean'?{excluded:!body.changes.included}:{})};}};
   await h.mount(Inspector,currentProps);await h.waitFor(()=>!!h.viewer.epoch&&!h.viewer.treePane.listProps.disabled);
   assert.equal(h.viewer.epoch.curation.review_state,'unreviewed');assert.equal(h.viewer.epoch.curation.included,true);
   if(!reopen){
    assert.match(text(h),/Not marked/);
    await h.act(()=>reviewButton(h).props.onClick());
    assert.deepEqual(writes.at(-1).changes,{reviewed:true});
    incomingFixture(h,saved);await h.render(Inspector,{...currentProps,revision:1});
    await h.waitFor(()=>h.viewer.epoch?.review_decision.reviewed===true&&!h.viewer.treePane.listProps.disabled);
    assert.match(text(h),/Reviewed/);
    await h.act(()=>h.viewer.inclusion.onToggle(h.viewer.epoch,false));
    assert.deepEqual(writes.at(-1).changes,{included:false});assert.equal(saved.excluded,true);
   }else{
    assert.match(text(h),/Reviewed/);assert.equal(h.viewer.epoch.review_decision.excluded,true);
    assert.equal(epochIncluded(h.viewer.epoch,h.viewer.inclusion.incoming),false);
    assert.equal(h.viewer.epoch.curation.included,true);assert.equal(h.viewer.epoch.curation.review_state,'unreviewed');
    assert.equal(h.viewer.epoch.curation.revision,0);
    assert.equal(h.fixture.requests.some(row=>row.path.includes('/curation')),false);
   }
  }finally{await h.close();}
 }
});

test('candidate detail with missing proposal receipt exposes no review action',async()=>{
 const h=await createWorkflowHarness({total:10});
 try{
  incomingFixture(h,decision());const respond=h.fixture.respond;
  h.fixture.respond=(...args)=>{const value=respond(...args);if(value.epoch_uuid)delete value.review_decision;return value;};
  const Inspector=await h.component('Inspector');await h.mount(Inspector,{...props,onReviewDecision:()=>{throw Error('Must not write');}});
  await h.waitFor(()=>!!h.viewer.epoch&&!h.viewer.treePane.listProps.disabled);
  assert.equal(reviewButton(h),undefined);assert.equal(epochIncluded(h.viewer.epoch,true),null);
  assert.equal(h.viewer.epoch.curation.included,true);
 }finally{await h.close();}
});
