import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const draft={id:'group',kind:'group',logic:'all',children:[]};
const catalog={key:'registry-0',data:{fields:[]},loading:false,error:null,supportsSummaries:false,reload(){}};

test('predicate catalog refresh preserves the editor node but gates every action until the current catalog arrives',async()=>{
 const h=await createWorkflowHarness();window.addEventListener=()=>{};window.removeEventListener=()=>{};try{
  const Dialog=await h.component('PredicateDialog');const props={draft,catalog,projectId:'project-A',onSearch(){throw Error('Submission must remain disabled');},onClose(){}};
  await h.mount(Dialog,props);
  const builder=h.root.findByType('fieldset');
  await h.render(Dialog,{...props,catalog:{...catalog,key:'registry-1',loading:true,data:null}});
  assert.equal(h.root.findByType('fieldset'),builder);
  const body=h.root.findByProps({className:'stable-content-body'});
  assert.equal(body.props.inert,'');assert.equal(body.props['aria-hidden'],true);
  const buttons=h.root.findAllByType('button');
  assert.equal(buttons.find(n=>n.children.includes('View matching epochs')).props.disabled,true);
  assert.equal(buttons.find(n=>n.children.includes('Preview matches')).props.disabled,true);
  await h.render(Dialog,{...props,catalog:{...catalog,key:'registry-1'}});
  assert.equal(h.root.findByType('fieldset'),builder);
  assert.equal(h.root.findByProps({className:'stable-content-body'}).props.inert,undefined);
 }finally{await h.close();}
});

test('predicate refresh errors remain visible and a different project cannot retain the prior editor',async()=>{
 const h=await createWorkflowHarness();window.addEventListener=()=>{};window.removeEventListener=()=>{};try{
  const Dialog=await h.component('PredicateDialog');const props={draft,catalog,projectId:'project-A',onSearch(){},onClose(){}};
  await h.mount(Dialog,props);
  await h.render(Dialog,{...props,catalog:{...catalog,key:'error',error:'Catalog read failed',data:null}});
  assert.ok(h.root.findAllByProps({role:'alert'}).length>0);
  assert.equal(h.root.findByProps({className:'stable-content-body'}).props.inert,'');
  await h.render(Dialog,{...props,projectId:'project-B',catalog:{...catalog,key:'new',data:null,loading:true}});
  assert.equal(h.root.findAllByType('fieldset').length,0);
 }finally{await h.close();}
});
