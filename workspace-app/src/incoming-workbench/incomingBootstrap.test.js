import test from 'node:test';
import assert from 'node:assert/strict';
import {incomingPageOffer,requireIncomingBootstrap} from './incomingBootstrap.js';
const root='/protocols/p/workbench/candidates/c';
const owner={root,protocolId:'p',projectId:'project',candidateRevision:'c',profileUuid:'actor',profileReady:true};
const bootstrap=()=>({contract_version:1,kind:'workbench_initial_page',root,protocol_uuid:'p',project_uuid:'project',candidate_revision_uuid:'c',actor:'actor',
 context:{candidate_revision_uuid:'c',candidate_scope_revision:'scope',expected_binding_version:2,generation:{metadata:'m'},draft:{draft_version:3},protocol:{query_revision:'scope',expected_binding_version:2,definition:{protocol_uuid:'p',project_uuid:'project'}}},
 page:{candidate_scope_revision:'scope',query_revision:'scope',expected_binding_version:2,generation:{metadata:'m'},total:2,offset:0,limit:60,cells:[{cell_uuid:'cell',epochs:2}],epochs:[{epoch_uuid:'a',cell_uuid:'cell'},{epoch_uuid:'b',cell_uuid:'cell'}]},
 request:{filters:{},offset:0,limit:60,include_cells:true}});
const path=root+'/epochs?candidate_scope_revision=scope&offset=0&limit=60&include_cells=true';
test('bootstrap validates exact page authority and grants one mounted consumer detached data',()=>{
 const value=bootstrap(),offer=incomingPageOffer(value,owner),consumer={};
 assert.equal(requireIncomingBootstrap(value,owner),value);
 const first=offer.claim({consumer,path});assert.deepEqual(first,value.page);first.epochs.pop();
 assert.equal(offer.claim({consumer,path}).epochs.length,2,'StrictMode effect replay keeps a detached exact copy');
 assert.equal(offer.claim({consumer:{},path}),undefined,'a new mount cannot reclaim the response');
});
test('bootstrap refuses stale, partial, missing, duplicate and wrong-owner data',()=>{
 for(const mutate of [v=>v.page.query_revision='old',v=>v.context.expected_binding_version=null,v=>delete v.context.generation,
  v=>v.page.generation={metadata:'changed'},v=>v.page.epochs.pop(),v=>v.page.cells[0].epochs=3,
  v=>v.page.epochs[1].epoch_uuid='a',v=>v.page.epochs[0].cell_uuid='wrong',v=>v.root='/wrong',v=>v.project_uuid='wrong']){
  const value=bootstrap();mutate(value);assert.throws(()=>requireIncomingBootstrap(value,owner));
 }
 assert.equal(incomingPageOffer(bootstrap(),{...owner,profileReady:false}),null);
 assert.equal(incomingPageOffer(bootstrap(),{...owner,profileUuid:'other'}),null);
});
test('page offers require the exact read path, filters, cell projection and bounded position',()=>{
 for(const altered of [path+'&tag=changed',path.replace('offset=0','offset=60'),path.replace('limit=60','limit=50'),
  path.replace('include_cells=true','include_cells=false'),path+'&anchor_uuid=a',path+'&offset=0',path.replace('scope','old'),path.replace('/c/','/d/')]){
  assert.equal(incomingPageOffer(bootstrap(),owner).claim({consumer:{},path:altered}),undefined);
 }
});
