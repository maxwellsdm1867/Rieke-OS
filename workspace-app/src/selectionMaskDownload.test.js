import test from 'node:test';
import assert from 'node:assert/strict';
import {createInspectorHarness} from './test-support/inspectorHarness.js';
function elements(value){if(Array.isArray(value))return value.flatMap(elements);if(!value||typeof value!=='object')return [];const children=value.props?.children;return [value,...(Array.isArray(children)?children:[children]).flatMap(elements)];}
function text(value){if(Array.isArray(value))return value.map(text).join(' ');if(typeof value==='string')return value;if(!value||typeof value!=='object')return '';const children=value.props?.children;return (Array.isArray(children)?children:[children]).map(text).join(' ');}
test('protocol mask controls preserve JSON import/export and save through the owned HTTP download boundary',async()=>{
 const h=await createInspectorHarness(),downloads=[],calls=[],prior=globalThis.document;
 globalThis.document={body:{appendChild(){}},createElement(tag){assert.equal(tag,'a');return {click(){downloads.push({href:this.href,filename:this.download});},remove(){}};}};
 h.fixture.api=async(path)=>{calls.push(path);return {format:'recording-selection-mask',version:1,protocol_uuid:'protocol-A',epochs:[{epoch_uuid:'epoch-A',included:true}]};};
 try{await h.render({protocol:{definition:{protocol_uuid:'protocol-A'},query_revision:'query-A',cells:[]},filters:{},revision:0});
  await h.act(()=>h.viewer.toolbar.actions.find(action=>action.label==='Import mask file…').run());
  assert.doesNotMatch(text(h.viewer.before),/MATLAB|EpicTree|UGM/);
  const controls=elements(h.viewer.before);assert.ok(controls.some(node=>node.type==='button'&&text(node).trim()==='Import JSON mask'));
  const save=controls.find(node=>node.type==='button'&&text(node).trim()==='Save JSON mask');assert.ok(save);
  await h.act(()=>save.props.onClick());
  assert.deepEqual(calls,['/protocols/protocol-A/masks/export']);
  assert.deepEqual(downloads,[{href:'/api/protocols/protocol-A/masks/export',filename:'recording-mask-protocol.json'}]);
  assert.doesNotMatch(text(h.viewer.before),/Selection mask saved/);
 }finally{await h.close();if(prior===undefined)delete globalThis.document;else globalThis.document=prior;}
});
