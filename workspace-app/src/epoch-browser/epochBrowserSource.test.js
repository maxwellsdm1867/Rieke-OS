import test from 'node:test';
import assert from 'node:assert/strict';
import {epochPageRequest,epochPageRevision,loadProtocolSelection} from './epochBrowserSource.js';

test('all/cell selection collects complete filtered pages rather than a displayed cell window',async()=>{
 const source={kind:'protocol',protocolId:'pin',query:'cell_type=ON',queryRevision:'q',bindingVersion:4},calls=[];
 const request=async path=>{calls.push(path);const query=new URLSearchParams(path.split('?')[1]),offset=Number(query.get('offset'));
  assert.equal(query.get('cell_type'),'ON');assert.equal(query.get('limit'),'60');assert.equal(query.get('cell_uuid'),'cell');
  assert.equal(query.get('selection_receipt'),'true');
  return {selection_revision:'selected-q',query_revision:'q',expected_binding_version:4,total:65,offset,epochs:Array.from({length:Math.min(60,65-offset)},(_,i)=>({epoch_uuid:`e-${offset+i}`,cell_uuid:'cell'}))};
 };
 assert.deepEqual(await loadProtocolSelection({source,request,cellUuid:'cell'}),Array.from({length:65},(_,i)=>`e-${i}`));
 assert.equal(calls.length,2);
 assert.deepEqual(await loadProtocolSelection({source,request:async()=>({selection_revision:'selected-q',query_revision:'q',expected_binding_version:4,total:0,offset:0,epochs:[]})}),[]);
});

test('complete selection refuses oversized, changed, missing, duplicate and out-of-cell pages',async()=>{
 const source={kind:'protocol',protocolId:'pin',queryRevision:'q',bindingVersion:4};
 for(const failure of ['oversized','query','binding','total','short','duplicate','cell','retired','tags','missing-witness']){
  let calls=0,current=true;
  await assert.rejects(loadProtocolSelection({source,cellUuid:'cell',isCurrent:()=>current,request:async()=>{
   const offset=calls++*60,total=failure==='oversized'?1001:61;
   const page={selection_revision:'selected-q',query_revision:'q',expected_binding_version:4,total,offset,epochs:Array.from({length:Math.min(60,total-offset)},(_,i)=>({epoch_uuid:`e-${offset+i}`,cell_uuid:'cell'}))};
   if(calls===2){
    if(failure==='query')page.query_revision='other';if(failure==='binding')page.expected_binding_version=5;
    if(failure==='total')page.total=62;if(failure==='short')page.epochs=[];
    if(failure==='duplicate')page.epochs[0].epoch_uuid='e-0';if(failure==='cell')page.epochs[0].cell_uuid='other';
    if(failure==='retired')current=false;
    if(failure==='tags')page.selection_revision='changed-tags';if(failure==='missing-witness')delete page.selection_revision;
   }
   return page;
  }}),undefined,failure);
  assert.equal(calls,failure==='oversized'?1:2,failure);
 }
 const controller=new AbortController();controller.abort();
 await assert.rejects(loadProtocolSelection({source,signal:controller.signal,request:()=>assert.fail('No retired read')}),{name:'AbortError'});
});

test('shared browser preserves protocol filters and locates cell pages by UUID',()=>{
 const source={kind:'protocol',protocolId:'saved',query:'group_label=NBQX&cell_type=ON'};
 const {path}=epochPageRequest(source,{cellUuid:'same-label-different-date',offset:60});
 const query=new URLSearchParams(path.split('?')[1]);
 assert.equal(query.get('group_label'),'NBQX');assert.equal(query.get('cell_type'),'ON');
 assert.equal(query.get('cell_uuid'),'same-label-different-date');assert.equal(query.get('offset'),'60');
 const anchored=epochPageRequest(source,{anchorUuid:'e',offset:120});
 assert.ok(anchored.path.includes('anchor_uuid=e'));assert.ok(!anchored.path.includes('offset='));
});
test('shared predicate pages retain exact predicate and revision when expanding a cell or locating an epoch',()=>{
 const predicate={field:'parameters/history1',operator:'eq',value:[1,2]};
 const source={kind:'predicate',predicate,splits:'date,cell',treeRevision:'verified'};
 const cell=epochPageRequest(source,{cellUuid:'cell-c',offset:60});
 assert.equal(cell.path,'/explore/epochs');assert.equal(cell.options.method,'POST');
 assert.deepEqual(cell.options.body,{predicate,splits:'date,cell',revision:'verified',limit:60,offset:60,cell_uuid:'cell-c'});
 const overview=epochPageRequest(source,{anchorUuid:'epoch-d',includeCells:true});
 assert.equal(overview.options.body.anchor_uuid,'epoch-d');assert.equal(overview.options.body.include_cells,true);
 assert.ok(!Object.hasOwn(overview.options.body,'offset'));assert.deepEqual(overview.options.body.predicate,predicate);
});
test('protocol and predicate revisions retain their source-specific receipt contracts',()=>{
 const protocol={kind:'protocol',queryRevision:'protocol-A'},predicate={kind:'predicate',treeRevision:'explorer-A'};
 assert.equal(epochPageRevision(protocol,{query_revision:'protocol-A',revision:'other'}),'protocol-A');
 assert.equal(epochPageRevision(predicate,{revision:'explorer-A',query_revision:'other'}),'explorer-A');
 for(const page of [{query_revision:'protocol-B'},{revision:'protocol-A'},{}])assert.throws(()=>epochPageRevision(protocol,page),/epoch list (is out of date|could not be verified)/);
 for(const page of [{revision:'explorer-B'},{query_revision:'explorer-A'},{}])assert.throws(()=>epochPageRevision(predicate,page),/epoch list (is out of date|could not be verified)/);
 assert.equal(epochPageRevision({kind:'protocol'},{query_revision:'observed'}),'observed');
});

test('predicate pages bound the cell list when asked: cells_limit and cells_after',async()=>{
  const {epochPageRequest}=await import('./epochBrowserSource.js');
  const source={kind:'predicate',predicate:{all:[]},splits:'date,cell',treeRevision:'R'};
  assert.equal(epochPageRequest(source,{includeCells:true}).options.body.cells_limit,undefined,'old behaviour without a limit');
  const first=epochPageRequest(source,{includeCells:true,cellsLimit:200}).options.body;
  assert.deepEqual([first.cells_limit,first.cells_after],[200,undefined]);
  const next=epochPageRequest(source,{includeCells:true,cellsLimit:200,cellsAfter:200}).options.body;
  assert.deepEqual([next.cells_limit,next.cells_after],[200,200]);
  assert.equal(epochPageRequest(source,{cellsLimit:200}).options.body.cells_limit,undefined,'no cell window without include_cells');
});


test('stale receipt is recoverable but missing receipt is an integrity failure',()=>{
 const source={kind:'protocol',protocolId:'p',queryRevision:'before'};
 assert.throws(()=>epochPageRevision(source,{query_revision:'after'}),error=>error.code==='epoch_list_stale');
 assert.throws(()=>epochPageRevision(source,{}),error=>!error.code);
});
