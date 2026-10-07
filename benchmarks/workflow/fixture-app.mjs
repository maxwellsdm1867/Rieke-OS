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

/** Runs before product code. Ordinary and profile runs share the same lightweight
 * transport observer; React CPU collection and server profiler opt in separately. */
export function installObserver(config={}) {
  const state = window.__workflow = {active:null,profile:config.phase==='profile',requests:[],renders:[],draws:[]};
  const original=window.fetch.bind(window);
  window.fetch=async (input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(!url.pathname.startsWith('/api/'))return original(input,options);
    const action=state.active;
    const row={action_id:action?.action_id||null,...(!action&&state.last_completed_action_id?{after_action_id:state.last_completed_action_id}:{}),url:url.pathname+url.search,start:absolute(),method:options.method||'GET'};
    state.requests.push(row);
    const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));
    if(action){headers.set('X-Benchmark-Action',action.action_id);headers.set('X-Benchmark-Profile',action.phase==='profile'?'1':'0');}
    try {const response=await original(input,{...options,headers});row.headers=absolute();row.status=response.status;row.request_id=response.headers.get('X-Benchmark-Request-Id');
      // Observe the actual consumer, avoiding a cloned body/read in timed path.
      const json=response.json.bind(response);response.json=async()=>{try{row.decode_start=absolute();const value=await json();row.end=absolute();row.result=value;return value;}catch(e){row.end=absolute();row.error=String(e);throw e;}};
      return response;
    }catch(e){row.end=absolute();row.error=String(e);throw e;}
  };
  function absolute(){return performance.now();}
  const stroke=CanvasRenderingContext2D.prototype.stroke;
  CanvasRenderingContext2D.prototype.stroke=function(...args){if(this.canvas.classList.contains('tv-base')&&this.strokeStyle===getComputedStyle(this.canvas).getPropertyValue('--plot-trace').trim())state.draws.push({at:absolute(),action_id:state.active?.action_id,stream_uuid:this.canvas.closest('.trace-viewer')?.querySelector('[aria-label="Response stream"]')?.value});return stroke.apply(this,args);};
}
