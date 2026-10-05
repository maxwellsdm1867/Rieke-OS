import test from 'node:test';
import assert from 'node:assert/strict';
import {createTreeSelectionReader} from './treeSelectionReader.js';

test('documented consumer example preserves sync, Promise and cancellation results',async()=>{
  const page=offset=>({kind:'epochs',revision:'r',path:['opaque'],offset,
    epochs:Array.from({length:60},(_,i)=>({epoch_uuid:`epoch-${offset+i}`}))});
  const reader=createTreeSelectionReader({requestPage:async(_scope,options)=>page(options.offset??0)});
  const scope={expectedRevision:'r'},supplied=page(0);
  const first=await reader.firstEpoch(scope,{path:['opaque'],revision:'r'});
  const samePage=reader.rangeEpochIds(scope,{page:supplied,firstIndex:0,lastIndex:1});
  const pending=reader.rangeEpochIds(scope,{page:supplied,firstIndex:59,lastIndex:60});
  assert.equal(first.epoch_uuid,'epoch-0');
  assert.equal(Array.isArray(samePage),true);assert.deepEqual(samePage,['epoch-0','epoch-1']);
  assert.equal(pending instanceof Promise,true);assert.deepEqual(await pending,['epoch-59','epoch-60']);
  const controller=new AbortController();controller.abort();
  await assert.rejects(reader.firstEpoch(scope,{path:['opaque'],signal:controller.signal}),{name:'AbortError'});
  assert.throws(()=>reader.rangeEpochIds(scope,{page:supplied,firstIndex:0,lastIndex:0,signal:controller.signal}),{name:'AbortError'});
});

function deferred(){let resolve;const promise=new Promise(yes=>{resolve=yes;});return {promise,resolve};}

test('first epoch cancellation between transport completion and reader continuation still rejects',async()=>{
  const controller=new AbortController();
  const reader=createTreeSelectionReader({requestPage:()=>{
    queueMicrotask(()=>queueMicrotask(()=>controller.abort()));
    return Promise.resolve(page(0,[{epoch_uuid:'late'}]));
  }});
  await assert.rejects(reader.firstEpoch({}, {path:[],signal:controller.signal}),{name:'AbortError'});
});
const page=(offset,epochs,revision='r')=>({kind:'epochs',revision,path:['opaque'],offset,epochs});

test('empty first branches return undefined without searching later siblings',async()=>{
  for(const empty of [{kind:'branches',revision:'r',branches:[]},page(0,[])]){
    const reader=createTreeSelectionReader({requestPage:async(_scope,{path})=>{
      if(path[0]==='cell')return {kind:'branches',revision:'r',branches:[{path:['empty']},{path:['populated']}]};
      assert.deepEqual(path,['empty']);return empty;
    }});
    assert.equal(await reader.firstEpoch({}, {path:['cell']}),undefined);
  }
});

test('discovered revision pins descendants and supplied revision mismatch fails immediately',async()=>{
  const seen=[];
  const reader=createTreeSelectionReader({requestPage:async(_scope,{path,currentRevision})=>{
    seen.push(currentRevision);
    return path.length? page(0,[{epoch_uuid:'first'}]):{kind:'branches',revision:'r',branches:[{path:['leaf']}]};
  }});
  assert.deepEqual(await reader.firstEpoch({}, {path:[]}),{epoch_uuid:'first'});
  assert.deepEqual(seen,[undefined,'r']);
  await assert.rejects(reader.firstEpoch({}, {path:[],revision:'wrong'}),{message:'Tree changed. Select the cell again.'});
});

test('transport errors retain their original object for both selection operations',async()=>{
  const failure=Object.assign(new Error('Backend unavailable'),{status:409,data:{error:'unchanged'}});
  const reader=createTreeSelectionReader({requestPage:async()=>{throw failure;}});
  await assert.rejects(reader.firstEpoch({}, {path:[]}),error=>error===failure);
  await assert.rejects(reader.rangeEpochIds({}, {page:page(60,[]),firstIndex:0,lastIndex:1}),error=>error===failure);
});

test('already canceled selection starts no transport and cancellation stops further pages',async()=>{
  const controller=new AbortController();controller.abort();
  const reader=createTreeSelectionReader({requestPage:()=>{throw Error('Canceled work must not fetch');}});
  await assert.rejects(reader.firstEpoch({}, {path:[],signal:controller.signal}),{name:'AbortError'});
  assert.throws(()=>reader.rangeEpochIds({}, {page:page(0,[{epoch_uuid:'a'}]),firstIndex:0,lastIndex:0,signal:controller.signal}),{name:'AbortError'});
  for(const kind of ['cell','range']){
    const pending=deferred(),abort=new AbortController(),requests=[];
    const late=createTreeSelectionReader({requestPage:(_scope,options,signal)=>{assert.equal(signal,abort.signal);requests.push(options);return pending.promise;}});
    const result=kind==='cell'?late.firstEpoch({}, {path:[],signal:abort.signal})
      :late.rangeEpochIds({}, {page:page(120,[{epoch_uuid:'last'}]),firstIndex:0,lastIndex:120,signal:abort.signal});
    abort.abort();pending.resolve(kind==='cell'?{kind:'branches',revision:'r',branches:[{path:['later']}]}:page(0,Array.from({length:60},()=>({epoch_uuid:'earlier'}))));
    await assert.rejects(result,{name:'AbortError'});assert.equal(requests.length,1);
  }
});

test('range completeness and revision checks also cover the supplied page',()=>{
  const reader=createTreeSelectionReader({requestPage:()=>{throw Error('Supplied page should not fetch');}});
  assert.throws(()=>reader.rangeEpochIds({}, {page:page(0,[{epoch_uuid:'a'}]),firstIndex:0,lastIndex:1}),{message:'Could not load the complete range.'});
  assert.throws(()=>reader.rangeEpochIds({}, {page:{...page(0,[]),kind:'branches'},firstIndex:0,lastIndex:0}),{message:'Tree changed. Select the range again.'});
});

test('default transport preserves recorded, predicate and workbench HTTP envelopes and signals',async()=>{
  const prior=globalThis.fetch,seen=[],controller=new AbortController();
  globalThis.fetch=async(url,options)=>{seen.push({url,method:options.method,signal:options.signal,body:JSON.parse(options.body)});return {ok:true,json:async()=>page(0,[{epoch_uuid:'first'}],'expected')};};
  const filters={number:0,empty:null},predicate={all:[{field:'x',value:false}]};
  try{
    const reader=createTreeSelectionReader();
    for(const scope of [
      {protocolId:'protocol',filters,splits:'date,cell',expectedRevision:'expected'},
      {predicate,filters,splits:'date,cell',expectedRevision:'expected'},
      {protocolId:'ignored',predicate,readContext:{root:'/workbench/session',candidate_scope_revision:'candidate'},filters,splits:'date,cell',expectedRevision:'expected'},
    ])await reader.firstEpoch(scope,{path:['opaque'],revision:'older',signal:controller.signal});
    const common={filters,splits:'date,cell',path:['opaque'],offset:0,limit:60,revision:'expected'};
    assert.deepEqual(seen,[
      {url:'/api/tree-pages',method:'POST',signal:controller.signal,body:{protocol_uuid:'protocol',...common}},
      {url:'/api/tree-pages',method:'POST',signal:controller.signal,body:{predicate,...common}},
      {url:'/api/workbench/session/tree/page',method:'POST',signal:controller.signal,body:{candidate_scope_revision:'candidate',...common}},
    ]);
  }finally{globalThis.fetch=prior;}
});

test('range allows exactly 1,000 positions and rejects larger selection before transport',async()=>{
  const reader=createTreeSelectionReader({requestPage:async(_scope,{offset})=>page(offset,Array.from({length:60},(_,i)=>({epoch_uuid:`id-${offset+i}`})))});
  const supplied=page(0,Array.from({length:60},(_,i)=>({epoch_uuid:`id-${i}`})));
  const ids=await reader.rangeEpochIds({}, {page:supplied,firstIndex:0,lastIndex:999});
  assert.equal(ids.length,1000);assert.equal(ids[0],'id-0');assert.equal(ids.at(-1),'id-999');
  assert.throws(()=>reader.rangeEpochIds({}, {page:supplied,firstIndex:0,lastIndex:1000}),{message:'Select at most 1,000 epochs.'});
});

test('range rejects a changed revision, non-epoch page or missing selected row',async()=>{
  for(const [part,message] of [
    [page(0,[{epoch_uuid:'stale'}],'wrong'),'Tree changed. Select the range again.'],
    [{...page(0,[]),kind:'branches'},'Tree changed. Select the range again.'],
    [page(0,[]),'Could not load the complete range.'],
  ]){
    const reader=createTreeSelectionReader({requestPage:async()=>part});
    await assert.rejects(async()=>reader.rangeEpochIds({}, {page:page(60,[{epoch_uuid:'last'}]),firstIndex:0,lastIndex:60}),{message});
  }
});

test('same-page range returns a synchronous array in server order without fetching',()=>{
  const reader=createTreeSelectionReader({requestPage:()=>{throw Error('Supplied page must be reused');}});
  const ids=reader.rangeEpochIds({}, {page:page(60,[{epoch_uuid:'z'},{epoch_uuid:'a'},{epoch_uuid:'m'}]),firstIndex:60,lastIndex:62});
  assert.deepEqual(ids,['z','a','m']);
});

test('range assembles fetched and supplied pages in exact position order',async()=>{
  const early=Array.from({length:60},(_,i)=>({epoch_uuid:`filler-${i}`}));
  early[58]={epoch_uuid:'z'};early[59]={epoch_uuid:'b'};
  const reader=createTreeSelectionReader({requestPage:async(_scope,options)=>{
    assert.deepEqual(options,{path:['opaque'],offset:0,currentRevision:'r'});
    return page(0,early);
  }});
  assert.deepEqual(await reader.rangeEpochIds({}, {page:page(60,[{epoch_uuid:'a'},{epoch_uuid:'y'}]),firstIndex:58,lastIndex:61}),['z','b','a','y']);
});

test('first epoch rejects cancellation after an ignoring transport completes',async()=>{
  const pending=deferred(),controller=new AbortController();
  const reader=createTreeSelectionReader({requestPage:()=>pending.promise});
  const result=reader.firstEpoch({}, {path:[],signal:controller.signal});
  controller.abort('caller reason');pending.resolve({kind:'epochs',revision:'r',epochs:[{epoch_uuid:'late'}]});
  await assert.rejects(result,{name:'AbortError'});
});

test('first epoch follows only the first branch and preserves its exact recorded DTO',async()=>{
  const epoch={epoch_uuid:'z-first',cell_uuid:'cell',value:null,zero:0,flag:false,large:'9007199254740993'};
  const pages=new Map([
    ['cell',{kind:'branches',revision:'r',branches:[{path:['first']},{path:['second']}]}],
    ['first',{kind:'epochs',revision:'r',epochs:[epoch,{epoch_uuid:'a-second'}]}],
  ]);
  const reader=createTreeSelectionReader({requestPage:async(_scope,{path})=>pages.get(path[0])});
  assert.equal(await reader.firstEpoch({}, {path:['cell'],revision:'r'}),epoch);
});

test('first epoch pins expected, supplied or discovered revision and rejects a changed later page',async()=>{
  for(const scope of [{expectedRevision:'expected'},{}]){
    const revision=scope.expectedRevision||'supplied';
    const reader=createTreeSelectionReader({requestPage:async(_scope,{path,currentRevision})=>path[0]==='cell'
      ?{kind:'branches',revision,branches:[{path:['leaf']}]}
      :{kind:'epochs',revision:'changed',epochs:[{epoch_uuid:'wrong'}]}});
    await assert.rejects(reader.firstEpoch(scope,{path:['cell'],revision:'supplied'}),{message:'Tree changed. Select the cell again.'});
  }
});
