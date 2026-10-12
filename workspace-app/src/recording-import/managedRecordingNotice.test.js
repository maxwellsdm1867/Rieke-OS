import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from '../test-support/workflowHarness.js';

test('import history shows verified managed location and external-original guidance only on confirmed jobs',async()=>{
  const h=await createWorkflowHarness();
  const {default:History}=await h.module('recording-import/ui/ImportHistory.jsx');
  const storage={kind:'managed_library',path:'/Disco/recordings/checksum/example.h5',verified:true,original_removal_safe:true};
  const job={job_uuid:'managed',source:'example.h5',status:'complete',catalog_committed:true,recording_storage:storage};
  const text=()=>h.root.findAll(node=>node.type==='p').map(node=>node.children.filter(child=>typeof child==='string').join('')).join(' ');
  try{
    await h.mount(History,{jobs:[job]});
    assert.match(text(),/delete the original copy outside Disco/);
    assert.equal(h.root.findByType('code').children.join(''),storage.path);
    assert.equal(h.root.findAllByType('details')[0].props.open,true);
    await h.render(History,{jobs:[{...job,status:'interrupted',catalog_committed:null}]});
    assert.doesNotMatch(text(),/delete the original/);
    await h.render(History,{jobs:[{...job,recording_storage:{...storage,original_removal_safe:false}}]});
    assert.match(text(),/Keep this managed recording/);
    assert.doesNotMatch(text(),/delete the original/);
  }finally{await h.close();}
});
