import test from 'node:test';
import assert from 'node:assert/strict';
import {predicateWithProtocolFilters,tagFilterLabel} from './protocolViewFilter.js';
import {annotationFilterNeedsRefresh} from './annotationReceipts.js';
import {predicateToDraft,compilePredicate} from './components/predicateState.js';

test('scientific view criteria remain distinct, exact, and composable',()=>{
 const predicate={not:{any:[{field:'parameters/x',operator:'is_null'},{field:'parameters/x',operator:'in',value:[0,1]}]}};
 const filters={metadata_predicate:JSON.stringify(predicate),cell_type:'RGC'};
 assert.deepEqual(predicateWithProtocolFilters({all:[]},filters),{all:[{all:[]},{field:'cell type',operator:'eq',value:'RGC'},predicate]});
 assert.deepEqual(compilePredicate(predicateToDraft(predicate)),predicate);
 assert.match(tagFilterLabel(filters),/Metadata/);
 const exportFilters={...filters};delete exportFilters.metadata_predicate;
 assert.ok(filters.metadata_predicate);assert.equal(exportFilters.metadata_predicate,undefined);
 assert.throws(()=>predicateWithProtocolFilters({all:[]},{metadata_predicate:'bad'}));
});
test('shared and curation scientific criteria require authority refresh',()=>{
 for(const field of ['annotations/effective/tags','curation/protocol/tags'])assert.equal(annotationFilterNeedsRefresh({metadata_predicate:JSON.stringify({not:{field,operator:'contains',value:'QC'}})}),true);
 assert.equal(annotationFilterNeedsRefresh({metadata_predicate:JSON.stringify({field:'parameters/x',operator:'gt',value:1})}),false);
 assert.equal(annotationFilterNeedsRefresh({metadata_predicate:'invalid'}),true);
});

import {frozenReadPath,candidatePreviewReceipt} from './frozenReadContext.js';
import {epochPageRequest} from './epochBrowserSource.js';
import {treePageRequest} from './pagedTreeRequest.js';
test('frozen row/detail/tree requests retain exact token and never fall back',()=>{
 const readContext={root:'/protocols/p/workbench/candidates/r',candidate_scope_revision:'opaque /+ token'};
 const path=frozenReadPath(readContext,'p','/epochs/e','x=1');
 assert.equal(new URL(path,'http://fixture').searchParams.get('candidate_scope_revision'),readContext.candidate_scope_revision);
 const page=epochPageRequest({kind:'protocol',protocolId:'p',readContext,query:'metadata_predicate=%7B%22any%22%3A%5B%5D%7D'},{includeCells:true});
 assert.ok(page.path.startsWith(readContext.root+'/epochs?'));
 const body=treePageRequest({protocolId:'p',readContext,filters:{metadata_predicate:'{"any":[]}'}});
 assert.equal(body.candidate_scope_revision,readContext.candidate_scope_revision);assert.equal(body.protocol_uuid,undefined);assert.equal(body.predicate,undefined);
 assert.throws(()=>frozenReadPath({root:readContext.root},'p','/epochs'));
});
test('candidate preview requires echoed scope and exact canonical filters; absent count is unavailable',()=>{
 const request={candidate_scope_revision:'scope-a',filters:{cell_type:'RGC',metadata_predicate:'{"all":[]}'}};
 const result={candidate_scope_revision:'scope-a',filters:{metadata_predicate:'{ "all" : [] }',cell_type:'RGC'},counts:{epochs:0}};
 assert.equal(candidatePreviewReceipt(result,request),0);
 assert.throws(()=>candidatePreviewReceipt({...result,candidate_scope_revision:'scope-b'},request));
 assert.throws(()=>candidatePreviewReceipt({...result,filters:{...result.filters,cell_type:'ON'}},request));
 assert.throws(()=>candidatePreviewReceipt({...result,counts:{}},request));
});
