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
  const {default:CellTypeAccordions}=await server.ssrLoadModule('/src/components/CellTypeAccordions.jsx');
  const {default:ProtocolInfographic}=await server.ssrLoadModule('/src/components/ProtocolInfographic.jsx');
  let renderer;const refs=[];
  t.after(async()=>{await act(()=>renderer?.unmount());await server.close();globalThis.window=beforeWindow;globalThis.requestAnimationFrame=beforeFrame;});
  return {Overview,ProtocolInfographic,CellListSection,CellTypeAccordions,ProtocolSelectionSummary,get root(){return renderer.root;},refs,
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
test('main infographic retains exact type counts and unavailable pending scope independently of browsing',async t=>{
  const h=await harness(t),workbench=[];
  const main={...data,binding:{revision_uuid:'frozen-main',version:3},catalog:{fields:[{id:'cell type',values:[{value:'RGC\\ON-midget',count:600}]}]}};
  await h.render(h.ProtocolInfographic,{data:main,browsingCounts:{cells:1,epochs:2},pendingReviewCells:null});
  const groups=h.root.findAllByProps({className:'cell-type-group'});assert.equal(groups.length,3);
  const labels=groups.map(group=>group.findByProps({className:'cell-type-toggle'}).findAllByType('span').map(node=>node.children.join('')).join(' '));
  for(const label of ['RGC\\ON-midget','Unknown','Unclassified'])assert(labels.some(value=>value.includes(label)));
  assert.equal(h.root.findAllByProps({className:'pi-epoch-details'}).length,0);
  const pending=h.root.findByProps({className:'pi-pending-review'});assert(pending.findAllByType('strong').some(node=>node.children.join('')==='Unavailable'));
  assert.equal(pending.findAllByType('button').length,0);
  await h.render(h.ProtocolInfographic,{data:main,browsingCounts:{cells:0,epochs:0},pendingReviewCells:7,onWorkbench:()=>workbench.push('open')});
  assert.equal(h.root.findAllByProps({className:'cell-type-group'}).length,3);
  const known=h.root.findByProps({className:'pi-pending-review'});assert(known.findAllByType('strong').some(node=>node.children.join('')==='7'));
  await act(()=>known.findByType('button').props.onClick());assert.deepEqual(workbench,['open']);
});

test('type disclosure starts collapsed, retains details and routes exact main cell UUIDs',async t=>{
  const h=await harness(t),calls=[];
  await h.render(h.CellTypeAccordions,{cells:[...data.cells,data.cells[0]],onInspect:uuid=>calls.push(['inspect',uuid]),onQC:uuid=>calls.push(['qc',uuid])});
  const groups=h.root.findAllByProps({className:'cell-type-group'});assert.equal(groups.length,3);
  const group=groups.find(node=>node.findByProps({className:'cell-type-toggle'}).findAllByType('span').some(span=>span.children.includes('RGC\\ON-midget')));
  const toggle=group.findByProps({className:'cell-type-toggle'});const panel=()=>group.findByProps({id:toggle.props['aria-controls']});
  assert.equal(toggle.props['aria-expanded'],false);assert.equal(panel().props.hidden,true);
  await act(()=>toggle.props.onClick());assert.equal(panel().props.hidden,false);
  const row=group.findByProps({className:'cell-row'});
  await act(()=>toggle.props.onClick());assert.equal(panel().props.hidden,true);
  await act(()=>toggle.props.onClick());assert.equal(group.findByProps({className:'cell-row'}),row);
  await act(()=>group.findAllByType('button').find(node=>node.children.includes('Inspect & tag epochs ')).props.onClick());
  await act(()=>group.findAllByType('button').find(node=>node.children.includes('Cell QC ')).props.onClick());
  assert.deepEqual(calls,[['inspect','a'],['qc','a']]);
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


test('unavailable project date metrics and inventory counts never display fabricated zeros',async t=>{
 const h=await harness(t);await h.render(h.Overview,{data:{...data,counts:{},cells:[{cell_uuid:'missing',cell_type:'Unknown',date:'2026-09-24',epochs:null,duration_seconds:null}]}});
 const date=h.root.findAllByType('button').find(node=>node.props.title?.startsWith('Show cells recorded'));
 assert.match(date.findByType('small').children.join(''),/Unavailable epochs · Unavailable/);
 const ribbon=h.root.findByProps({className:'ov-metric-ribbon'});
 assert(ribbon.findAllByType('strong').some(node=>node.children.join('')==='Unavailable'));
 const inventory=h.root.findByProps({className:'ov-inventory'});
 assert(inventory.findAllByType('strong').some(node=>node.children.join('')==='Unavailable'));
});


test('missing membership summaries are unavailable while an authoritative empty array is genuinely empty',async t=>{
 const h=await harness(t);await h.render(h.ProtocolInfographic,{data:{binding:{revision_uuid:'main'},counts:{epochs:8}}});
 assert.match(h.root.findByProps({className:'pi-cell-coverage'}).children.join(''),/unavailable/);
 const missing=h.root.findByProps({className:'pi-metrics'}).findAllByType('strong').map(node=>node.children.join(''));
 assert.deepEqual(missing.slice(0,2),['Unavailable','Unavailable']);assert.equal(h.root.findAllByProps({className:'cell-type-group'}).length,0);
 await h.render(h.ProtocolInfographic,{data:{binding:{revision_uuid:'main'},cells:[],counts:{epochs:0,duration_seconds:0,included:0,excluded:0}}});
 assert.equal(h.root.findAllByProps({className:'pi-cell-coverage'}).length,0);
 assert.deepEqual(h.root.findByProps({className:'pi-metrics'}).findAllByType('strong').map(node=>node.children.join('')).slice(0,2),['0','0']);
 await h.render(h.ProtocolInfographic,{data:{binding:{revision_uuid:'main'},cells:[{label:'missing-id'},data.cells[0]],counts:{epochs:600}}});
 assert.match(h.root.findByProps({className:'pi-cell-coverage'}).children.join(''),/1 cell summary row lacks a UUID/);
 assert.equal(h.root.findByProps({className:'pi-metrics'}).findAllByType('strong')[0].children.join(''),'Unavailable');
});
