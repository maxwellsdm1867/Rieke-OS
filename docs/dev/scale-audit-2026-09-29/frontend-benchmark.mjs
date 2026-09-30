// Disposable synthetic audit. No production requests, source data, or app changes.
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {writeFile} from 'node:fs/promises';
import os from 'node:os';
import {performance} from 'node:perf_hooks';
const root=fileURLToPath(new URL('../../../workspace-app/',import.meta.url));
const require=createRequire(root+'package.json');
const {createElement}=require('react');
const {renderToString}=require('react-dom/server');
const {createServer}=await import(require.resolve('vite'));
const {default:react}=await import(require.resolve('@vitejs/plugin-react'));
const {createResourceCache,cachedResourceRequest,initialEpochTracePath}=await import('../../../workspace-app/src/resourceCache.js');
const {finiteExtent}=await import('../../../workspace-app/src/components/traceGeometry.js');
const {registeredMetadataField}=await import('../../../workspace-app/src/components/metadataValues.js');
const {groupedCellPage}=await import('../../../workspace-app/src/boundedTree.js');
const output={measured_at:new Date().toISOString(),machine:{node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,total_memory_gib:os.totalmem()/2**30},limitations:['Node SSR and synthetic helper timings, not browser paint / INP / H5 throughput.','No production API requests or original data read; generated identities and metadata only.','Synthetic large catalogs put inspected fields near the end to expose repeated linear search cost.'],measurements:[]};
const previous=console.error;console.error=(message,...args)=>{if(!String(message).startsWith('Warning: useLayoutEffect does nothing on the server'))previous(message,...args);};
const server=await createServer({root,configFile:false,plugins:[react()],server:{middlewareMode:true,hmr:false},appType:'custom',logLevel:'error'});
try{
 const {default:InspectionCellTree}=await server.ssrLoadModule('/src/components/InspectionCellTree.jsx');
 const {CellList}=await server.ssrLoadModule('/src/components/Common.jsx');
 const {default:MetadataPanel}=await server.ssrLoadModule('/src/components/MetadataPanel.jsx');
 const {default:Overview}=await server.ssrLoadModule('/src/components/Overview.jsx');
 function measure(name,size,run,repeats=3){
  const samples=[];let result;
  for(let i=0;i<repeats;i++){const at=performance.now();result=run();samples.push(performance.now()-at);}
  const sorted=[...samples].sort((a,b)=>a-b),row={name,size,samples_ms:samples,median_ms:sorted[Math.floor(sorted.length/2)],result};output.measurements.push(row);console.log(JSON.stringify(row));return row;
 }
 const cells=n=>Array.from({length:n},(_,i)=>({cell_uuid:`cell-${i}`,label:`Cell${i}`,date:`2026-09-${String(1+i%28).padStart(2,'0')}`,cell_type:['On Parasol','Off Parasol','Midget'][i%3],epochs:100,duration_seconds:500}));
 for(const n of [100,1000,10000,50000]){
  const records=cells(n),props={cells:records,targets:[],source:{kind:'protocol',protocolId:'synthetic',query:''},revision:0};
  measure('default InspectionCellTree SSR; all dates closed',n,()=>{const html=renderToString(createElement(InspectionCellTree,props));return {cell_details_elements:(html.match(/class="cell-tree-cell"/g)||[]).length,html_bytes:Buffer.byteLength(html)};});
  measure('bounded CellList SSR',n,()=>{const html=renderToString(createElement(CellList,{cells:records}));return {cell_rows:(html.match(/class="cell-row"/g)||[]).length,html_bytes:Buffer.byteLength(html)};});
  measure('groupedCellPage helper',n,()=>{const page=groupedCellPage(records,0);return {total:page.total,visible:page.groups.reduce((sum,g)=>sum+g.cells.length,0)};});
 }
 for(const n of [100,1000,5000]){
  const protocols=Array.from({length:n},(_,i)=>({protocol_uuid:`protocol-${i}`,name:`Synthetic Protocol ${i}`,counts:{epochs:i+1,cells:5,duration_seconds:100}}));
  measure('Overview SSR varying protocol count',n,()=>{const html=renderToString(createElement(Overview,{data:{cells:[],protocols,counts:{},sources:[],events:[]}}));return {protocol_rows:(html.match(/class="ov-protocol-row"/g)||[]).length,html_bytes:Buffer.byteLength(html)};});
  measure('ProtocolVolumes current exact max-per-row expression',n,()=>{let sum=0;for(const protocol of protocols){const count=protocol.counts?.epochs??protocol.epoch_count??0;sum+=count/Math.max(1,...protocols.map(item=>item.counts?.epochs??item.epoch_count??0))*100;}return {sum};});
  measure('proposed max-once expression',n,()=>{const max=Math.max(1,...protocols.map(item=>item.counts?.epochs??item.epoch_count??0));let sum=0;for(const protocol of protocols)sum+=(protocol.counts?.epochs??protocol.epoch_count??0)/max*100;return {sum};});
 }
 for(const n of [100,1000,10000]){
  const fields=Array.from({length:n},(_,i)=>({id:`parameters/p${i}`,grouping_priority:i,grouping_role:'technical'}));
  const parameters=Object.fromEntries(Array.from({length:100},(_,i)=>[`p${n-100+i}`,i]));
  measure('MetadataPanel SSR 100 parameters near end of field catalog',n,()=>{const html=renderToString(createElement(MetadataPanel,{epoch:{epoch_uuid:'synthetic',parameters},catalog:{data:{fields}}}));return {html_bytes:Buffer.byteLength(html)};});
  const paths=Object.keys(parameters).map(key=>['parameters',key]);
  measure('100 registeredMetadataField lookups',n,()=>({found:paths.filter(path=>registeredMetadataField(path,fields)).length}));
  measure('proposed predecoded field map plus 100 lookups',n,()=>{const index=new Map(fields.map(field=>[JSON.stringify(field.id.split('/').map(part=>decodeURIComponent(part).replace(/~1/g,'/').replace(/~0/g,'~'))),field]));return {found:paths.filter(path=>index.has(JSON.stringify(path))).length};});
 }
 const values=Array.from({length:20000},(_,i)=>Math.sin(i/20)*50);
 measure('bounded 20k trace finiteExtent',20000,()=>finiteExtent(values),5);
 measure('bounded 20k trace JSON stringify + parse',20000,()=>{const parsed=JSON.parse(JSON.stringify({values}));return {samples:parsed.values.length};},5);
 const cache=createResourceCache();
 measure('bounded 20k trace cache put including serialization estimate',20000,()=>{cache.put('/epochs/synthetic/trace',0,{values});return cache.stats();},5);
 let requests=0;const duplicateCache=createResourceCache();const request=async()=>{requests++;await new Promise(resolve=>setTimeout(resolve,10));return {epoch_uuid:'synthetic'};};
 await Promise.all([cachedResourceRequest('/epochs/synthetic',{cache:duplicateCache,request}),cachedResourceRequest('/epochs/synthetic',{cache:duplicateCache,request})]);
 output.duplicate_miss={concurrent_same_key_calls:2,underlying_request_calls:requests};
 output.trace_window={full_stream_samples:100000000,initial_path:initialEpochTracePath({epoch_uuid:'synthetic',streams:[{kind:'responses',uuid:'response',sample_count:100000000}]})};
 const boundedCache=createResourceCache();for(let i=0;i<1000;i++)boundedCache.put(`/epochs/synthetic-${i}`,0,{values});output.cache_after_1000_trace_sized_entries=boundedCache.stats();
 // Matches Inspector.jsx's Promise.all(uuids.map(api(...))) fan-out, without network.
 for(const n of [1,60,1000]){let active=0,peak=0;await Promise.all(Array.from({length:n},async()=>{active++;peak=Math.max(peak,active);await new Promise(resolve=>setTimeout(resolve,1));active--;}));output.measurements.push({name:'Inspector curation Promise.all GET fan-out simulation',size:n,peak_concurrent_calls:peak});}
}finally{await server.close();console.error=previous;await writeFile(new URL('./frontend-benchmark.json',import.meta.url),JSON.stringify(output,null,2)+'\n');}
