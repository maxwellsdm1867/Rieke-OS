import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectionHarness,deferred,cells,sourceA,pageAt} from './test-support/inspectionTreeHarness.js';

const base={cells,source:sourceA,revision:1,targets:[],disabled:false};
test('mounted inspection cancels late cell/range publication for scope and revision changes',async()=>{
 const h=await createInspectionHarness();
 try{
  for(const kind of ['cell','range'])for(const change of ['unchanged','revision','query','protocol','queryRevision','order','membership','disabled']){
   const pending=deferred(),published=[],signals=[];
   h.network.api=(_path,options)=>{signals.push(options.signal);return pending.promise;};
   const props={...base,onFocus(){},onSelectCell:(cell,epoch)=>published.push([cell.cell_uuid,epoch.epoch_uuid]),setTargets:ids=>published.push(ids)};
   await h.render(props);let work;
   if(kind==='cell')({work}=await h.selectCell());
   else{await h.selectEpoch(58);published.length=0;({work}=await h.selectEpoch(63,{shiftKey:true}));}
   const updates={unchanged:{source:{...sourceA}},revision:{revision:2},query:{source:{...sourceA,query:'cell_type=OFF'}},
    protocol:{source:{...sourceA,protocolId:'protocol-B'}},queryRevision:{source:{...sourceA,queryRevision:'query-B'}},order:{cells:[...cells].reverse()},
    membership:{cells:cells.map(cell=>({...cell,epochs:cell.epochs+1}))},disabled:{disabled:true}};
   await h.render({...props,...updates[change]});
   await h.act(async()=>{pending.resolve(pageAt());await work;});
   if(change==='unchanged')assert.deepEqual(published,kind==='cell'?[['cell-A','cell-A-0']]:[['cell-A-58','cell-A-59','cell-A-60','cell-A-61','cell-A-62','cell-A-63']],`${kind}:${change}`);
   else{assert.equal(signals[0].aborted,true,`${kind}:${change}`);assert.deepEqual(published,[],`${kind}:${change}`);}
   assert.deepEqual(h.errors,[]);await h.unmount();
  }
 }finally{await h.close();}
});

test('old completions and errors cannot clear a newer pending selection or resurrect after A/B/A',async()=>{
 const h=await createInspectionHarness(),pending=[deferred(),deferred()],published=[];let index=0;
 h.network.api=()=>pending[index++].promise;
 const props={...base,onSelectCell:(...args)=>published.push(args),setTargets(){}};
 try{
  await h.render(props);const first=await h.selectCell(),oldHandler=h.branch.onSelectCell;
  await h.render({...props,revision:2});
  await h.act(()=>oldHandler(cells[0]));assert.equal(index,1);
  await h.render(props);const second=await h.selectCell();
  await h.act(async()=>{pending[0].reject(Error('stale error'));await first.work;});
  assert.equal(h.selecting,true);assert.deepEqual(h.errors,[]);assert.deepEqual(published,[]);
  await h.act(async()=>{pending[1].resolve(pageAt());await second.work;});
  assert.equal(h.selecting,false);assert.equal(published.length,1);
 }finally{await h.close();}
});

test('same-scope pending selection uses latest callbacks and cannot overwrite changed targets',async()=>{
 const h=await createInspectionHarness();
 try{
  let pending=deferred();const old=[],latest=[];
  h.network.api=()=>pending.promise;
  const props={...base,onFocus(){},onSelectCell:()=>old.push('cell'),setTargets:ids=>old.push(ids)};
  await h.render(props);const cell=await h.selectCell();
  await h.render({...props,onSelectCell:()=>latest.push('cell')});
  await h.act(async()=>{pending.resolve(pageAt());await cell.work;});
  assert.deepEqual(old,[]);assert.deepEqual(latest,['cell']);
  pending=deferred();await h.selectEpoch(58);old.length=0;latest.length=0;
  const successfulRange=await h.selectEpoch(63,{shiftKey:true});
  await h.render({...props,setTargets:ids=>latest.push(ids)});
  await h.act(async()=>{pending.resolve(pageAt());await successfulRange.work;});
  assert.deepEqual(old,[]);assert.deepEqual(latest,[['cell-A-58','cell-A-59','cell-A-60','cell-A-61','cell-A-62','cell-A-63']]);
  await h.render(props);
  pending=deferred();await h.selectEpoch(58);old.length=0;
  const range=await h.selectEpoch(63,{shiftKey:true});
  await h.render({...props,targets:['keep']});
  await h.act(async()=>{pending.resolve(pageAt());await range.work;});
  assert.deepEqual(old,[]);assert.match(h.errors[0],/Selection changed/);
 }finally{await h.close();}
});

test('protocol and predicate range pages require consistent receipts despite unchanged endpoints/counts',async()=>{
 const h=await createInspectionHarness();
 try{
  for(const kind of ['protocol','predicate']){
   const source=kind==='protocol'?sourceA:{kind,predicate:{all:[]},splits:'cell',treeRevision:'query-A'};
   const published=[];h.network.api=async()=>pageAt('cell-A',0,'query-B',kind);
   await h.render({...base,source,onFocus(){},setTargets:ids=>published.push(ids)});
   await h.selectEpoch(58,{},'cell-A',pageAt('cell-A',0,'query-A',kind));published.length=0;
   const {work}=await h.selectEpoch(63,{shiftKey:true},'cell-A',pageAt('cell-A',60,'query-A',kind));
   await h.act(()=>work);assert.deepEqual(published,[]);assert.match(h.errors[0],/query changed/);
   await h.unmount();
  }
 }finally{await h.close();}
});

test('cell ownership, unmount cancellation, and duplicate-label UUID qualifiers stay exact',async()=>{
 const h=await createInspectionHarness(),published=[];
 const props={...base,onSelectCell:(...args)=>published.push(args),setTargets(){}};
 try{
  h.network.api=async()=>pageAt('cell-B');await h.render(props);
  const summaries=h.summaries.filter(item=>item.title);
  assert.equal(summaries.length,2);assert.deepEqual(summaries.map(item=>item.title),cells.map(item=>item.cell_uuid));
  assert.notEqual(summaries[0]['aria-label'],summaries[1]['aria-label']);assert.deepEqual(cells.map(item=>item.label),['Cell3','Cell3']);
  const wrong=await h.selectCell();await h.act(()=>wrong.work);assert.match(h.errors[0],/ownership/);assert.deepEqual(published,[]);
  const pending=deferred();let signal;h.network.api=(_path,options)=>{signal=options.signal;return pending.promise;};
  const late=await h.selectCell();await h.unmount();assert.equal(signal.aborted,true);
  pending.resolve(pageAt());await late.work;assert.deepEqual(published,[]);
 }finally{await h.close();}
});
