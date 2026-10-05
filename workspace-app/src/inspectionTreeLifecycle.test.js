import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectionHarness,deferred,cells,sourceA,pageAt} from './test-support/inspectionTreeHarness.js';

const base={cells,source:sourceA,revision:1,targets:[],disabled:false};
test('actual expanding cell page and first-epoch selection share one request',async()=>{
 const h=await createInspectionHarness({realPages:true}),pending=deferred(),calls=[],selected=[];
 h.network.api=(path,options)=>{calls.push({path,...options});return pending.promise;};
 try{
  await h.render({...base,setTargets(){},onSelectCell:(_cell,epoch)=>selected.push(epoch.epoch_uuid)});
  await h.toggle(0,true);
  const selection=await h.selectCell();await h.toggle(1,true);
  assert.equal(calls.length,1,'the cell summary and mounted page must join the same read');
  await h.act(async()=>{pending.resolve(pageAt());await selection.work;});
  assert.deepEqual(selected,['cell-A-0']);
  assert(h.buttons.some(button=>button['aria-label']?.endsWith('epoch 1')));
 }finally{await h.close();}
});
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


test('return restores date/cell expansion and page only after fresh matching membership',async()=>{
 const h=await createInspectionHarness();let saved;
 const props={...base,navigationScope:'project-A/protocol-A/filter-A',membershipReady:true,onNavigationChange:value=>{saved=value;},setTargets(){}};
 try{
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  await h.act(()=>h.buttons.find(button=>button.children==='Load more epochs').onClick());
  await h.unmount();
  await h.render({...props,cells:[],membershipReady:false,initialNavigation:saved});
  await h.render({...props,initialNavigation:saved});
  assert.equal(h.details[0].open,true);assert.equal(h.details[1].open,true);
  assert.ok(h.buttons.some(button=>button['aria-label']?.endsWith('epoch 61')));
  await h.unmount();
  await h.render({...props,navigationScope:'project-A/protocol-A/filter-B',initialNavigation:saved});
  assert.equal(h.details[0].open,false);assert.equal(h.details[1].open,false);
 }finally{await h.close();}
});


test('external and same-target navigation intents cancel delayed scroll; errors sleep and retry restores',async()=>{
 const prior={requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame,MutationObserver:globalThis.MutationObserver};
 const frames=new Map(),observers=new Set(),listeners=new Map();let serial=0,childPending=true;
 globalThis.requestAnimationFrame=callback=>{frames.set(++serial,callback);return serial;};
 globalThis.cancelAnimationFrame=id=>frames.delete(id);
 globalThis.MutationObserver=class{constructor(callback){this.callback=callback;}observe(){observers.add(this);}disconnect(){observers.delete(this);}};
 const pane={scrollTop:0,scrollHeight:660,clientHeight:100,addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)};
 const element={closest:()=>pane,querySelector:()=>childPending?{}:null};
 const h=await createInspectionHarness({treeElement:element});
 const props={...base,navigationScope:'scope-A',navigationRequest:0,membershipReady:false,setTargets(){},initialNavigation:{scope:'scope-A',dates:['2026-06-11'],cells:['cell-A'],offsets:{'cell-A':0},scrollTop:180}};
 const frame=async()=>h.act(()=>{const work=[...frames.values()];frames.clear();work.forEach(fn=>fn());});
 const changed=()=>{for(const observer of [...observers])observer.callback();};
 try{
  await h.render(props);await frame();assert.equal(frames.size,0,'failed membership sleeps');
  await h.render({...props,membershipReady:true});changed();await frame();assert.equal(frames.size,0,'failed child page sleeps');
  await h.render({...props,membershipReady:true,navigationRequest:1});
  childPending=false;changed();await frame();await frame();
  assert.equal(pane.scrollTop,0,'same-target explicit intent beats prior scroll');
  assert.equal(observers.size,0,'canceled operation releases observer');
  await h.unmount();assert.equal(frames.size,0);assert.equal(listeners.size,0);
  childPending=true;await h.render({...props,membershipReady:true});await frame();assert.equal(frames.size,0);
  childPending=false;changed();await frame();assert.equal(pane.scrollTop,0);await frame();assert.equal(pane.scrollTop,180,'retry restores once child page settles');
  assert.equal(observers.size,0);
  await h.unmount();pane.scrollTop=0;childPending=true;await h.render({...props,membershipReady:true});await frame();
  await h.render({...props,membershipReady:true,focused:'new-epoch'});childPending=false;changed();await frame();await frame();assert.equal(pane.scrollTop,0,'external focus change also cancels');
 }finally{await h.close();Object.assign(globalThis,prior);}
});

test('scrolling appends bounded pages with original ordinals and retires changed membership',async()=>{
 const h=await createInspectionHarness();let saved;
 const props={...base,setTargets(){},onNavigationChange:value=>{saved=value;}};
 try{
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  assert.equal(h.buttons.some(button=>button['aria-label']?.startsWith('Next epochs')),false);
  assert.equal(h.buttons.filter(button=>button['aria-label']?.startsWith('Inspect ')).length,60);
  await h.act(()=>h.buttons.find(button=>button.children==='Load more epochs').onFocus());
  assert.equal(h.buttons.filter(button=>button['aria-label']?.startsWith('Inspect ')).length,65);
  assert.equal(saved.offsets['cell-A'],60);
  await h.unmount();
  h.network.page=(source,request)=>({loading:false,error:null,reload(){},data:pageAt(request.cellUuid,request.offset,request.offset?'changed':'query-A')});
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  await h.act(()=>h.buttons.find(button=>button.children==='Load more epochs').onClick());
  assert.match(h.errors.join(' '),/query changed/i);
  assert.equal(h.buttons.some(button=>button['aria-label']?.startsWith('Inspect ')),false);
 }finally{await h.close();}
});

test('keyboard focus reveals later rows without a visible sentinel and rejects binding changes',async()=>{
 const h=await createInspectionHarness(),props={...base,setTargets(){}};
 try{
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  await h.render({...props,focused:'cell-A-60',revealEpoch:pageAt('cell-A',60).epochs[0]});
  assert.ok(h.buttons.some(button=>button['aria-label']?.endsWith('epoch 61')&&button['aria-current']==='true'));
  await h.unmount();
  h.network.page=(source,request)=>({loading:false,error:null,reload(){},data:{...pageAt(request.cellUuid,request.offset),expected_binding_version:request.offset?2:1}});
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  await h.act(()=>h.buttons.find(button=>button.children==='Load more epochs').onClick());
  assert.match(h.errors.join(' '),/list changed/i);
  assert.equal(h.buttons.some(button=>button['aria-label']?.startsWith('Inspect ')),false);
 }finally{await h.close();}
});

test('malformed continuation renders retry instead of publishing rows or crashing',async()=>{
 const h=await createInspectionHarness(),props={...base,setTargets(){}};
 try{
  h.network.page=(source,request)=>({loading:false,error:null,reload(){},data:request.offset?{...pageAt(request.cellUuid,request.offset),epochs:{invalid:true}}:pageAt(request.cellUuid,request.offset)});
  await h.render(props);await h.toggle(0,true);await h.toggle(1,true);
  await h.act(()=>h.buttons.find(button=>button.children==='Load more epochs').onClick());
  assert.match(h.errors.join(' '),/list changed/i);
 }finally{await h.close();}
});
