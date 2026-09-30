import test from 'node:test';
import assert from 'node:assert/strict';
import {saveCurationSelection} from './curationSelection.js';
import {deferred} from './test-support/pagedTreeHarness.js';
const options={protocolId:'protocol-A',queryRevision:'query-A',bindingVersion:3,epochUuids:['epoch-A','epoch-B'],selectionScope:{filters:{cell_type:'A'},cell_uuid:'cell-A'},changes:{tags_add:['retained']}};
const receipt=(params=options)=>({protocol_uuid:params.protocolId,query_revision:params.queryRevision,expected_binding_version:params.bindingVersion,epochs:params.epochUuids.map((epoch_uuid,index)=>({epoch_uuid,cell_uuid:'cell-A',curation_revision:index}))});

test('1,000 selected identities require one compact read and one atomic mutation',async()=>{
  const params={...options,epochUuids:Array.from({length:1000},(_,i)=>`epoch-${i}`)};
  const calls=[],read=receipt(params);
  const result=await saveCurationSelection({...params,request:async(path,request)=>{calls.push({path,...request});return calls.length===1?read:{saved:true};}});
  assert.deepEqual(result,{saved:true});assert.equal(calls.length,2);
  assert.equal(calls[0].path,'/protocols/protocol-A/curation/read');
  assert.equal(calls[1].path,'/protocols/protocol-A/curation');
  assert.deepEqual(calls[1].body.epoch_uuids,params.epochUuids);
  assert.deepEqual(calls[1].body.expected_revisions,Object.fromEntries(read.epochs.map(row=>[row.epoch_uuid,row.curation_revision])));
  assert.deepEqual(calls[1].body.selection_scope,params.selectionScope);
  assert.equal(calls[1].body.query_revision,'query-A');assert.equal(calls[1].body.expected_binding_version,3);
  assert.equal(calls[1].signal,undefined,'A submitted write is not cancelled with its preparation read');
});

test('oversized and duplicate batches fail before any API call',async()=>{
  for(const epochUuids of [[],['a','a'],Array(1001).fill('a'),[undefined]]){
    await assert.rejects(saveCurationSelection({...options,epochUuids,request:()=>assert.fail('No request')}),/Select 1–1,000/);
  }
});

test('wrong query, binding, identities, order, cell or revision receipt prevents any write',async()=>{
  const changes=[r=>({...r,protocol_uuid:'other'}),r=>({...r,query_revision:'other'}),r=>({...r,expected_binding_version:4}),
    r=>({...r,epochs:r.epochs.slice(1)}),r=>({...r,epochs:[...r.epochs].reverse()}),
    r=>({...r,epochs:r.epochs.map(row=>({...row,cell_uuid:'other-cell'}))}),
    r=>({...r,epochs:r.epochs.map(row=>({...row,curation_revision:'0'}))}),
    r=>({...r,epochs:r.epochs.map(row=>({...row,curation_revision:-1}))})];
  for(const alter of changes){let calls=0;
    await assert.rejects(saveCurationSelection({...options,request:async()=>{calls++;return alter(receipt());}}));
    assert.equal(calls,1);
  }
});

test('a changed selection after the read cannot initiate a mutation',async()=>{
  const pending=deferred();let current=true,calls=0;
  const work=saveCurationSelection({...options,isCurrent:()=>current,request:()=>{calls++;return pending.promise;}});
  current=false;pending.resolve(receipt());
  await assert.rejects(work,/Selection or dataset changed/);assert.equal(calls,1);
});

test('mutation conflict and uncertain save failure are surfaced once without replay',async()=>{
  for(const message of ['Revision conflict','Saved to SQL but recovery failed','Connection lost']){let calls=0;
    await assert.rejects(saveCurationSelection({...options,request:async()=>{calls++;if(calls===1)return receipt();throw Error(message);}}),error=>error.message===message);
    assert.equal(calls,2);
  }
});
