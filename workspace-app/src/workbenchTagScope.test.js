import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

// A tag saved inside a frozen Workbench view travels on the tag channel. The
// Workbench queue, context, pages and selection manifests are not re-read and
// its frozen read token is not renewed (the server no longer folds shared tags
// into candidate scope either).
const base='/protocols/protocol-A/workbench',root=`${base}/candidates/union`;
const cell={cell_uuid:'cell-0',label:'Cell 0',date:'2026-09-29',cell_type:'ON',epochs:2};
const queue={contract_version:1,queue_revision:'queue-one',pending_epoch_count:2,pending_cell_count:1,eligible_pending_epoch_count:2,eligible_pending_cell_count:1,total_candidate_count:0,candidates:[],
  capabilities:{cumulative_pending_browse:true,frozen_browse:true,drafts:true,additive_accept:true,incoming_export:true}};
const context=()=>({contract_version:1,actor:'author',candidate_revision_uuid:'union',candidate_scope_revision:'scope-one',candidate_recipe_sha256:'recipe',expected_query_revision:'query',expected_binding_version:2,
  protocol:{definition:{protocol_uuid:'protocol-A',name:'Test'},query_revision:'scope-one',query_revision_contract:'workbench-candidate-scope-v2',expected_binding_version:2,cells:[cell],counts:{epochs:2,cells:1}},
  draft:{draft_version:1,selection_mode:'selected',deferred:false,decisions:[],decisions_total:0,decisions_truncated:false},counts:{incoming_epochs:2,pending_epochs:2,pending_cells:1}});
async function mountedWorkbench(){
  const h=await createWorkflowHarness({total:2,frozenTraces:true});
  const chips=(kind,identity)=>[...((kind==='cell'?h.fixture.cellAnnotations:h.fixture.annotations).get(identity)||[])].map(tag=>({tag,profile_uuid:'author',author_name:'Scientist',target_kind:kind,target_uuid:identity,revision:h.fixture.annotationVersions.get(`${kind}:${identity}`)||0}));
  const revisions=(kind,identity)=>h.fixture.annotationVersions.has(`${kind}:${identity}`)?{author:h.fixture.annotationVersions.get(`${kind}:${identity}`)}:{};
  const row=identity=>({epoch_uuid:identity,cell_uuid:'cell-0',cell_label:'Cell 0',date:'2026-09-29',protocol_name:'Test',streams:[],curation:{tags:[],included:true,revision:0},review_decision:{selected:false,reviewed:false,excluded:false},
    annotations:{epoch_uuid:identity,cell_uuid:'cell-0',cell_tags:chips('cell','cell-0'),epoch_tags:chips('epoch',identity),effective_tags:[...chips('cell','cell-0'),...chips('epoch',identity)],revisions:{cell:revisions('cell','cell-0'),epoch:revisions('epoch',identity)}}});
  const {useWorkspaceChanges}=await h.module('useWorkspaceChanges.js');
  h.fixture.route={page:'protocol',protocol:'protocol-A',key:'workbench'};
  h.fixture.respond=(url,options,fallback)=>{
    const path=url.pathname.replace(/^\/api/,'');
    if(path===base)return queue;
    if(path===`${base}/prepare`)return {contract_version:1,kind:'workbench_pending_union',prepare_operation_uuid:'prepare-one',operation_uuid:'prepare-one',candidate_revision_uuid:'union',root,candidate_scope_revision:'scope-one',queue_revision:'queue-one',actor:'author',protocol_uuid:'protocol-A',context:context(),counts:context().counts};
    if(path===`${root}/context`)return context();
    if(path===`${root}/epochs`)return {epochs:['epoch-0','epoch-1'].map(row),cells:[cell],total:2,offset:0,limit:60,candidate_scope_revision:'scope-one',query_revision:'scope-one',expected_binding_version:2};
    if(path.startsWith(`${root}/epochs/`))return row(path.split('/').at(-1));
    if(path==='/annotation-profiles')return {selected_profile_uuid:'author',profiles:[{profile_uuid:'author',display_name:'Scientist'}]};
    return fallback();
  };
  function Shell(){
    const {revision,structureRevision,reviewRevision,changed}=useWorkspaceChanges();
    h.fixture.clock={revision,structureRevision,reviewRevision};
    return createElement(h.Protocol,{id:'protocol-A',projectId:'project',revision,structureRevision,reviewRevision,onChange:changed,initialWorkbench:{},workbenchProtocols:[{protocol_uuid:'protocol-A',name:'Test'}]});
  }
  return {h,Shell};
}

const input=h=>h.root.findAllByType('input').find(node=>node.props['aria-label']?.startsWith('Tag ')&&!node.props['aria-label'].startsWith('Tag to add'));
async function ready(h){await h.waitFor(()=>{try{return !!input(h)&&!input(h).props.disabled;}catch{return false;}});}
async function save(h,value){await h.act(()=>input(h).props.onChange({target:{value}}));await h.act(()=>input(h).parent.props.onSubmit({preventDefault(){}}));await ready(h);}
const workbenchReads=calls=>calls.filter(call=>call.path.startsWith(base)).map(call=>`${call.method} ${call.path}`);

for(const kind of ['epoch','cell'])test(`a ${kind} tag in a frozen Workbench view issues no Workbench reads and keeps its frozen token`,async()=>{
  const {h,Shell}=await mountedWorkbench();
  try{
    await h.mount(Shell);
    await h.waitFor(()=>{try{return !!h.viewer.treePane?.listProps?.onFocus&&!h.viewer.treePane.listProps.disabled;}catch{return false;}});
    await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-0',{epoch_uuid:'epoch-0',cell_uuid:'cell-0'}));
    await ready(h);await h.settle(100);
    const token=()=>h.viewer.treePane.listProps.source.readContext.candidate_scope_revision;
    assert.equal(token(),'scope-one');
    if(kind==='cell'){await h.act(()=>h.viewer.treePane.listProps.onSelectCell(cell,{epoch_uuid:'epoch-0',cell_uuid:'cell-0'}));await ready(h);}
    const clock={...h.fixture.clock},mounts=h.fixture.mounts,before=h.fixture.requests.length;
    await save(h,`${kind} note`);await h.settle(300);
    const calls=h.fixture.requests.slice(before);
    const write=calls.find(call=>call.path==='/annotations');
    assert.equal(write?.body.target_kind,kind);
    assert.deepEqual(workbenchReads(calls),[],'no queue, context, page, tree or manifest re-read');
    assert.equal(h.fixture.clock.reviewRevision,clock.reviewRevision,'the tag receipt does not tick the Workbench clock');
    if(kind==='epoch')assert.deepEqual(h.fixture.clock,clock,'an epoch receipt does not tick the app clock');
    assert.equal(token(),'scope-one','the frozen read token is not renewed');
    assert.equal(h.fixture.mounts,mounts,'the frozen browser is not remounted');
    assert.equal(input(h).props.disabled,false,'the tag editor is not relocked');
    const shown=kind==='cell'?h.viewer.epoch.annotations.cell_tags:h.viewer.epoch.annotations.epoch_tags;
    assert.deepEqual(shown.map(chip=>chip.tag),[`${kind} note`]);
  }finally{await h.close();}
});

test('the Workbench clock skips every confirmed tag receipt but not curation, structure or receipt-less tag events',async()=>{
  const h=await createWorkflowHarness();
  try{
    const {useWorkspaceChanges}=await h.module('useWorkspaceChanges.js');let api;
    await h.mount(()=>{api=useWorkspaceChanges();return null;},{});
    const receipt=kind=>({version:1,targets:[{target_kind:kind,target_uuid:`${kind}-0`,revisions:{me:1},tags:[]}]});
    await h.act(()=>api.changed({kind:'annotations',confirmed:receipt('epoch')}));
    await h.act(()=>api.changed({kind:'annotations',tagChannel:true}));
    assert.deepEqual([api.revision,api.structureRevision,api.reviewRevision],[0,0,0]);
    await h.act(()=>api.changed({kind:'annotations',confirmed:receipt('cell')}));
    assert.deepEqual([api.revision,api.structureRevision,api.reviewRevision],[0,0,0],'cell receipts also travel on the tag channel');
    await h.act(()=>api.changed({kind:'annotations'}));
    assert.deepEqual([api.revision,api.structureRevision,api.reviewRevision],[1,0,1],'receipt-less tag events keep the old full refresh');
    await h.act(()=>api.changed({kind:'curation'}));
    assert.deepEqual([api.revision,api.structureRevision,api.reviewRevision],[2,0,2]);
    await h.act(()=>api.changed());
    assert.deepEqual([api.revision,api.structureRevision,api.reviewRevision],[3,1,3]);
  }finally{await h.close();}
});

test('only advertised tag-free read tokens keep page authority across tag receipts',async()=>{
  const {stableTagAuthority}=await import('./annotations/annotationReceipts.js');
  assert.equal(stableTagAuthority({query_revision_contract:'protocol-state-v4'}),true);
  assert.equal(stableTagAuthority({query_revision_contract:'workbench-candidate-scope-v2'}),true);
  for(const protocol of [null,{},{query_revision_contract:'protocol-state-v3'},{query_revision_contract:'workbench-candidate-scope-v1'}])
    assert.equal(stableTagAuthority(protocol),false);
});

for(const variant of ['an older server','a tag filter'])test(`a frozen epoch tag renews the page once for ${variant}`,async()=>{
  const {h,Shell}=await mountedWorkbench();
  try{
    if(variant==='an older server'){const respond=h.fixture.respond;h.fixture.respond=(url,options,fallback)=>{const value=respond(url,options,fallback);
      return value?.protocol?.query_revision_contract?{...value,protocol:{...value.protocol,query_revision_contract:undefined}}:value?.context?.protocol?{...value,context:{...value.context,protocol:{...value.context.protocol,query_revision_contract:undefined}}}:value;};}
    await h.mount(Shell);
    await h.waitFor(()=>{try{return !!h.viewer.treePane?.listProps?.onFocus&&!h.viewer.treePane.listProps.disabled;}catch{return false;}});
    if(variant==='a tag filter'){await h.act(()=>h.viewer.onViewFilters({tagged:'true'}));await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);}
    await h.act(()=>h.viewer.treePane.listProps.onFocus('epoch-0',{epoch_uuid:'epoch-0',cell_uuid:'cell-0'}));
    await ready(h);await h.settle(100);
    const before=h.fixture.requests.length;
    await save(h,'renew');await h.settle(300);
    const reads=workbenchReads(h.fixture.requests.slice(before));
    assert.equal(reads.filter(path=>path.includes('/candidates/union/epochs?')).length,1,reads.join('\n'));
    assert.deepEqual(reads.filter(path=>/\/context|workbench\?|\/prepare/.test(path)),[],'the candidate context and queue are not reloaded');
    assert.equal(h.viewer.treePane.listProps.source.readContext.candidate_scope_revision,'scope-one');
  }finally{await h.close();}
});

for(const name of ['ColumnTree','HierarchyTree'])test(`frozen ${name} re-reads its pages once after a tag burst and live trees never do`,async()=>{
  const h=await createWorkflowHarness();
  const page={revision:'a'.repeat(64),candidate_scope_revision:'scope-1',kind:'branches',path:[],depth:0,offset:0,limit:60,total:1,total_epochs:3,count:3,cells:1,duration_seconds:0,selection:{count:3},split_order:['date'],levels:[{field:'date',label:'Recording date'}],ancestors:[],epochs:[],has_more:false,
    branches:[{key:'group-0',path:['group-0'],label:'Group 0',value:'group-0',count:3,cells:1,duration_seconds:0}]};
  h.fixture.respond=(url,options,fallback)=>url.pathname.endsWith('/tree/page')?{...page,query_revision:'live',expected_binding_version:2}:fallback();
  try{
    const Tree=await h.component(name),{tagStore}=await h.module('annotations/tagStore.js');
    const frozen={setSelectedEpochs:()=>{},protocolId:'protocol-A',readContext:{root:'/protocols/protocol-A/workbench/candidates/c',candidate_scope_revision:'scope-1'},splits:'date',revision:0};
    let mounted=false;
    for(const props of [frozen,{protocolId:'protocol-A',splits:'date',revision:0,expectedRevision:'live'}]){
      if(mounted)await h.render(Tree,props);else await h.mount(Tree,props);
      mounted=true;await h.settle(150);
      const pages=()=>h.fixture.requests.filter(row=>row.path.endsWith('/tree/page')).length,before=pages();
      const receipt=index=>({version:1,targets:[{target_kind:'epoch',target_uuid:`epoch-${index}`,revisions:{author:index+1},tags:[]}]});
      await h.act(()=>{for(let index=0;index<3;index++)tagStore.ingest(receipt(index));});
      await h.settle(300);
      assert.equal(pages()-before,props.readContext?1:0,props.readContext?'one coverage refresh for the burst':'live trees keep their tag-free pages');
      tagStore.reset();await h.settle(150);
    }
  }finally{await h.close();}
});
