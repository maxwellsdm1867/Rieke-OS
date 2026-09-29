import test from 'node:test';
import assert from 'node:assert/strict';
import {epochPageRequest} from './epochBrowserSource.js';

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
