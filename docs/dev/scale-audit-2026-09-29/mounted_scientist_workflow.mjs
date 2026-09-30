// Controlled transport-delay experiment, not browser paint or native HTTP timing.
import {createWorkflowHarness} from '../../../workspace-app/src/test-support/workflowHarness.js';
import {writeFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
const destination=process.argv[2];
if(!destination)throw Error('Provide a new JSON receipt path and optional immutable baseline src directory');
const root=resolve(import.meta.dirname,'../../..');
const baselineRoot=resolve(process.argv[3]||process.env.RIEKE_WORKFLOW_BASELINE_ROOT||resolve(root,'docs/dev/scale-audit-2026-09-29/frozen-100000-dense-recovery/snapshot/workspace-app/src'));
const baselineFiles=['App.jsx','components/Inspector.jsx','components/AnnotationTags.jsx'];
const files=['workspace-app/src/App.jsx','workspace-app/src/components/Inspector.jsx','workspace-app/src/components/AnnotationTags.jsx','workspace-app/src/useWorkspaceChanges.js','workspace-app/src/epochBrowserSource.js','workspace-app/src/test-support/workflowHarness.js','workspace-app/src/api.js','workspace-app/src/resourceRequest.js','workspace-app/src/resourceCache.js','workspace-app/src/annotationTags.js','workspace-app/src/curationSelection.js','workspace-app/src/epochSelection.js','workspace-app/src/inspectionCellTree.js','workspace-app/src/components/InspectionCellTree.jsx','workspace-app/src/components/EpochTags.jsx','workspace-app/src/components/ProtocolViewFilter.jsx','workspace-app/src/protocolViewFilter.js','workspace-app/src/components/Common.jsx','workspace-app/src/useImportMonitor.js','workspace-app/package-lock.json'];
const hash=async path=>createHash('sha256').update(await readFile(path)).digest('hex');
const hashes=async()=>Object.fromEntries(await Promise.all(files.map(async file=>[file,await hash(resolve(root,file))])));
const baselineHashes=async()=>Object.fromEntries(await Promise.all(baselineFiles.map(async file=>[file,await hash(resolve(baselineRoot,file))])));
const report={baseline_root:baselineRoot,baseline_components_before:await baselineHashes(),baseline_description:'Prior App/Inspector/AnnotationTags flow components with current harness and support modules; not a full historical application build.',scope:'Mounted React product request/authority lifecycle with simulated transport; no browser rendering, native database, H5 trace or real-scientist latency claim.',started_at:new Date().toISOString(),before:await hashes(),transport_ms:{save:25,overview:120,page:40,metadata_fields:40,focused_epoch:20,other:10},cases:[]};
const predicate=name=>({tag_predicate:JSON.stringify({all:[{field:'annotations/effective/tags',operator:'contains',value:name},{not:{field:'annotations/epoch/tags',operator:'contains',value:'excluded'}}]})});
const delay=record=>record.method==='POST'?25:/^\/(overview|projects|protocol-suggestions|protocols\/[^/?]+)(?:\?|$)/.test(record.path)?120:record.path.includes('/epochs?')||record.path.includes('/tree-fields')||record.path==='/metadata/fields'?40:record.path.startsWith('/epochs/')?20:10;
const serialize=(records,start)=>records.map(record=>({...record,started_ms:record.started-start,completed_ms:record.completed-start,started:undefined,completed:undefined}));
for(const total of [500,1000,5000,100000])for(const baseline of [true,false]){
  const h=await createWorkflowHarness({total,baseline,delay,baselineRoot});
  try{
    await h.mount();await h.waitFor(()=>{try{return h.viewer.epoch&&!h.root.findByProps({'aria-label':'Tag this epoch'}).props.disabled;}catch{return false;}});
    await h.settle(260);
    const item={epochs:total,implementation:baseline?'prior flow components with current harness/support':'current flow components with current harness/support',operations:[],initial_inspector_mounts:h.fixture.mounts};
    let mark=h.fixture.requests.length,start=performance.now();
    await h.act(()=>h.root.findByProps({'aria-label':'Tag this epoch'}).props.onChange({target:{value:'workflow saved tag'}}));
    await h.act(()=>h.root.findByProps({'aria-label':'Tag this epoch'}).parent.props.onSubmit({preventDefault(){}}));
    await h.waitFor(()=>{try{return h.viewer.epoch?.annotations.epoch_tags.some(tag=>tag.tag==='workflow saved tag')&&!h.root.findByProps({'aria-label':'Tag this epoch'}).props.disabled;}catch{return false;}});
    item.operations.push({action:'save shared epoch tag then current authority editable',controlled_completion_ms:performance.now()-start,requests:serialize(h.fixture.requests.slice(mark),start)});
    await h.settle(260);
    for(const name of ['A','B','A']){
      mark=h.fixture.requests.length;start=performance.now();
      await h.act(()=>h.viewer.onViewFilters(predicate(name)));
      await h.waitFor(()=>{try{return !h.viewer.navigation.loading&&h.viewer.navigation.total===total/2;}catch{return false;}});
      item.operations.push({action:`filter ${name}`,controlled_completion_ms:performance.now()-start,requests:serialize(h.fixture.requests.slice(mark),start)});
      await h.settle(260);
    }
    item.final_inspector_mounts=h.fixture.mounts;item.inspector_unmounts=h.fixture.unmounts;
    report.cases.push(item);
    console.log(JSON.stringify({epochs:total,baseline,mounts:item.final_inspector_mounts,operations:item.operations.map(operation=>({action:operation.action,requests:operation.requests.length,ms:Math.round(operation.controlled_completion_ms)}))}));
  }finally{await h.close();}
}
report.after=await hashes();report.baseline_components_after=await baselineHashes();report.source_unchanged=JSON.stringify(report.before)===JSON.stringify(report.after)&&JSON.stringify(report.baseline_components_before)===JSON.stringify(report.baseline_components_after);report.finished_at=new Date().toISOString();
report.limitations=['The renderer mounts actual App/Protocol/Inspector/tag/filter/cell-tree code but replaces layout/trace drawing and unrelated screens.','Synthetic transport delay is controlled; timing differences show dependency order and request fanout, not production p95.','All four declared dataset sizes create bounded page responses and at most one cell summary per500epochs; no raw100k-row React view is mounted.','Open tree/column branches and actual H5 trace latency are outside this mounted collapsed-cell-list measurement.','Native workflow receipts separately measure server operations; neither receipt alone measures browser paint.'];
await writeFile(destination,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
