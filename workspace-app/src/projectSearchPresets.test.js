import test from 'node:test';
import assert from 'node:assert/strict';
import {searchPresetPayload,presetDownloadRecipe,parsePresetRecipe,validatePresetReceipt,sortedProjectPresets,resolvedPresetMatch,presetSaveTarget,samePresetTarget} from './projectSearchPresets.js';
const predicate={all:[{field:'parameters/frequencyCutoff',operator:'eq',value:25},{not:{field:'metadata/epoch/label',operator:'eq',value:'25'}},{field:'parameters/isControl',operator:'eq',value:false},{field:'parameters/example',operator:'eq',value:null}]};
const preset={preset_uuid:'saved-id',project_uuid:'source-project',name:'History with cutoff',description:'Reusable source query',predicate,splits:'',pinned:true,version:3,epochs:['must-not-export'],selection:{included:['must-not-export']}};

test('project updates carry optimistic version and only query fields, preserving flat layout',()=>{
  assert.deepEqual(searchPresetPayload({...preset,pinned:false},preset),{name:preset.name,description:preset.description,predicate,splits:'',pinned:false,expected_version:3});
  assert.equal(Object.hasOwn(searchPresetPayload(preset),'expected_version'),false);
  assert.throws(()=>searchPresetPayload(preset,{version:undefined}),/Reload/);
  assert.throws(()=>searchPresetPayload(preset,{version:0}),/Reload/);
});
test('portable download carries recipe provenance but imports as a new query without frozen membership',()=>{
  const recipe=presetDownloadRecipe(preset);
  assert.equal(recipe.format,'rieke-search-preset');assert.equal(recipe.version,1);
  assert.equal(recipe.project_uuid,'source-project');assert.equal(recipe.catalog_ref,'catalog.json');assert.equal(recipe.membership_mode,'live-query');
  assert.equal(recipe.splits,'');assert.equal(recipe.preset_uuid,'saved-id');assert.equal(recipe.preset_version,3);assert.equal(recipe.epochs,undefined);assert.equal(recipe.selection,undefined);
  const imported=parsePresetRecipe(JSON.stringify(recipe));assert.deepEqual(imported.predicate,predicate);assert.equal(imported.source_project_uuid,'source-project');assert.equal(imported.pinned,false);assert.equal(imported.preset_uuid,undefined);
});
test('import rejects frozen payloads, unsupported versions, excessive nesting and unsafe numbers',()=>{
  const recipe=presetDownloadRecipe(preset);
  for(const changed of [{version:2},{format:'recording-selection-mask'},{epochs:[]},{catalog_ref:'../another/catalog.json'}])assert.throws(()=>parsePresetRecipe(JSON.stringify({...recipe,...changed})));
  let deep={all:[]};for(let i=0;i<20;i++)deep={not:deep};
  assert.throws(()=>parsePresetRecipe(JSON.stringify({...recipe,predicate:deep})),/eight levels/);
  assert.throws(()=>parsePresetRecipe(JSON.stringify({...recipe,predicate:{field:'n',operator:'eq',value:9007199254740992}})),/exactly/);
  assert.throws(()=>parsePresetRecipe(JSON.stringify({...recipe,predicate:{field:'x',operator:'arbitrary_sql',value:1}})),/operator/);
});
test('project pins sort before other saved queries without mutating server rows',()=>{
  const rows=[{name:'Alpha',pinned:false},{name:'Zulu',pinned:true}];
  assert.equal(sortedProjectPresets(rows)[0].name,'Zulu');assert.equal(rows[0].name,'Alpha');
  assert.equal(validatePresetReceipt(preset),preset);assert.throws(()=>validatePresetReceipt({name:'no receipt'}),/receipt/);
  assert.throws(()=>validatePresetReceipt({...preset,version:0}),/receipt/);
});
test('server canonical match always reuses one entry even when new or a different current preset is selected',()=>{
  const other={...preset,preset_uuid:'other',version:8};
  assert.equal(presetSaveTarget(other,preset,'new'),other);
  assert.equal(presetSaveTarget(other,preset,'update'),other);
  assert.equal(presetSaveTarget(null,preset,'new'),null);
  assert.equal(presetSaveTarget(null,preset,'update'),preset);
  assert.equal(resolvedPresetMatch({preset:other}),other);
  assert.equal(resolvedPresetMatch({preset:null}),null);
  assert.throws(()=>resolvedPresetMatch({}),/check/);
});
test('new equivalent entry or changed version requires destination review before writing',()=>{
  assert.equal(samePresetTarget(null,null),true);
  assert.equal(samePresetTarget(preset,{...preset}),true);
  assert.equal(samePresetTarget(null,preset),false);
  assert.equal(samePresetTarget(preset,{...preset,version:4}),false);
  assert.equal(samePresetTarget(preset,{...preset,preset_uuid:'other'}),false);
});
