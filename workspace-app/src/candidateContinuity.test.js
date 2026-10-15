import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';
import {frozenPresentationScope,frozenReadPath,frozenTreePresentationScope} from './epoch-browser/frozenReadContext.js';
const root='/protocols/protocol-A/workbench/candidates/candidate-A';
const cohort=(route=root,binding=2)=>JSON.stringify([route,'immutable-recipe-A',binding]);
function props(token='token-A',revision=0,route=root,binding=2){return {
 protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:token,expected_binding_version:binding,cells:[]},projectId:'project',filters:{},revision,
 readContext:{root:route,candidate_scope_revision:token,cohort_key:cohort(route,binding)},initialEpochUuid:'epoch-8',onChange(){},onReviewDecision:async()=>{}
};}
function attach(h,{missing=false,failure=false,shifted=false}={}){
 h.fixture.respond=(url,options,fallback)=>{
  const match=url.pathname.match(/^\/api\/protocols\/protocol-A\/workbench\/candidates\/[^/]+(.*)$/);
  if(!match)return fallback();
  const token=url.searchParams.get('candidate_scope_revision');assert.ok(token);
  url.pathname=match[1].startsWith('/epochs/epoch-')?'/api'+match[1]:'/api/protocols/protocol-A'+match[1];
  let value=fallback();
  if(shifted&&token==='token-B'&&value.epochs){
   const limit=Number(url.searchParams.get('limit')||60),requested=Number(url.searchParams.get('offset')||0),anchor=url.searchParams.get('anchor_uuid');
   url.searchParams.delete('anchor_uuid');url.searchParams.set('offset','0');url.searchParams.set('limit',String(h.fixture.total));
   const full=fallback(),ordered=full.epochs.filter(row=>row.epoch_uuid!=='epoch-8');
   ordered.splice(90,0,full.epochs.find(row=>row.epoch_uuid==='epoch-8'));
   const offset=anchor?Math.floor(ordered.findIndex(row=>row.epoch_uuid===anchor)/60)*60:requested;
   value={...full,limit,offset,epochs:ordered.slice(offset,offset+limit)};
  }
  const epoch=record=>({...record,review_decision:{selected:true,reviewed:token==='token-B',excluded:false}});
  if(value.epochs){
   if(missing&&token==='token-B'&&url.searchParams.has('anchor_uuid'))return failure?{failure:typeof failure==='number'?failure:404,error:failure===503?'Temporary read failure':'Epoch is outside this frozen filtered scope'}:{...value,query_revision:token,epochs:[]};
   return {...value,query_revision:token,epochs:value.epochs.filter(row=>!missing||token!=='token-B'||row.epoch_uuid!=='epoch-8').map(epoch)};
  }
  return value.epoch_uuid?epoch(value):value;
 };
}
const inspectRow=(h,ordinal)=>h.root.findAllByType('button').find(node=>node.props['aria-label']?.startsWith('Inspect ')&&node.props['aria-label'].endsWith(` epoch ${ordinal}`));
async function openCell(h){
 const date=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date');await h.act(()=>date.props.onToggle({currentTarget:{open:true}}));
 const cell=h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell');await h.act(()=>cell.props.onToggle({currentTarget:{open:true}}));
 await h.waitFor(()=>!!inspectRow(h,9));return {date,cell};
}

test('explicit cohort presentation key never replaces fresh read token and resets without evidence',()=>{
 const a=props().readContext,b={...a,candidate_scope_revision:'token-B'};
 assert.equal(frozenPresentationScope(a,'protocol-A','candidate_scope_revision=token-A'),frozenPresentationScope(b,'protocol-A','candidate_scope_revision=token-B'));
 assert.match(frozenReadPath(b,'protocol-A','/epochs'),/candidate_scope_revision=token-B/);
 assert.notEqual(frozenPresentationScope({...a,cohort_key:undefined},'protocol-A','candidate_scope_revision=token-A'),frozenPresentationScope({...b,cohort_key:undefined},'protocol-A','candidate_scope_revision=token-B'));
 assert.notEqual(frozenPresentationScope(a,'protocol-A','tag=A'),frozenPresentationScope(b,'protocol-A','tag=B'));
});

test('frozen tree continuity excludes annotation-dependent filters and grouping and retains owner boundaries',()=>{
 const base={projectId:'p',protocolId:'protocol-A',readContext:{...props().readContext,actor:'a'},filters:{},splits:'date,cell,block'};
 const scope=frozenTreePresentationScope(base);assert.ok(scope);
 assert.equal(frozenTreePresentationScope({...base,revision:7,readContext:{...base.readContext,candidate_scope_revision:'new'}}),scope);
 for(const filters of [{tag:'a'},{tagged:'true'},{tag_predicate:'{}'},{metadata_predicate:JSON.stringify({not:{field:'annotations/epoch/tags',operator:'contains',value:'a'}})}])assert.equal(frozenTreePresentationScope({...base,filters}),null);
 for(const splits of ['annotations/epoch/tags','date,curation/p/tags'])assert.equal(frozenTreePresentationScope({...base,splits}),null);
 for(const changed of [{projectId:'other'},{filters:{cell_type:'ON'}},{splits:'cell,date'},
  {readContext:{...base.readContext,actor:'b'}},{readContext:{...base.readContext,cohort_key:'other'}},{expectedRevision:'explicit'}])assert.notEqual(frozenTreePresentationScope({...base,...changed}),scope);
 assert.equal(frozenTreePresentationScope({...base,readContext:{...base.readContext,cohort_key:null}}),null);
});

test('draft token advance keeps focus/date/cell/row nodes, old rows inert, and uses fresh authority once ready',async()=>{
 const h=await createWorkflowHarness({total:100});attach(h);const mutations=[];
 try{
  const Inspector=await h.component('Inspector'),initial={...props(),onReviewDecision:async body=>mutations.push(body)};
  await h.mount(Inspector,initial);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  const nodes=await openCell(h),row=inspectRow(h,9),listKey=h.viewer.treePane.listKey;
  const oldReview=h.viewer.detailExtras.props.onReview;
  h.fixture.delay=record=>record.path.includes('token-B')?140:0;
  await h.render(Inspector,{...initial,...props('token-B',1)});
  assert.equal(h.viewer.treePane.listKey,listKey);
  assert.equal(h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-date'),nodes.date);
  assert.equal(h.root.findAllByType('details').find(node=>node.props.className==='cell-tree-cell'),nodes.cell);
  assert.equal(nodes.date.props.open,true);assert.equal(nodes.cell.props.open,true);assert.equal(inspectRow(h,9),row);
  assert.ok(h.root.findAllByType('div').some(node=>node.props.className==='stable-content-body'&&node.props.inert===true));
  assert.equal(h.viewer.treePane.listProps.navigationDisabled,true);assert.equal(h.viewer.epoch,null);
  await h.act(()=>oldReview(true));assert.deepEqual(mutations,[]);
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  assert.equal(h.viewer.epoch.review_decision.reviewed,true);assert.equal(inspectRow(h,9),row);
  assert.equal(h.viewer.treePane.listProps.source.queryRevision,'token-B');
  assert.equal(h.fixture.requests.filter(record=>record.path.includes('token-B')&&record.path.includes('cell_uuid=cell-0')).length,1);
 }finally{await h.close();}
});

test('late prior-token reads cannot repaint the latest same-cohort focus or decision',async()=>{
 const h=await createWorkflowHarness({total:100});attach(h);
 try{
  const Inspector=await h.component('Inspector');await h.mount(Inspector,props());await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);await openCell(h);
  h.fixture.delay=record=>record.path.includes('token-B')?200:0;
  await h.render(Inspector,props('token-B',1));await h.settle(20);await h.render(Inspector,props('token-C',2));
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  await h.settle(230);assert.equal(h.viewer.epoch.review_decision.reviewed,false);assert.equal(h.viewer.treePane.listProps.source.queryRevision,'token-C');
  assert.ok(h.fixture.requests.some(record=>record.path.includes('token-B')&&record.aborted));
 }finally{await h.close();}
});

test('new root, binding, recipe, filters or absent cohort evidence reset focus and reject retained candidate review',async()=>{
 for(const change of ['root','binding','recipe','filter','absent']){
  const h=await createWorkflowHarness({total:100});attach(h);const mutations=[];
  try{
   const Inspector=await h.component('Inspector'),initial={...props(),onReviewDecision:async body=>mutations.push(body)};
   await h.mount(Inspector,initial);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
   const old=h.viewer.detailExtras.props.onReview;
   const next={...initial,...(change==='root'?props('token-A',0,root.replace('candidate-A','candidate-B')):change==='binding'?props('token-B',1,root,3):change==='filter'?{filters:{tag:'B'}}:{readContext:{...initial.readContext,candidate_scope_revision:'token-B',cohort_key:change==='absent'?undefined:JSON.stringify([root,'different-recipe',2])},revision:1})};
   await h.render(Inspector,next);await h.waitFor(()=>!h.viewer.treePane.listProps.disabled);
   await h.act(()=>old(true));assert.deepEqual(mutations,[],change);assert.equal(h.viewer.epoch,null,change);
  }finally{await h.close();}
 }
});

test('restored focus absent from refreshed scope locates once then clears on missing 200 and 404',async()=>{
 for(const failure of [false,true]){
  const h=await createWorkflowHarness({total:100});attach(h,{missing:true,failure});
  try{
   const Inspector=await h.component('Inspector');await h.mount(Inspector,props());await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
   await h.render(Inspector,props('token-B',1));
   await h.waitFor(()=>h.fixture.requests.some(record=>record.path.includes('anchor_uuid=epoch-8')&&record.completed));await h.settle(120);
   assert.equal(h.viewer.epoch,null);assert.equal(h.viewer.resource.loading,false);
   assert.equal(h.fixture.requests.filter(record=>record.path.includes('anchor_uuid=epoch-8')).length,1);
   assert.ok(h.root.findAllByProps({role:'alert'}).length);assert.equal(h.viewer.detailExtras,null);
  }finally{await h.close();}
 }
});

test('temporary focus-locator failure preserves the UUID and recovers only after explicit retry',async()=>{
 const h=await createWorkflowHarness({total:100});attach(h,{missing:true,failure:503});const saved=[];
 try{
  const Inspector=await h.component('Inspector');
  await h.mount(Inspector,{...props(),onSessionChange:value=>saved.push(value)});
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  await h.render(Inspector,{...props('token-B',1),onSessionChange:value=>saved.push(value)});
  await h.waitFor(()=>h.root.findAllByType('button').some(button=>button.children.includes('Refresh epoch list')));
  assert.equal(saved.at(-1).focused,'epoch-8');assert.equal(h.viewer.treePane.listProps.disabled,true);
  assert.equal(h.fixture.requests.filter(record=>record.path.includes('anchor_uuid=epoch-8')).length,1);
  attach(h);
  await h.act(()=>h.root.findAllByType('button').find(button=>button.children.includes('Refresh epoch list')).props.onClick());
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  assert.equal(saved.at(-1).focused,'epoch-8');
 }finally{await h.close();}
});


test('focused UUID shifted to another refreshed page is located once without retargeting or mutation',async()=>{
 const h=await createWorkflowHarness({total:100});attach(h,{shifted:true});const mutations=[];
 try{
  const Inspector=await h.component('Inspector'),initial={...props(),onReviewDecision:async body=>mutations.push(body)};
  await h.mount(Inspector,initial);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&!h.viewer.treePane.listProps.disabled);
  await h.render(Inspector,{...initial,...props('token-B',1)});
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-8'&&h.viewer.navigation.position===90&&!h.viewer.treePane.listProps.disabled);
  assert.equal(h.viewer.epoch.review_decision.reviewed,true);assert.equal(h.viewer.treePane.listProps.source.queryRevision,'token-B');
  assert.equal(h.fixture.requests.filter(record=>record.path.includes('anchor_uuid=epoch-8')).length,1);assert.deepEqual(mutations,[]);
 }finally{await h.close();}
});

test('clearing focused cell revalidates same-token UUID outside the first all-cell page once',async()=>{
 const h=await createWorkflowHarness({total:650});attach(h);const mutations=[];
 try{
  const Inspector=await h.component('Inspector'),initial={...props(),initialEpochUuid:'epoch-508',initialNavigation:{focusCell:'cell-1'},onReviewDecision:async body=>mutations.push(body)};
  await h.mount(Inspector,initial);await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-508'&&!h.viewer.treePane.listProps.disabled);
  const chip=h.viewer.toolbarChildren.props.children.find(child=>child?.props?.className==='inspection-focus-chip');assert.equal(chip.props.className,'inspection-focus-chip');
  await h.act(()=>chip.props.onClick());
  await h.waitFor(()=>h.viewer.epoch?.epoch_uuid==='epoch-508'&&h.viewer.navigation.position===508&&!h.viewer.treePane.listProps.disabled);
  assert.equal(h.fixture.requests.filter(record=>record.path.includes('anchor_uuid=epoch-508')).length,1);
  assert.ok(h.fixture.requests.filter(record=>record.path.includes('anchor_uuid=epoch-508')).every(record=>!record.path.includes('cell_uuid=')));
  assert.deepEqual(mutations,[]);
 }finally{await h.close();}
});
