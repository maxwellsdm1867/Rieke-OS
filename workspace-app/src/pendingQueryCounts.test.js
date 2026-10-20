import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

const priorResize=globalThis.ResizeObserver;
test.before(()=>{globalThis.ResizeObserver=class{observe(){} disconnect(){}};});
test.after(()=>{if(priorResize)globalThis.ResizeObserver=priorResize;else delete globalThis.ResizeObserver;});

const text=node=>typeof node==='string'?node:(node.children||[]).map(text).join(' ');
const row=(n,cell)=>({epoch_uuid:`epoch-${n}`,cell_uuid:cell,cell_label:cell==='cell-a'?'Cell A':'Cell B',date:'2026-09-29',start_time:`2026-09-29T10:00:0${n}`,protocol_name:'p.Noise'});
const cells=[0,1,2,3].map(i=>({cell_uuid:`cell-${'abcd'[i]}`,label:`Cell ${'ABCD'[i]}`,date:'2026-09-29',cell_type:'ON',epochs:2}));
// A multi-field query: rows at once, totals and the cell list pending one counts job.
function backend(h,{jobFor=()=>'counts-1',readyAfter=1}={}){
 const state={polls:{},cancels:[],pages:[]};
 h.fixture.respond=(url,options,fallback)=>{
  const path=url.pathname,body=options.body?JSON.parse(options.body):{};
  if(path==='/api/explore/epochs'){
   state.pages.push(body);const job=jobFor(body),ready=(state.polls[job]||0)>readyAfter;
   if(!ready)return {revision:body.revision,offset:0,epochs:[row(0,'cell-a'),row(1,'cell-a'),row(2,'cell-b')],total:null,has_more:true,cells_pending:true,counts:{status:'pending',request_id:job}};
   const after=body.cells_after||0,window=cells.slice(after,after+2);
   return {revision:body.revision,offset:0,epochs:[row(0,'cell-a'),row(1,'cell-a'),row(2,'cell-b')],total:8,has_more:true,cells:window,cells_total:4,cells_next:after+2<4?after+2:null,counts:{status:'ready',request_id:job}};
  }
  const poll=path.match(/^\/api\/explore\/summaries\/([^/]+)$/);
  if(poll){const id=poll[1];state.polls[id]=(state.polls[id]||0)+1;return state.polls[id]>readyAfter?{request_id:id,status:'ready',result:{matched_count:8,cell_count:4}}:{request_id:id,status:'pending'};}
  const cancel=path.match(/^\/api\/explore\/summaries\/([^/]+)\/cancel$/);
  if(cancel){state.cancels.push(cancel[1]);return {status:'cancelled'};}
  return fallback();
 };
 return state;
}
const props=(predicate,revision)=>({projectId:'project-A',predicate,splits:['date','cell'],preview:{tree_revision:revision,matched_count:null,catalog:{fields:[]}},onSession(){}});

test('multi-field results show rows with pending counts, poll one counts job, then fill exact counts and a bounded cell list',async()=>{
 const h=await createWorkflowHarness({total:20,liveMetadata:false,realTreePane:true}),state=backend(h);
 try{
  const MatchingEpochs=await h.component('MatchingEpochs');
  await h.mount(MatchingEpochs,props({all:[{field:'cell_type',operator:'eq',value:'ON'},{field:'parameters/x',operator:'gt',value:1}]},'R1'));
  await h.waitFor(()=>state.pages.length>=1&&h.root.findAllByProps({className:'pending-epoch-rows'}).length===1);
  assert.equal(state.pages[0].cells_limit,200,'the cell list is requested in bounded windows');assert.equal(state.pages[0].include_cells,true);
  const pending=h.root.findByProps({className:'pending-epoch-rows'});
  assert.equal(pending.findAllByType('button').length,3,'rows show before counts exist');
  assert.match(text(pending.findByProps({role:'status'})),/Counting/);
  await h.waitFor(()=>h.root.findAllByProps({className:'inspection-cells-window'}).length===1,{timeout:5000});
  const jobs=h.fixture.requests.filter(r=>r.path.startsWith('/explore/summaries'));
  assert.ok(jobs.every(r=>r.method==='GET'&&r.path==='/explore/summaries/counts-1'),'exactly one counts job is polled and none is submitted');
  assert.equal(h.root.findAllByProps({className:'pending-epoch-rows'}).length,0);
  const window=()=>h.root.findByProps({className:'inspection-cells-window'});
  assert.match(text(window()),/2 of 4 cells/);
  const before=state.pages.length;
  await h.act(()=>window().findByType('button').props.onClick());
  await h.waitFor(()=>/4 of 4 cells/.test(text(window())));
  assert.equal(state.pages.length,before+1);assert.equal(state.pages.at(-1).cells_after,2);assert.equal(state.pages.at(-1).cells_limit,200);
  assert.equal(window().findAllByType('button').length,0,'no further window at the end');
 }finally{await h.close();}
});

test('a query change cancels the pending counts job of the previous query',async()=>{
 const h=await createWorkflowHarness({total:20,liveMetadata:false,realTreePane:true}),state=backend(h,{jobFor:body=>body.revision==='R1'?'counts-1':'counts-2',readyAfter:1000});
 try{
  const MatchingEpochs=await h.component('MatchingEpochs');
  await h.mount(MatchingEpochs,props({any:[{field:'cell_type',operator:'eq',value:'ON'},{field:'parameters/x',operator:'gt',value:1}]},'R1'));
  await h.waitFor(()=>(state.polls['counts-1']||0)>=1);
  await h.render(MatchingEpochs,props({any:[{field:'cell_type',operator:'eq',value:'OFF'},{field:'parameters/x',operator:'gt',value:2}]},'R2'));
  await h.waitFor(()=>state.cancels.includes('counts-1')&&(state.polls['counts-2']||0)>=1,{timeout:5000});
  assert.deepEqual(state.cancels,['counts-1']);
 }finally{await h.close();}
});

test('single-field results keep instant totals and start no counts job',async()=>{
 const h=await createWorkflowHarness({total:20,liveMetadata:false,realTreePane:true});
 const pages=[];
 h.fixture.respond=(url,options,fallback)=>{if(url.pathname==='/api/explore/epochs'){const body=JSON.parse(options.body);pages.push(body);return {revision:body.revision,offset:0,epochs:[row(0,'cell-a')],total:1,has_more:false,cells:[cells[0]],cells_total:1,cells_next:null};}return fallback();};
 try{
  const MatchingEpochs=await h.component('MatchingEpochs');
  await h.mount(MatchingEpochs,{...props({all:[{field:'cell_type',operator:'eq',value:'ON'}]},'R1'),preview:{tree_revision:'R1',matched_count:1,catalog:{fields:[]}}});
  await h.waitFor(()=>h.root.findAllByProps({className:'inspection-cells-window'}).length===1);
  assert.equal(h.fixture.requests.filter(r=>r.path.startsWith('/explore/summaries')).length,0);
  assert.equal(pages.length,1);assert.match(text(h.root.findByProps({className:'inspection-cells-window'})),/1 of 1 cells/);
 }finally{await h.close();}
});
