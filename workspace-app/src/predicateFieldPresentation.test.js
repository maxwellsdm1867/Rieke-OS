import test from 'node:test';
import assert from 'node:assert/strict';
import {predicateFieldLabel,predicateFieldGroup,predicateFieldRank,predicateFieldSearch} from './predicateFieldPresentation.js';
import {compilePredicate,newCondition} from './components/predicateState.js';
test('Protocol ID is first among common fields without changing saved field IDs',()=>{
 const p={id:'protocol',label:'Acquisition protocol',path:'protocol_name',types:['string']};
 assert.equal(predicateFieldLabel(p),'Protocol ID');assert.equal(predicateFieldGroup(p),'Common fields');
 assert.ok(predicateFieldRank(p)<predicateFieldRank({id:'date'}));
 assert.match(predicateFieldSearch(p),/protocol id/);
 assert.deepEqual(compilePredicate({...newCondition(),field:'protocol',operator:'contains',valueText:'VariableMeanNoise'},[p]),{field:'protocol',operator:'contains',value:'VariableMeanNoise'});
});
test('legacy labels expose exact metadata fields and do not invent unrecorded fields',()=>{
 const field={id:'metadata/cell/notes',label:'Cell · Notes',path:'metadata.cell.notes'};
 assert.equal(predicateFieldLabel(field),'Cell Notes');assert.match(predicateFieldSearch(field),/comments/);
 assert.equal(predicateFieldLabel({id:'properties/bathTemperature'}),'Bath Temperature');
 assert.equal(predicateFieldGroup({id:'parameters/frequencyCutoff',category:'Parameters'}),'Protocol settings');
 assert.equal(predicateFieldLabel({id:'curation/abc/tags',label:'Tags · Noise'}),'Tags · Noise');
});
