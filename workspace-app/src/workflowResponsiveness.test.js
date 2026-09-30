import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {deferred} from './test-support/pagedTreeHarness.js';

const filter=name=>({tag_predicate:JSON.stringify({all:[{field:'annotations/effective/tags',operator:'contains',value:name},{not:{field:'annotations/epoch/tags',operator:'contains',value:'excluded'}}]})});
const sharedInput=h=>h.root.findByProps({'aria-label':'Tag this epoch'});
const sharedSection=h=>h.root.findByProps({'aria-label':'Shared cell and epoch tags'});
async function ready(h){await h.waitFor(()=>{try{return !!h.viewer.epoch&&!sharedInput(h).props.disabled;}catch{return false;}});}
async function sharedSave(h,value){await h.act(()=>sharedInput(h).props.onChange({target:{value}}));await h.act(()=>sharedInput(h).parent.props.onSubmit({preventDefault(){}}));}
const summaries=record=>/^\/(projects|overview|protocol-suggestions|jobs|metadata\/status)(?:\?|$)/.test(record.path)||/^\/protocols\/[^/?]+(?:\?|$)/.test(record.path);

for(const total of [500,1000,5000,100000])test(`mounted ${total} epochs: A/B/A filters start fenced pages immediately and retain one Inspector`,async()=>{
  const h=await createWorkflowHarness({total});
  try{
    await h.mount();await ready(h);const start=h.fixture.requests.length;
    await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-0','epoch-2']));
    for(const name of ['A','B','A']){
      const before=h.fixture.requests.length;
      await h.act(()=>h.viewer.onViewFilters(filter(name)));
      await h.waitFor(()=>!h.viewer.navigation.loading&&h.viewer.treePane.listProps.cells.length>0);
      assert.equal(h.viewer.targets.length,0);
      assert.equal(h.viewer.epoch,null,'A changed filter must clear an out-of-scope focused epoch');
      assert.equal(h.viewer.treePane.listProps.cells.reduce((sum,cell)=>sum+cell.epochs,0),total/2);
      assert.equal(h.viewer.navigation.total,total/2);
      const calls=h.fixture.requests.slice(before).filter(record=>record.path.startsWith('/protocols/'));
      assert.equal(calls.filter(record=>record.path.includes('/epochs?')).length,1);
      assert.equal(calls.filter(record=>record.path.includes('/tree-fields')).length,0);
      assert.equal(h.fixture.requests.slice(before).filter(record=>record.path==='/metadata/fields').length,0);
      assert.equal(calls.filter(summaries).length,0);
    }
    assert.equal(h.fixture.mounts,1);assert.equal(h.fixture.unmounts,0);
    assert.equal(h.fixture.requests.slice(start).filter(summaries).length,0);
  }finally{await h.close();}
});

test('mounted shared save refreshes live authority once, defers hidden summaries, and refreshes overview when shown',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);const before=h.fixture.requests.length;
    await sharedSave(h,'new tag');await ready(h);
    const calls=h.fixture.requests.slice(before);
    assert.equal(calls.filter(record=>record.path==='/annotations').length,1);
    assert.equal(calls.filter(record=>record.path.includes('/annotations')&&record.method==='GET').length,0);
    assert.equal(calls.filter(record=>record.path.includes('/epochs?')).length,0);
    assert.equal(calls.filter(record=>record.path==='/epochs/epoch-0?protocol_uuid=protocol-A').length,0);
    assert.equal(calls.filter(summaries).length,0);
    assert.equal(calls.filter(record=>record.path.includes('/tree-fields')||record.path==='/metadata/fields').length,0);
    assert.equal(h.viewer.epoch.annotations.epoch_tags[0].tag,'new tag');
    assert.equal(h.viewer.treePane.listProps.disabled,true);
    await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path.includes('/epochs?')).length,1);
    assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-1');
    assert.equal(h.fixture.mounts,1);
    const returnAt=h.fixture.requests.length;
    await h.act(()=>h.fixture.navigate('overview'));
    assert.equal(h.fixture.requests.slice(returnAt).filter(record=>record.path==='/overview').length,1);
    assert.equal(h.fixture.requests.slice(returnAt).filter(record=>record.path==='/projects').length,0);
  }finally{await h.close();}
});

test('mounted curation uses fresh page authority after tags while the hidden descriptor remains older',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);await sharedSave(h,'shared');await ready(h);await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
    const dataset=h.viewer.tags.props.children;
    await h.act(()=>dataset.props.onValue('dataset'));
    const before=h.fixture.requests.length;
    await h.act(()=>h.viewer.tags.props.children.props.onAdd('dataset'));
    await ready(h);
    const calls=h.fixture.requests.slice(before).filter(record=>record.path.includes('/curation'));
    assert.equal(calls.length,2);assert.equal(calls[0].body.query_revision,'query-1');
    assert.equal(calls[0].body.expected_binding_version,2);
    assert.equal(calls[1].body.query_revision,'query-1');
    assert.deepEqual(calls[1].body.epoch_uuids,['epoch-0']);
    assert.equal(h.fixture.requests.slice(before).filter(summaries).length,0);
  }finally{await h.close();}
});

test('mounted filtered export waits for its exact summary without unmounting Inspector',async()=>{
  const h=await createWorkflowHarness(),pending=deferred();
  try{
    await h.mount();await ready(h);await h.act(()=>h.viewer.onViewFilters(filter('B')));
    const before=h.fixture.mounts;let requested;
    h.fixture.respond=(url,options,fallback)=>{
      if(url.pathname==='/api/protocols/protocol-A'&&url.searchParams.has('tag_predicate')){requested=url;return pending.promise;}
      return fallback();
    };
    await h.act(()=>h.root.findByProps({'aria-label':'Export'}).props.onClick());
    assert.ok(requested?.searchParams.get('tag_predicate').includes('B'));
    const button=()=>h.root.findByType('workflow-dialog').findAllByType('button').find(node=>node.children.some(child=>typeof child==='string'&&child.startsWith('Save & export')));
    assert.equal(button().props.disabled,true);
    assert.equal(h.fixture.mounts,before);assert.equal(h.fixture.unmounts,0);
    await h.act(()=>pending.resolve({definition:{name:'Test'},query_revision:'query-0',expected_binding_version:2,counts:{epochs:250,cells:1,included:250},cells:[],source_eligibility:{}}));
    assert.equal(button().props.disabled,false);assert.equal(h.fixture.mounts,before);
  }finally{await h.close();}
});

test('mounted shared save507 retains the draft, does not navigate or invalidate, and never retries',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);h.fixture.failNextSave=true;const before=h.fixture.requests.length;
    await h.act(()=>sharedInput(h).props.onChange({target:{value:'retain draft'}}));
    const target=h.fixture.nodes.get('Tag this epoch');
    await h.act(()=>sharedSection(h).props.onKeyDown({key:'Tab',target,preventDefault(){},stopPropagation(){}}));
    assert.equal(sharedInput(h).props.value,'retain draft');assert.equal(h.viewer.epoch.epoch_uuid,'epoch-0');
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path==='/annotations').length,1);
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path.includes('/epochs?')||summaries(record)).length,0);
    assert.match(JSON.stringify(h.root.findAllByProps({role:'alert'}).map(node=>node.children.filter(child=>typeof child==='string'))),/Durable recovery copy failed/);
    await h.settle(180);
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.method==='POST').length,1);
  }finally{await h.close();}
});

test('mounted selected shared save refuses old selection after its cancellable revision read',async()=>{
  const h=await createWorkflowHarness(),pending=deferred();
  try{
    await h.mount();await ready(h);let read;
    h.fixture.respond=(url,options,fallback)=>{if(url.pathname==='/api/annotations/read'){read=JSON.parse(options.body);return pending.promise;}return fallback();};
    await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-0','epoch-2']));
    const input=h.root.findByProps({'aria-label':'Tag 2 selected epochs'});
    await h.act(()=>input.props.onChange({target:{value:'retained selection draft'}}));
    await h.act(()=>input.parent.props.onSubmit({preventDefault(){}}));
    await h.act(()=>h.viewer.treePane.listProps.setTargets(['epoch-4']));
    await h.act(()=>pending.resolve({targets:Object.fromEntries(read.target_uuids.map(identity=>[identity,{target_kind:'epoch',target_uuid:identity,revisions:{author:0}}]))}));
    assert.equal(h.fixture.requests.filter(record=>record.path==='/annotations').length,0);
    assert.equal(h.root.findByProps({'aria-label':'Tag 1 selected epochs'}).props.value,'retained selection draft');
  }finally{await h.close();}
});

test('mounted structural refresh invalidates project/import/metadata summaries even during inspection',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);const before=h.fixture.requests.length;
    const metadata=h.root.find(node=>typeof node.type==='function'&&node.type.name==='MetadataRefresh');
    await h.act(()=>metadata.props.onChange());
    const paths=new Set(h.fixture.requests.slice(before).map(record=>record.path));
    for(const path of ['/projects','/overview','/protocol-suggestions','/jobs','/metadata/status','/metadata/fields','/protocols/protocol-A'])assert.ok(paths.has(path),path);
  }finally{await h.close();}
});

test('same-scope tag refresh retains expanded cells but disables stale authority until the page returns',async()=>{
  const h=await createWorkflowHarness(),pending=deferred();
  try{
    await h.mount();await ready(h);
    const cell=()=>h.root.findByProps({className:'cell-tree-cell'});
    await h.act(()=>cell().props.onToggle({currentTarget:{open:true}}));
    assert.equal(cell().props.open,true);
    h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/protocols/protocol-A/epochs'&&url.searchParams.get('include_cells')==='true'?pending.promise:fallback();
    await sharedSave(h,'keep branch');
    assert.equal(cell().props.open,true);
    assert.equal(h.viewer.treePane.listProps.disabled,true);
    await h.act(()=>pending.resolve({query_revision:'query-1',expected_binding_version:2,total:500,offset:0,epochs:[],cells:[{cell_uuid:'cell-0',label:'Cell 0',date:'2026-09-29',epochs:500}]}));
    await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
    assert.equal(cell().props.open,true);
  }finally{await h.close();}
});

test('an external annotation notification refreshes authority without reloading unrelated project metadata',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);const before=h.fixture.requests.length;
    h.fixture.generation++;
    const sync=h.root.findAllByType('workflow-child').find(node=>node.props.enabled===true);
    await h.act(()=>sync.props.onChange({pulled:1}));await ready(h);
    assert.equal(h.viewer.treePane.listProps.source.queryRevision,'query-1');
    assert.equal(h.fixture.requests.slice(before).filter(summaries).length,0);
  }finally{await h.close();}
});

test('mounted dataset save507 preserves its draft and does not queue an automatic retry',async()=>{
  const h=await createWorkflowHarness();
  try{
    await h.mount();await ready(h);h.fixture.failNextSave=true;
    await h.act(()=>h.viewer.tags.props.children.props.onValue('dataset draft'));
    const before=h.fixture.requests.length;
    await h.act(()=>h.viewer.tags.props.children.props.onAdd('dataset draft'));
    assert.equal(h.viewer.tags.props.children.props.value,'dataset draft');
    assert.equal(h.fixture.generation,0);
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path.includes('/curation')).length,2);
    assert.equal(h.fixture.requests.slice(before).filter(summaries).length,0);
    await h.settle(150);
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.method==='POST').length,2);
  }finally{await h.close();}
});

test('standalone annotations accept a fresh epoch snapshot after explicit refresh without keeping a redundant remote reader',async()=>{
  const h=await createWorkflowHarness();
  const epoch={epoch_uuid:'epoch-0',cell_uuid:'cell-0',annotations:{cell_tags:[],epoch_tags:[],revisions:{epoch:{author:0},cell:{author:0}}}};
  try{
    const Tags=await h.component('AnnotationTags');
    await h.mount(Tags,{epoch,revision:0,onChange:()=>{}});
    await sharedSave(h,'standalone');
    assert.ok(h.fixture.requests.some(record=>record.path==='/epochs/epoch-0/annotations'));
    const fresh={...epoch,annotations:{...epoch.annotations,revisions:{epoch:{author:1},cell:{author:0}},epoch_tags:[{tag:'standalone',profile_uuid:'author',author_name:'Scientist'}]}};
    await h.render(Tags,{epoch:fresh,revision:1,onChange:()=>{}});
    const before=h.fixture.requests.length;
    await h.render(Tags,{epoch:fresh,revision:2,onChange:()=>{}});
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path.endsWith('/annotations')).length,0);
    assert.equal(sharedInput(h).props.disabled,false);
  }finally{await h.close();}
});

test('successful tag Tab waits for a fresh anchored membership page before choosing the next epoch',async()=>{
  const h=await createWorkflowHarness(),anchor=deferred();
  try{
    await h.mount();await ready(h);let requested=false;
    h.fixture.respond=(url,options,fallback)=>{if(url.pathname==='/api/protocols/protocol-A/epochs'&&url.searchParams.has('anchor_uuid')){requested=true;return anchor.promise;}return fallback();};
    await h.act(()=>sharedInput(h).props.onChange({target:{value:'save then next'}}));
    const target=h.fixture.nodes.get('Tag this epoch');
    await h.act(()=>sharedSection(h).props.onKeyDown({key:'Tab',target,preventDefault(){},stopPropagation(){}}));
    assert.equal(requested,true);assert.equal(h.viewer.navigation.loading,true);
    // The old page's immediate neighbor was epoch-1. A post-save membership
    // receipt now places epoch-7 next; this exact authority must win.
    await h.act(()=>anchor.resolve({query_revision:'query-1',expected_binding_version:2,total:2,offset:0,epochs:[{epoch_uuid:'epoch-0',cell_uuid:'cell-0'},{epoch_uuid:'epoch-7',cell_uuid:'cell-0'}],cells:[{cell_uuid:'cell-0',label:'Cell 0',date:'2026-09-29',epochs:2}]}));
    await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-7');
    assert.equal(h.fixture.annotations.get('epoch-0')[0],'save then next');
    assert.equal(h.fixture.requests.filter(record=>record.path==='/annotations').length,1);
  }finally{await h.close();}
});

test('late successful tag Tab cannot navigate a newly filtered Inspector after its old editor unmounted',async()=>{
  const h=await createWorkflowHarness(),save=deferred();
  try{
    await h.mount();await ready(h);
    h.fixture.respond=(url,options,fallback)=>url.pathname==='/api/annotations'?save.promise:fallback();
    await h.act(()=>sharedInput(h).props.onChange({target:{value:'old scope'}}));
    const target=h.fixture.nodes.get('Tag this epoch');let work;
    await h.act(()=>{work=sharedSection(h).props.onKeyDown({key:'Tab',target,preventDefault(){},stopPropagation(){}});});
    await h.act(()=>h.viewer.onViewFilters(filter('B')));
    const before=h.fixture.requests.length;
    await h.act(async()=>{save.resolve({changed:1,targets:{'epoch-0':{target_kind:'epoch',target_uuid:'epoch-0',revisions:{author:1},tags:[{tag:'old scope',profile_uuid:'author',author_name:'Scientist',target_kind:'epoch',target_uuid:'epoch-0',revision:1}]}}});await work;});
    assert.equal(h.fixture.requests.slice(before).filter(record=>record.path.includes('anchor_uuid')).length,0);
    assert.equal(h.viewer.epoch,null);assert.equal(h.fixture.mounts,1);
  }finally{await h.close();}
});
