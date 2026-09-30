import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';
import {deferred} from './test-support/pagedTreeHarness.js';
const props={protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',expected_binding_version:2,cells:[]},filters:{},revision:0,initialEpochUuid:'epoch-A'};
const receipt=body=>({protocol_uuid:'protocol-A',query_revision:body.query_revision,expected_binding_version:body.expected_binding_version,epochs:body.epoch_uuids.map(epoch_uuid=>({epoch_uuid,cell_uuid:'cell-A',curation_revision:0}))});
function errorText(element){
  if(!element||typeof element!=='object')return '';
  if(element.props?.role==='alert')return element.props.children.filter(child=>typeof child==='string').join('');
  const children=element.props?.children;return (Array.isArray(children)?children:[children]).map(errorText).join('');
}

test('mounted Inspector saves 1,000 exact selected epochs in two calls and clears only the successful draft',async()=>{
  const h=await createInspectorHarness(),calls=[];let changed=0;
  h.fixture.api=async(path,options)=>{calls.push({path,...options});return path.endsWith('/read')?receipt(options.body):{saved:true};};
  try{
    await h.render({...props,onChange:()=>changed++});
    const selected=Array.from({length:1000},(_,i)=>`epoch-${i}`);
    await h.act(()=>h.viewer.treePane.listProps.setTargets(selected));
    await h.act(()=>h.tags.onValue('keep draft'));
    await h.act(()=>h.tags.onAdd('keep draft'));
    assert.equal(calls.length,2);assert.deepEqual(calls[1].body.epoch_uuids,selected);
    assert.equal(changed,1);assert.equal(h.tags.value,'');assert.equal(h.tags.busy,false);
  }finally{await h.close();}
});

test('mounted Inspector retains draft and blocks save when selection or scope changes during read',async()=>{
  for(const change of ['selection','filter','query','binding','revision']){
    const h=await createInspectorHarness(),pending=deferred(),calls=[];let changed=0;
    h.fixture.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
    const initial={...props,onChange:()=>changed++};
    try{
      await h.render(initial);await h.act(()=>h.tags.onValue('retained'));let work;
      await h.act(()=>{work=h.tags.onAdd('retained');});
      if(change==='selection')await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-B']));
      else await h.render({...initial,...(change==='filter'?{filters:{cell_type:'other'}}:change==='revision'?{revision:1}:{protocol:{...initial.protocol,...(change==='query'?{query_revision:'query-B'}:{expected_binding_version:3})}})});
      assert.equal(calls[0].signal.aborted,true,change);
      await h.act(async()=>{pending.resolve(receipt(calls[0].body));await work;});
      assert.equal(calls.length,1,change);assert.equal(changed,0);
      if(change==='filter'){
        // Filter changes intentionally clear focus/selection without remounting
        // Inspector. Its draft must still be present after an explicit refocus.
        assert.equal(h.viewer.epoch,null);
        await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-A',h.fixture.epoch));
      }
      assert.equal(h.tags.value,'retained');
      assert.match(errorText(h.viewer.before),/Selection or dataset changed/);assert.equal(h.tags.busy,false);
    }finally{await h.close();}
  }
});

test('mounted Inspector keeps the draft after an optimistic save conflict and does not retry',async()=>{
  const h=await createInspectorHarness(),calls=[];
  h.fixture.api=async(path,options)=>{calls.push({path,...options});if(path.endsWith('/read'))return receipt(options.body);throw Error('Revision conflict');};
  try{
    await h.render(props);await h.act(()=>h.tags.onValue('retained'));
    await h.act(()=>h.tags.onAdd('retained'));
    assert.equal(calls.length,2);assert.equal(h.tags.value,'retained');assert.equal(h.tags.busy,false);
    assert.match(errorText(h.viewer.before),/Revision conflict/);
  }finally{await h.close();}
});

test('a retained old Inspector action cannot save a previous scope',async()=>{
  const h=await createInspectorHarness();let calls=0;
  h.fixture.api=()=>{calls++;throw Error('Must not request');};
  try{
    await h.render(props);const oldAdd=h.tags.onAdd;
    await h.render({...props,revision:1});
    await h.act(()=>oldAdd('retained'));
    assert.equal(calls,0);assert.match(errorText(h.viewer.before),/Selection or dataset changed/);
  }finally{await h.close();}
});

test('same-scope rerender permits completion; saving never replays after later navigation',async()=>{
  const h=await createInspectorHarness(),read=deferred(),save=deferred(),calls=[];let changed=0;
  h.fixture.api=(path,options)=>{calls.push({path,...options});return path.endsWith('/read')?read.promise:save.promise;};
  const initial={...props,onChange:()=>changed++};
  try{
    await h.render(initial);await h.act(()=>h.tags.onValue('original'));let work;
    await h.act(()=>{work=h.tags.onAdd('original');});
    await h.render({...initial,filters:{}});
    await h.act(()=>{read.resolve(receipt(calls[0].body));});
    assert.equal(calls.length,2);assert.equal(calls[1].signal,undefined);
    await h.render({...initial,revision:1});
    await h.act(()=>h.tags.onValue('new draft'));
    await h.act(async()=>{save.resolve({saved:true});await work;});
    assert.equal(calls.length,2);assert.equal(changed,1);assert.equal(h.tags.value,'new draft');
  }finally{await h.close();}
});
