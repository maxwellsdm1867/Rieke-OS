import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflowHarness} from './test-support/workflowHarness.js';

test('contextual predicate editor restores current conditions; cancel and clear are explicit',async()=>{
 const h=await createWorkflowHarness(),changes=[];
 const filters={cell_type:'RGC',group_label:'Drug',tagged:'true'};
 const protocol={definition:{query:{all:[{field:'protocol',operator:'eq',value:'Noise'}]}},selection_options:{cell_types:['RGC','ON']},groups:['Drug','Wash']};
 try{
  const Editor=await h.component('ProtocolViewFilter');
  await h.mount(Editor,{protocol,filters,onChange:value=>changes.push(value),revision:0});
  const button=text=>h.root.findAllByType('button').find(node=>node.children.some(child=>typeof child==='string'&&child.includes(text)));
  await h.act(()=>button('Filter view').props.onClick());
  const selects=h.root.findAllByType('select');
  assert.deepEqual(selects.map(node=>node.props.value),['RGC','Drug','tagged']);
  assert.match(h.root.findByType('pre').children.join(''),/Noise/);
  await h.act(()=>selects[0].props.onChange({target:{value:'ON'}}));
  await h.act(()=>h.root.findByProps({'aria-label':'Close view filters'}).props.onClick());
  assert.deepEqual(changes,[]);
  await h.act(()=>button('Filter view').props.onClick());
  assert.equal(h.root.findAllByType('select')[0].props.value,'RGC');
  await h.act(()=>h.root.findByType('form').props.onSubmit({preventDefault(){}}));
  assert.deepEqual(changes,[filters]);
  await h.act(()=>button('Filter view').props.onClick());
  await h.act(()=>button('Clear view filters').props.onClick());
  assert.deepEqual(changes,[filters,{}]);
 }finally{await h.close();}
});
