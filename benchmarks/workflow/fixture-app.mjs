/** Owned composition shell: production components, no intercepted API replies. */
export function fixtureSource(meta) {
  return `import React,{Profiler,useState} from 'react';
import {createRoot} from 'react-dom/client';
import Inspector from '/src/epoch-browser/ui/Inspector.jsx';
import MetadataExplorer from '/src/metadata-explorer/ui/MetadataExplorer.jsx';
import CumulativeIncomingReview from '/src/incoming-workbench/ui/CumulativeIncomingReview.jsx';
import useWorkbenchQueue from '/src/incoming-workbench/useWorkbenchQueue.js';
import {AnnotationProfileProvider} from '/src/annotations/annotationProfile.js';
import {TreeBranchReadOwner} from '/src/tree-ancestors/treeBranchReads.jsx';
import {useResource} from '/src/api.js';
import '/src/styles.css';
import '/src/themes.css';
const meta=${JSON.stringify(meta)};
function Main(){const r=useResource('/protocols/'+meta.protocol,0);return r.data?<Inspector projectId={meta.project} protocol={r.data} filters={{}} revision={0} onChange={()=>{}} onBack={()=>{}}/>:<p>{r.error||'Loading protocol'}</p>;}
function Incoming(){const queue=useWorkbenchQueue(meta.protocol,0);return !queue.data?<p>{queue.error||'Loading workbench queue'}</p>:<CumulativeIncomingReview queue={queue} session={window.__workflow.incomingSession||{}} projectId={meta.project} protocolId={meta.protocol} revision={0} onChange={()=>{}} onHistory={()=>{}} onRefresh={queue.reload} onSession={value=>{window.__workflow.incomingSession=value;}}/>;}
function render(id,phase,actualDuration,baseDuration,startTime,commitTime){const b=window.__workflow;if(b?.active?.phase==='profile')b.renders.push({action_id:b.active.action_id,module:id,phase,actual_duration_ms:actualDuration,base_duration_ms:baseDuration,start_ms:startTime-b.active.intent,commit_ms:commitTime-b.active.intent});}
function MeasureProfiler({id,children}){return window.__workflow.profile?<Profiler id={id} onRender={render}>{children}</Profiler>:children;}
function App(){const[mode,setMode]=useState('idle');return <AnnotationProfileProvider projectId={meta.project}><TreeBranchReadOwner projectId={meta.project} revision={0}><header><button onClick={()=>setMode('main')}>Benchmark Main</button><button onClick={()=>setMode('idle')}>Benchmark Away</button><button onClick={()=>setMode('incoming')}>Benchmark Workbench</button><button onClick={()=>setMode('search')}>Benchmark Predicate</button></header><MeasureProfiler id={mode==='main'?'epoch-browser':mode==='incoming'?'incoming-workbench':'metadata-explorer'} >{mode==='main'?<Main/>:mode==='incoming'?<Incoming/>:mode==='search'?<MetadataExplorer projectId={meta.project} initialPredicate={meta.predicate||{field:'cell',operator:'eq',value:meta.first_cell}} initialEditorOpen revision={0} onChange={()=>{}}/>:<p>Owned benchmark fixture</p>}</MeasureProfiler></TreeBranchReadOwner></AnnotationProfileProvider>;}createRoot(document.getElementById('root')).render(<App/>);`;
}

/** Independent UI adapter for the retained dropdown and current stream controls.
 * The label-only single-stream form needs the fixture's exact stream inventory;
 * it cannot infer identity from whichever network reply happened to arrive. */
export function installTraceControlReader({streams=[]}={}) {
  window.__workflowReadStream = root => {
    const controls=[...(root?.querySelectorAll('[aria-label="Response stream"]')||[])];
    if(!controls.length)return {status:'pending',reason:'stream control missing'};
    const expected=new Map(streams.map(row=>[row.uuid,row]));
    const invalid=reason=>({status:'incompatible',reason,controls:controls.map(el=>({tag:el.tagName,text:el.textContent}))});
    if(controls.length!==1)return invalid('ambiguous stream controls');
    if(!streams.length||expected.size!==streams.length)return invalid('independent stream inventory missing or duplicated');
    const control=controls[0];
    if(control.tagName==='SELECT'){
      if(!control.value)return {status:'pending',reason:'stream selection empty'};
      if(!expected.has(control.value))return invalid('dropdown selected an unknown stream UUID');
      return {status:'ready',kind:'select',stream_uuid:control.value};
    }
    if(control.tagName!=='DIV')return invalid('unsupported stream control element');
    const buttons=[...control.querySelectorAll('button')];
    if(buttons.length){
      const ids=buttons.map(button=>button.getAttribute('title'));
      if(ids.length!==streams.length||new Set(ids).size!==ids.length||ids.some(id=>!expected.has(id)))return invalid('stream button inventory differs from fixture');
      const selected=buttons.filter(button=>button.getAttribute('aria-pressed')==='true');
      if(selected.length!==1)return invalid('expected exactly one pressed stream button');
      return {status:'ready',kind:'buttons',stream_uuid:selected[0].getAttribute('title')};
    }
    const labels=[...control.querySelectorAll('span')];
    if(streams.length!==1||labels.length!==1)return invalid('label-only control requires exactly one known stream');
    const stream=streams[0],label=`${stream.device||''} · ${stream.units||'unit not recorded'}`.trim();
    if(labels[0].textContent.trim()!==label)return invalid('single-stream label differs from fixture');
    return {status:'ready',kind:'single-label',stream_uuid:stream.uuid};
  };
}

/** Independent wire oracle: no production decoder imports or cloned body reads. */
export function installBinaryTraceOracle(){
 window.__workflowDecodeBinaryTrace=buffer=>{
  const fail=()=>{throw Error('Invalid binary trace oracle envelope');};
  if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<8||buffer.byteLength>8+65536+7+1000000*8)fail();
  const view=new DataView(buffer),bytes=new Uint8Array(buffer);
  if(String.fromCharCode(...bytes.subarray(0,4))!=='DTF1')fail();
  const length=view.getUint32(4,true),offset=Math.ceil((8+length)/8)*8;
  if(!length||length>65536||offset>buffer.byteLength)fail();
  for(let i=8+length;i<offset;i++)if(bytes[i]!==0)fail();
  let header;try{header=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes.subarray(8,8+length)));}catch{fail();}
  if(!header||!Array.isArray(header.windows)||!header.windows.length||header.windows.length>10||!Number.isSafeInteger(header.start)||header.start<0||!Number.isSafeInteger(header.count)||header.count<1||header.count>1000000||!Number.isSafeInteger(header.total_samples)||header.start+header.count>header.total_samples)fail();
  const little=new Uint8Array(new Uint16Array([1]).buffer)[0]===1;
  let position=0,cursor=header.start;
  const windows=header.windows.map(window=>{
   if(!window||Object.hasOwn(window,'values')||!Number.isSafeInteger(window.count)||window.count<1||window.count>100000||window.start!==cursor||window.byte_offset!==position||window.byte_length!==window.count*8||position+window.byte_length>buffer.byteLength-offset)fail();
   for(const key of ['epoch_uuid','stream_uuid','source_sha256','sample_rate','units','total_samples','decimated'])if(window[key]!==header[key])fail();
   if(typeof window.epoch_uuid!=='string'||!window.epoch_uuid||typeof window.stream_uuid!=='string'||!window.stream_uuid||typeof window.source_sha256!=='string'||!/^[a-f0-9]{64}$/.test(window.source_sha256)||!Number.isFinite(window.sample_rate)||window.sample_rate<=0||window.decimated!==false)fail();
   const values=little?new Float64Array(buffer,offset+position,window.count):Float64Array.from({length:window.count},(_,i)=>view.getFloat64(offset+position+i*8,true));
   if(values.some(v=>!Number.isFinite(v)))fail();
   position+=window.byte_length;cursor+=window.count;
   return {...window,values};
  });
  if(cursor!==header.start+header.count||position!==buffer.byteLength-offset)fail();
  return {...header,windows};
 };
}

/** Runs before product code. Ordinary and profile runs share the same lightweight
 * transport observer; React CPU collection and server profiler opt in separately. */
export function installObserver(config={}) {
  const state = window.__workflow = {active:null,profile:config.phase==='profile',module_timing:config.module_timing===true,requests:[],renders:[],draws:[]};
  const original=window.fetch.bind(window);
  window.fetch=async (input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(!url.pathname.startsWith('/api/'))return original(input,options);
    const action=state.active;
    const row={action_id:action?.action_id||null,...(!action&&state.last_completed_action_id?{after_action_id:state.last_completed_action_id}:{}),url:url.pathname+url.search,start:absolute(),method:options.method||'GET'};
    state.requests.push(row);
    const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));
    if(state.module_timing)headers.set('X-Disco-Timing','1');
    if(action){headers.set('X-Benchmark-Action',action.action_id);headers.set('X-Benchmark-Profile',action.phase==='profile'?'1':'0');}
    try {const response=await original(input,{...options,headers});row.headers=absolute();row.status=response.status;row.request_id=response.headers.get('X-Benchmark-Request-Id');row.content_type=response.headers.get('Content-Type');
      // Observe the actual consumer, avoiding a cloned body/read in timed path.
      const json=response.json.bind(response);response.json=async()=>{try{row.decode_start=absolute();const value=await json();row.end=absolute();row.result=value;return value;}catch(e){row.end=absolute();row.error=String(e);throw e;}};
      if(typeof response.arrayBuffer==='function'){
       const arrayBuffer=response.arrayBuffer.bind(response);
       response.arrayBuffer=async()=>{try{row.decode_start=absolute();const value=await arrayBuffer();row.end=absolute();row.binary=value;return value;}catch(e){row.end=absolute();row.error=String(e);throw e;}};
      }
      return response;
    }catch(e){row.end=absolute();row.error=String(e);throw e;}
  };
  function absolute(){return performance.now();}
  const stroke=CanvasRenderingContext2D.prototype.stroke;
  CanvasRenderingContext2D.prototype.stroke=function(...args){const tracked=this.canvas.classList.contains('tv-base')&&this.strokeStyle===getComputedStyle(this.canvas).getPropertyValue('--plot-trace').trim();const result=stroke.apply(this,args);if(tracked){const control=window.__workflowReadStream(this.canvas.closest('.trace-viewer'));state.draws.push({at:absolute(),action_id:state.active?.action_id,stream_uuid:control.stream_uuid,control});}return result;};
}
