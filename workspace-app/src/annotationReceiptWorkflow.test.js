import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {confirmAnnotationReceipt,mergeAnnotationReceipts,applyAnnotationReceipts} from './annotationReceipts.js';
import {createResourceCache} from './resourceCache.js';

const input=h=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props['aria-label'].startsWith('Tag to add'));
async function ready(h){await h.waitFor(()=>{try{return !!input(h)&&!input(h).props.disabled;}catch{return false;}});}
async function save(h,value){await h.act(()=>input(h).props.onChange({target:{value}}));await h.act(()=>input(h).parent.props.onSubmit({preventDefault(){}}));await ready(h);}
const text=node=>node.children.filter(value=>typeof value==='string').join('').trim();
async function filterRules(h,logic,rules){
  await h.act(()=>h.root.findByProps({'aria-controls':'protocol-view-filter-panel'}).props.onClick());
  await h.act(()=>h.root.findByProps({id:'protocol-view-filter-panel'}).findAllByType('select')[0].props.onChange({target:{value:'rules'}}));
  await h.act(()=>h.root.findByProps({'aria-label':'Match tag rules'}).props.onChange({target:{value:logic}}));
  for(let index=0;index<rules.length;index++){
    if(index&&!h.root.findAllByProps({'aria-label':`Tag scope ${index+1}`}).length)await h.act(()=>h.root.findAllByType('button').find(node=>text(node)==='Add tag rule').props.onClick());
    await h.act(()=>{h.root.findByProps({'aria-label':`Tag scope ${index+1}`}).props.onChange({target:{value:rules[index].scope}});h.root.findByProps({'aria-label':`Tag value ${index+1}`}).props.onChange({target:{value:rules[index].value}});});
  }
  await h.act(()=>h.root.findByProps({id:'protocol-view-filter-panel'}).props.onSubmit({preventDefault(){}}));
  await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
}

test('mounted tag10 then another10 acknowledges each exact receipt, then composes20 and cell/epoch filters',async()=>{
  const h=await createWorkflowHarness({total:40});h.fixture.savedTagFilters=true;
  try{
    await h.mount();await ready(h);
    for(const [start,tag] of [[0,'A'],[10,'B']]){
      await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
      const ids=Array.from({length:10},(_,offset)=>`epoch-${start+offset}`);
      await h.act(()=>h.viewer.treePane.listProps.setTargets(ids));
      const before=h.fixture.requests.length;
      await save(h,tag);
      const calls=h.fixture.requests.slice(before);
      assert.deepEqual(calls.filter(row=>row.method==='POST').map(row=>row.path),['/annotations/read','/annotations']);
      assert.deepEqual(calls.find(row=>row.path==='/annotations').body.target_uuids,ids);
      assert.equal(calls.filter(row=>row.path.startsWith('/epochs/')||row.path.includes('/epochs?')).length,0,'Acknowledgment must not wait for an epoch/page read');
      assert.equal(input(h).props.disabled,false);
      assert.match(h.root.findByProps({className:'annotation-result'}).children.join(''),/Saved 10 selected epoch/);
      for(const id of ids)assert.deepEqual(h.fixture.annotations.get(id),[tag]);
    }
    await filterRules(h,'any',[{scope:'effective',value:'A'},{scope:'epoch',value:'B'}]);
    assert.equal(h.viewer.navigation.total,20);
    const ast=JSON.parse(new URLSearchParams(h.viewer.treePane.listProps.source.query).get('tag_predicate'));
    assert.deepEqual(ast.any.map(node=>node.field),['annotations/effective/tags','annotations/epoch/tags']);
    const cell=h.viewer.treePane.listProps.cells[0];
    await h.act(()=>h.viewer.treePane.listProps.onSelectCell(cell,{epoch_uuid:'epoch-0',cell_uuid:'cell-0'}));await ready(h);
    const before=h.fixture.requests.length;
    await save(h,'cell C');
    const mutation=h.fixture.requests.slice(before).find(row=>row.path==='/annotations');
    assert.equal(mutation.body.target_kind,'cell');assert.deepEqual(mutation.body.target_uuids,['cell-0']);
    assert.equal(h.fixture.cellAnnotations.size,1);assert.equal(h.fixture.annotations.size,20,'Cell inheritance must not create epoch annotation rows');
    assert.equal(h.viewer.epoch.annotations.cell_tags[0].tag,'cell C');
    await filterRules(h,'all',[{scope:'cell',value:'cell C'},{scope:'epoch',value:'A'}]);
    assert.equal(h.viewer.navigation.total,10);assert.equal(h.fixture.mounts,1);
  }finally{await h.close();}
});

test('twenty successive direct tags use confirmed per-profile revisions without focused metadata rereads',async()=>{
  const h=await createWorkflowHarness({total:20});
  try{
    await h.mount();await ready(h);const before=h.fixture.requests.length;
    for(let count=0;count<20;count++){
      await save(h,`tag ${count}`);
      assert.equal(h.viewer.epoch.annotations.revisions.epoch.author,count+1);
      assert.equal(input(h).props.disabled,false);
    }
    const calls=h.fixture.requests.slice(before),writes=calls.filter(row=>row.path==='/annotations');
    assert.equal(writes.length,20);assert.deepEqual(writes.map(row=>row.body.expected_revisions['epoch-0']),Array.from({length:20},(_,i)=>i));
    assert.equal(calls.filter(row=>row.path==='/epochs/epoch-0?protocol_uuid=protocol-A').length,0);
    assert.equal(h.viewer.epoch.annotations.epoch_tags.length,20);
    await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
    assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-20');
  }finally{await h.close();}
});

test('receipt eviction reloads the focused target before the next direct edit',async()=>{
  const h=await createWorkflowHarness({total:100});
  try{
    await h.mount();await ready(h);await save(h,'focused first');
    const before=h.fixture.requests.length;
    for(let start=1;start<=61;start+=20){
      await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
      await h.act(()=>h.viewer.treePane.listProps.setTargets(Array.from({length:20},(_,offset)=>`epoch-${start+offset}`)));
      await save(h,`batch ${start}`);
    }
    assert.equal(h.viewer.epoch.epoch_uuid,'epoch-0');
    assert.equal(h.viewer.epoch.annotations.revisions.epoch.author,1);
    assert.deepEqual(h.viewer.epoch.annotations.epoch_tags.map(chip=>chip.tag),['focused first']);
    assert.ok(h.fixture.requests.slice(before).some(row=>row.path==='/epochs/epoch-0?protocol_uuid=protocol-A'),'Eviction must refresh the old focused metadata base');
    await h.act(()=>h.viewer.treePane.listProps.setTargets([]));await ready(h);
    await save(h,'focused second');
    const mutation=h.fixture.requests.filter(row=>row.path==='/annotations').at(-1);
    assert.deepEqual(mutation.body.target_uuids,['epoch-0']);
    assert.equal(mutation.body.expected_revisions['epoch-0'],1);
    assert.equal(mutation.status,200);
    assert.equal(h.viewer.epoch.annotations.revisions.epoch.author,2);
  }finally{await h.close();}
});

test('receipt validation rejects wrong target/profile revisions and preserves independent author sets',()=>{
  const request={target_kind:'cell',target_uuids:['cell'],profile_uuid:'me',expected_revisions:{cell:1}};
  const chip=(profile,revision,tag)=>({target_kind:'cell',target_uuid:'cell',profile_uuid:profile,author_name:profile,revision,tag});
  const result={changed:1,targets:{cell:{target_kind:'cell',target_uuid:'cell',revisions:{me:2,other:5},tags:[chip('me',2,'saved'),chip('other',5,'other')]}}};
  assert.throws(()=>confirmAnnotationReceipt({...result,persistence:{database:'pending'}},request),/could not be verified/);
  const confirmed=confirmAnnotationReceipt(result,request),store=mergeAnnotationReceipts(new Map(),confirmed);
  const base={epoch_uuid:'e',cell_uuid:'cell',annotations:{cell_tags:[chip('other',6,'newer')],epoch_tags:[],revisions:{cell:{other:6},epoch:{}}}};
  const next=applyAnnotationReceipts(base,store);
  assert.deepEqual(new Set(next.annotations.cell_tags.map(row=>row.tag)),new Set(['saved','newer']));
  assert.equal(store.size,1);
  for(const change of ['identity','kind','revision','profile']){
    const bad=structuredClone(result);
    if(change==='identity')bad.targets.cell.target_uuid='another';
    if(change==='kind')bad.targets.cell.target_kind='epoch';
    if(change==='revision')bad.targets.cell.revisions.me=0;
    if(change==='profile')bad.targets.cell.tags[0].profile_uuid='invented';
    assert.throws(()=>confirmAnnotationReceipt(bad,request),/could not be verified/);
  }
  let bounded=new Map();
  for(let count=0;count<100;count++)bounded=mergeAnnotationReceipts(bounded,{version:1,targets:[{target_kind:'cell',target_uuid:String(count),tags:[],revisions:{}}]},{targets:8,bytes:2000});
  assert.ok(bounded.size<=8);assert.ok([...bounded.values()].reduce((sum,value)=>sum+value.bytes,0)<=2000);
});

test('confirmed cell receipts invalidate bounded metadata caches without discarding immutable trace windows',()=>{
  const cache=createResourceCache();
  cache.put('/epochs/e?protocol_uuid=p',0,{epoch_uuid:'e'});
  cache.put('/epochs/e/trace?stream_uuid=s',0,{values:[1,2]});
  cache.invalidateAnnotations({targets:[{target_kind:'cell',target_uuid:'cell'}]});
  assert.equal(cache.get('/epochs/e?protocol_uuid=p',0),undefined);
  assert.deepEqual(cache.get('/epochs/e/trace?stream_uuid=s',0),{values:[1,2]});
});
