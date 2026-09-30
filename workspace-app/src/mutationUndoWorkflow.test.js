import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
const input=h=>h.root.findByProps({'aria-label':'Tag this epoch'});
const ready=h=>h.waitFor(()=>{try{return !!h.viewer.epoch&&!input(h).props.disabled;}catch{return false;}});

test('mounted committed tag undo survives epoch navigation and adds no ordinary edit requests',async()=>{
 const h=await createWorkflowHarness({total:40,enableUndo:true});
 try{
  h.fixture.respond=(url,options,fallback)=>{
   const body=options.body?JSON.parse(options.body):{};
   if(url.pathname==='/api/annotations'){
    const result=fallback();
    if(options.headers['X-Rieke-Undo-Receipt']==='1')result.undo={kind:'annotations',operations:body.target_uuids.map(target_uuid=>({target_uuid,target_kind:body.target_kind,profile_uuid:body.profile_uuid,expected_revision:body.expected_revisions[target_uuid]+1,before_revision:body.expected_revisions[target_uuid],tags_remove:body.tags_add,tags_add:body.tags_remove}))};
    return result;
   }
   if(url.pathname==='/api/annotations/undo'){
    const row=body.operations[0];assert.equal(row.target_uuid,'epoch-0');assert.equal(row.expected_revision,1);
    h.fixture.annotations.set(row.target_uuid,[]);h.fixture.annotationVersions.set(`epoch:${row.target_uuid}`,2);h.fixture.generation++;
    return {changed:1,annotations:[{...row,revision:2,tags:[],author_name:'Scientist'}]};
   }
   return fallback();
  };
  await h.mount();await ready(h);const before=h.fixture.requests.length;
  await h.act(()=>input(h).props.onChange({target:{value:'fresh tag'}}));
  await h.act(()=>input(h).parent.props.onSubmit({preventDefault(){}}));await ready(h);
  assert.equal(h.fixture.requests.slice(before).filter(row=>row.path==='/annotations').length,1);
  assert.equal(h.fixture.requests.slice(before).filter(row=>row.path==='/annotations/read').length,0);
  assert.equal(input(h).props['data-saved-undo'],'true');
  // Navigate to another original epoch before pressing Undo.
  await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-2'));
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-2');
  assert.equal(input(h).props['data-saved-undo'],'true','A clean composer after epoch navigation must still hand off committed undo');
  const undo=h.root.findAllByType('button').find(row=>row.children.includes('Undo edit'));
  assert.equal(undo.props.disabled,false);await h.act(()=>undo.props.onClick());
  await h.waitFor(()=>h.fixture.requests.some(row=>row.path==='/annotations/undo'));
  await ready(h);
  assert.deepEqual(h.fixture.annotations.get('epoch-0'),[]);
  assert.equal(h.viewer.epoch.epoch_uuid,'epoch-2');
 }finally{await h.close();}
});
