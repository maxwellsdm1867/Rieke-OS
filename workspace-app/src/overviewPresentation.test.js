import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

async function harness(t) {
  const beforeWindow=globalThis.window,beforeFrame=globalThis.requestAnimationFrame;
  globalThis.window={matchMedia:()=>({matches:true})};globalThis.requestAnimationFrame=callback=>callback();
  const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,cacheDir:'/tmp/rieke-arthur-proof/test-vite-cache',
    server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',logLevel:'error',esbuild:{jsx:'automatic'},plugins:[{
      name:'overview-no-io',enforce:'pre',resolveId(id){if(id==='./RecordingSize.jsx')return '\0recording-size';},
      load(id){if(id==='\0recording-size')return 'export default function RecordingSize(){return null;}';}
    }]});
  const {default:Overview}=await server.ssrLoadModule('/src/components/Overview.jsx');
  const {default:ProtocolSelectionSummary}=await server.ssrLoadModule('/src/components/ProtocolSelectionSummary.jsx');
  const {default:CellListSection}=await server.ssrLoadModule('/src/components/CellListSection.jsx');
  const {default:ProtocolInfographic}=await server.ssrLoadModule('/src/components/ProtocolInfographic.jsx');
  let renderer;const refs=[];
  t.after(async()=>{await act(()=>renderer?.unmount());await server.close();globalThis.window=beforeWindow;globalThis.requestAnimationFrame=beforeFrame;});
  return {Overview,ProtocolInfographic,CellListSection,ProtocolSelectionSummary,get root(){return renderer.root;},refs,
    async render(Component,props){await act(()=>{const element=React.createElement(Component,props);if(renderer)renderer.update(element);else renderer=TestRenderer.create(element,{createNodeMock:()=>({focus:()=>refs.push('focus'),scrollIntoView:options=>refs.push(options.behavior)})});})}};
}
const data={cells:[{cell_uuid:'a',cell_type:'RGC\\ON-midget',label:'Cell1',date:'2026-09-24',epochs:600,exported:3},
  {cell_uuid:'b',cell_type:'Unknown',label:'Cell1',date:'2026-09-25',epochs:2},{cell_uuid:'c',cell_type:null,label:'Cell3',epochs:1}],
  counts:{cells:999,epochs:603,included:603},sources:[],protocols:[]};

test('overview collapse preserves rows; scoped type/date controls reveal and focus; QC receives exact UUID',async t=>{
  const h=await harness(t),selected=[];await h.render(h.Overview,{data,onQC:uuid=>selected.push(uuid)});
  const toggle=()=>h.root.findByProps({className:'cell-list-toggle'}),panel=()=>h.root.findByProps({id:toggle().props['aria-controls']});
  assert.equal(toggle().props['aria-expanded'],false);assert.equal(panel().props.hidden,true);
  await act(()=>toggle().props.onClick());assert.equal(panel().props.hidden,false);
  const row=h.root.findAllByProps({className:'cell-row'})[0];
  await act(()=>toggle().props.onClick());assert.equal(panel().props.hidden,true);
  await act(()=>toggle().props.onClick());assert.equal(h.root.findAllByProps({className:'cell-row'})[0],row);
  await act(()=>h.root.findAllByType('button').find(node=>node.props.title==='Filter the cell list below'&&node.findAllByType('span').some(span=>span.children.includes('RGC\\ON-midget'))).props.onClick());
  assert.equal(panel().props.hidden,false);assert.equal(h.root.findAllByProps({className:'cell-row'}).length,1);assert.deepEqual(h.refs.slice(-2),['focus','auto']);
  await act(()=>h.root.findAllByType('button').find(node=>node.children.includes('Cell QC ')).props.onClick());assert.deepEqual(selected,['a']);
  await act(()=>h.root.findAllByType('button').find(node=>node.children.includes(' Clear')).props.onClick());
  assert.equal(h.root.findAllByProps({className:'cell-row'}).length,3);
  const dates=h.root.findAllByType('button').filter(node=>node.props.title?.startsWith('Show cells recorded'));
  await act(()=>dates.find(node=>node.props.title.includes('Sep 25')).props.onClick());
  assert.equal(h.root.findAllByProps({className:'cell-row'}).length,1);
});
test('protocol compact infographic counts cells rather than epoch facets and preserves exact labels/export participation',async t=>{
  const h=await harness(t);await h.render(h.ProtocolInfographic,{data:{...data,catalog:{fields:[{id:'cell type',values:[{value:'RGC\\ON-midget',count:600}]}]}}});
  const graph=h.root.findAllByType('svg').find(node=>node.props.role==='img');
  assert.match(graph.props['aria-label'],/^3 matching cells:/);assert.match(graph.props['aria-label'],/RGC\\ON-midget: 1/);
  assert.match(graph.props['aria-label'],/Unknown: 1/);assert.match(graph.props['aria-label'],/Unclassified: 1/);
  const entries=h.root.findAllByProps({className:'cell-type-entry'});assert.equal(entries.length,3);
  assert.equal(entries.find(node=>node.findByType('span').children.includes('RGC\\ON-midget')).findByType('small').children.join(''),'1 with saved exports');
});

test('dataset cell list shares accessible collapse and preserves inspection/QC identity callbacks',async t=>{
  const h=await harness(t),inspections=[],qc=[];
  await h.render(h.CellListSection,{cells:[...data.cells,data.cells[0]],title:'Cells in this protocol',onInspect:uuid=>inspections.push(uuid),onQC:uuid=>qc.push(uuid)});
  const toggle=()=>h.root.findByProps({className:'cell-list-toggle'}),panel=()=>h.root.findByProps({id:toggle().props['aria-controls']});
  assert.equal(toggle().props['aria-expanded'],false);assert.equal(panel().props.hidden,true);assert.equal(h.root.findAllByProps({className:'cell-row'}).length,3);
  await act(()=>toggle().props.onClick());assert.equal(panel().props.hidden,false);
  await act(()=>h.root.findAllByType('button').find(node=>node.children.includes('Inspect & tag epochs ')).props.onClick());assert.deepEqual(inspections,['a']);
  await act(()=>h.root.findAllByType('button').find(node=>node.children.includes('Cell QC ')).props.onClick());assert.deepEqual(qc,['a']);
  await act(()=>toggle().props.onClick());assert.equal(panel().props.hidden,true);
});

test('compact protocol context keeps main, browsing and export mark scopes independent',async t=>{
  const h=await harness(t),calls=[];
  await h.render(h.ProtocolSelectionSummary,{data:{total_counts:{epochs:100,cells:8,included:80},counts:{epochs:30,cells:3,included:20},effective_query:{all:[]}},filters:{cell_type:'ON midget'},onClear:()=>calls.push('clear'),onExport:()=>calls.push('export'),onEdit:()=>calls.push('edit')});
  const readouts=h.root.findByProps({className:'protocol-scope-readouts'});
  assert.deepEqual(readouts.findAllByType('strong').map(node=>node.children.join('')),['100','8','30','3','80']);
  await act(()=>readouts.findAllByType('button').find(node=>node.children.includes('Choose export subset')).props.onClick());
  assert.deepEqual(calls,['export']);
  await act(()=>readouts.findAllByType('button').find(node=>node.children.includes('Show all recordings')).props.onClick());
  assert.deepEqual(calls,['export','clear']);
  const details=h.root.findByProps({className:'protocol-query-details'});assert.equal(details.props.open,undefined);
});
