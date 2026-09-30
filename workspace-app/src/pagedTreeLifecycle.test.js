import test from 'node:test';
import assert from 'node:assert/strict';
import {createPagedTreeHarness,deferred,scopeA,pageAt,startSelection,selectionRaceCases} from './test-support/pagedTreeHarness.js';

test('mounted tree cancels old cell/range requests on every source scope change and retains same-scope results',async()=>{
  for(const result of await selectionRaceCases())for(const assertion of result.assertions)assert.ok(assertion.passed,`${result.kind}:${result.change}: ${assertion.name}`);
});

test('mounted selection generation prevents A → B → A resurrection and ignores stale errors',async()=>{
  const h=await createPagedTreeHarness(),pending=deferred(),published=[];let signal;
  h.network.api=(_path,options)=>{signal=options.signal;return pending.promise;};
  const props={...scopeA,onSelectCell:(...args)=>published.push(args)};
  try{
    await h.render(props);const {work}=await startSelection(h,'cell');
    const oldHandler=h.tree.onSelectBranch;
    await h.render({...props,filters:{tag:'B'}});
    // Retained handlers cannot start an old-scope request after the commit.
    await h.act(()=>oldHandler({value:'cell-A',path:[]},{field:'cell'},'old-revision'));
    await h.render(props);assert.equal(signal.aborted,true);
    await h.act(async()=>{pending.reject(new Error('Old scope failed'));await work;});
    assert.deepEqual(published,[]);assert.deepEqual(h.errors,[]);
  }finally{await h.close();}
});

test('new cell click wins out of order and unmount aborts without publication',async()=>{
  const h=await createPagedTreeHarness(),pending=[deferred(),deferred(),deferred()],signals=[],published=[];let i=0;
  h.network.api=(_path,options)=>{signals.push(options.signal);return pending[i++].promise;};
  try{
    await h.render({...scopeA,onSelectCell:(cell,epoch)=>published.push([cell,epoch.epoch_uuid])});
    const first=await startSelection(h,'cell');let second;
    await h.act(()=>{second=h.tree.onSelectBranch({value:'cell-B',path:['B']},{field:'cell'},'old-revision');});
    await h.act(async()=>{pending[1].resolve({...pageAt(0),epochs:[{epoch_uuid:'epoch-B'}]});await second;pending[0].resolve(pageAt(0));await first.work;});
    assert.equal(signals[0].aborted,true);assert.deepEqual(published,[['cell-B','epoch-B']]);
    const third=await startSelection(h,'cell');await h.unmount();assert.equal(signals[2].aborted,true);
    pending[2].resolve(pageAt(0));await third.work;assert.equal(published.length,1);
  }finally{await h.close();}
});

test('pending range cannot overwrite an independently changed selection',async()=>{
  const h=await createPagedTreeHarness(),pending=deferred(),published=[];
  h.network.api=()=>pending.promise;
  const props={...scopeA,setSelectedEpochs:ids=>published.push(ids)};
  try{
    await h.render(props);const {work}=await startSelection(h,'range');published.length=0;
    await h.render({...props,selectedEpochs:['another-epoch']});
    await h.act(async()=>{pending.resolve(pageAt(0));await work;});
    assert.deepEqual(published,[]);assert.match(h.errors[0],/Selection changed/);
  }finally{await h.close();}
});

test('scope change clears the Shift anchor and preserves Command/Ctrl toggle semantics',async()=>{
  const h=await createPagedTreeHarness(),published=[];
  try{
    const props={...scopeA,setSelectedEpochs:ids=>published.push(ids)};
    await h.render(props);await h.act(()=>h.tree.onSelectEpoch('epoch-A-0',pageAt(0).epochs[0],{},pageAt(0),0));
    await h.render({...props,revision:'view-B',selectedEpochs:['keep']});
    await h.act(()=>h.tree.onSelectEpoch('epoch-A-60',pageAt(60).epochs[0],{shiftKey:true},pageAt(60),0));
    assert.deepEqual(published.at(-1),[]);
    await h.act(()=>h.tree.onSelectEpoch('epoch-A-60',pageAt(60).epochs[0],{ctrlKey:true},pageAt(60),0));
    assert.deepEqual(published.at(-1),['keep','epoch-A-60']);
  }finally{await h.close();}
});

test('cell traversal rejects a server revision change before selecting',async()=>{
  const h=await createPagedTreeHarness(),published=[];
  h.network.api=async()=>({...pageAt(0),revision:'wrong-revision'});
  try{
    await h.render({...scopeA,onSelectCell:(...args)=>published.push(args)});
    const {work}=await startSelection(h,'cell');await h.act(()=>work);
    assert.deepEqual(published,[]);assert.match(h.errors[0],/Tree changed/);
  }finally{await h.close();}
});
