import {decodeTraceGeometry,TRACE_GEOMETRY_TYPE} from './traces/traceDisplayGeometry.js';
import {decodeTraceBinary,TRACE_BINARY_TYPE} from './traces/traceBinary.js';
import {useRetainedView,retainablePresentationRead} from './retainedWorkspaceViews.js';
import {useWorkspaceRequestScope} from './workspaceRequest.js';
import {mutationUndo,isUndoableRequest} from "./undo/mutationUndo.js";
import {startResourceRequest,visibleResourceState} from './resourceRequest.js';
import {cachedResourceRequest,epochResourceCache,peekEpochWithTrace,prefetchEpochMetadata,prefetchEpochTraces,prefetchTraceWindows,requestEpochWithTrace} from './resourceCache.js';
import {readWholeTrace,MAX_WHOLE_TRACE_CHUNK_SAMPLES} from './traces/readWholeTrace.js';
import {MAX_TRACE_SAMPLES} from './traces/ui/traceGeometry.js';
import { useCallback, useEffect, useRef, useState } from 'react';
import {trackWrite,assertDesktopWritable} from './desktopLifecycle.js';
export function createApiRequest(transport=requestApi){
 return function request(path,options={}){
  const write=['POST','PUT','PATCH','DELETE'].includes((options.method||'GET').toUpperCase());
  if(write){try{assertDesktopWritable(path);}catch(error){return Promise.reject(error);}}
  let token;
  try{if(isUndoableRequest(path,options))token=mutationUndo.begin();}catch(error){return Promise.reject(error);}
  const endRead=options.background!==true&&(!write||path==='/explore/epochs')?epochResourceCache.beginDemand():()=>{};
  let submission;
  try{submission=transport(path,token?{...options,headers:{...options.headers,'X-Rieke-Undo-Receipt':'1'}}:options);}catch(error){endRead();if(token)mutationUndo.failed(error);return Promise.reject(error);}
  const operation=Promise.resolve(submission).then(result=>{if(token)mutationUndo.complete(token,result.undo);return result;},error=>{if(token)mutationUndo.failed(error);throw error;}).finally(endRead);
  return write?trackWrite(operation):operation;
 };
}
export const api=createApiRequest();

// Canonical global trace identity: exact epoch, stream, source hash, rate,
// units and count under the caller's trace revision (structure/source events,
// never annotation or curation). Scoped/imported/prepared reads never use it.
export function wholeTraceIdentity(revision,epoch,stream){
  return JSON.stringify([revision,epoch?.epoch_uuid??null,epoch?.source_sha256??null,stream?.uuid??null,stream?.sample_count??null,stream?.sample_rate??null,stream?.units??null]);
}
const traceMatches=(value,epoch,stream,start,count)=>value?.epoch_uuid===epoch.epoch_uuid&&value.stream_uuid===stream.uuid&&value.start===start&&value.count===count&&value.values?.length===count&&
  (!epoch.source_sha256||value.source_sha256===epoch.source_sha256)&&(!Number.isFinite(stream.sample_rate)||value.sample_rate===stream.sample_rate)&&
  (stream.units===undefined||value.units===stream.units);
// An exact view of retained samples; nothing is resampled or copied for typed arrays.
function sliceTrace(trace,start,count){
  if(start===trace.start&&count===trace.count)return trace;
  const from=start-trace.start,values=trace.values instanceof Float64Array?trace.values.subarray(from,from+count):trace.values.slice(from,from+count);
  return {...trace,start,count,values};
}
// A window inside an already admitted whole stream is served from it: the
// decoded cache (streams over 20k) or the whole-stream window snapshot (<=20k).
function retainedWindow(revision,epoch,stream,start,count){
  if(!epoch?.epoch_uuid||!stream?.uuid||!Number.isSafeInteger(stream.sample_count)||start<0||start+count>stream.sample_count)return undefined;
  const whole=epochResourceCache.peekWholeTrace(wholeTraceIdentity(revision,epoch,stream));
  if(whole&&traceMatches(whole,epoch,stream,0,stream.sample_count))return sliceTrace(whole,start,count);
  // The exact whole-stream snapshot path keeps its normal demand admission.
  if(stream.sample_count>MAX_TRACE_SAMPLES||start===0&&count===stream.sample_count)return undefined;
  const snapshot=epochResourceCache.peek(`/epochs/${epoch.epoch_uuid}/trace?${new URLSearchParams({stream_uuid:stream.uuid,start:'0',count:String(stream.sample_count)})}`,revision);
  return snapshot&&traceMatches(snapshot,epoch,stream,0,stream.sample_count)?sliceTrace(snapshot,start,count):undefined;
}

// Canonical global trace reads reuse the prefetch key while checking the selected
// source/descriptor. Scoped/imported viewers retain their supplied request owner.
// Cache generations, stale warm/in-flight responses and fresh admission stay here,
// outside presentation. Cancellation and mismatch errors are never hidden.
export async function requestTraceWindow(path,{revision=0,signal,epoch,stream,window:{start,count}}){
  const matches=value=>traceMatches(value,epoch,stream,start,count);
  const retained=retainedWindow(revision,epoch,stream,start,count);
  if(retained)return retained;
  const warm=epochResourceCache.peek(path,revision);
  if(!warm||matches(warm)){
    const result=await cachedResourceRequest(path,{request:api,revision,signal});
    if(matches(result))return result;
  }
  const token=epochResourceCache.token(),fresh=await api(path,{signal});
  signal?.throwIfAborted();
  if(!matches(fresh))throw Error('Trace source or descriptor does not match the selected recording. Refresh and retry.');
  epochResourceCache.put(path,revision,fresh,token);
  return fresh;
}

// Canonical global whole-stream (>20k) demand. A complete validated stream is
// retained in the bounded decoded cache and answers later windows inside it.
// Partial windows outside a retained stream read exactly their own window.
export async function requestWholeTrace({revision=0,signal,epoch,stream,window={start:0,count:stream.sample_count},background=false}){
  const retained=retainedWindow(revision,epoch,stream,window.start,window.count);
  if(retained)return retained;
  const complete=window.start===0&&window.count===stream.sample_count;
  const request=background?(path,options)=>api(path,{...options,background:true}):api;
  const read=readSignal=>readWholeTrace({request,epochUuid:epoch.epoch_uuid,sourceSha256:epoch.source_sha256,stream,readContext:null,signal:readSignal,window,
    maxChunkSamples:complete?MAX_WHOLE_TRACE_CHUNK_SAMPLES:MAX_TRACE_SAMPLES});
  if(!complete)return read(signal);
  const id=wholeTraceIdentity(revision,epoch,stream),admission=epochResourceCache.token();
  const end=background?()=>{}:epochResourceCache.beginDemand();
  try{
    const trace=await epochResourceCache.pendingWholeTrace(id,read,{signal});
    signal?.throwIfAborted();
    if(!traceMatches(trace,epoch,stream,0,stream.sample_count))throw Error('Trace source or descriptor does not match the selected recording. Refresh and retry.');
    epochResourceCache.putWholeTrace(id,epoch.epoch_uuid,trace,admission);
    return trace;
  }finally{end();}
}

// Warm only the next epoch's first response stream (20k < count <= 1M samples)
// in the background, after the delay and while no demand read is running.
export const WHOLE_TRACE_WARM_MAX_SAMPLES=1000000;
export function warmNextWholeTrace(epoch,{revision=0,delayMs=180}={}){
  const stream=epoch?.streams?.find(item=>item.kind==='responses'&&Number.isSafeInteger(item.sample_count)&&item.sample_count>0);
  if(!epoch?.epoch_uuid||!stream?.uuid||stream.sample_count<=MAX_TRACE_SAMPLES||stream.sample_count>WHOLE_TRACE_WARM_MAX_SAMPLES)return()=>{};
  if(epochResourceCache.peekWholeTrace(wholeTraceIdentity(revision,epoch,stream)))return()=>{};
  const controller=new AbortController();
  const timer=setTimeout(async()=>{
    while(!controller.signal.aborted&&epochResourceCache.hasDemand())await new Promise(resolve=>setTimeout(resolve,8));
    if(controller.signal.aborted)return;
    try{await requestWholeTrace({revision,signal:controller.signal,epoch,stream,background:true});}catch{/* demand owns errors */}
  },Math.max(0,delayMs));
  return()=>{clearTimeout(timer);controller.abort();};
}
export function useWholeTraceWarm(epoch,revision=0,delayMs=180){
  const owner=useWorkspaceRequestScope(),active=useRetainedView()?.active!==false;
  const stream=epoch?.streams?.find(item=>item.kind==='responses'&&Number.isSafeInteger(item.sample_count)&&item.sample_count>0);
  const identity=epoch&&stream?JSON.stringify([epoch.epoch_uuid,epoch.source_sha256??null,stream.uuid,stream.sample_count,stream.sample_rate??null,stream.units??null]):null;
  const latest=useRef(epoch);latest.current=epoch;
  useEffect(()=>!active||owner||!identity?undefined:warmNextWholeTrace(latest.current,{revision,delayMs}),[identity,revision,delayMs,owner,active]);
}

export class PreparationRequiredError extends Error {
  constructor(data){super('Prepare this view to continue.');this.name='PreparationRequiredError';this.status=202;this.data=data;this.preparation=data.preparation;}
}
export async function requestApi(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...Object.fromEntries(Object.entries(options).filter(([key])=>key!=='undoOperation'&&key!=='background'&&key!=='onResponse'&&key!=='notModified')), headers: { 'Content-Type': 'application/json', 'X-Workspace-Request': '1', ...(options.background===true?{'X-Disco-Trace-Priority':'background'}:{}), ...options.headers },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if(response.status===304&&options.notModified&&options.headers?.['If-None-Match']){
    options.onResponse?.({status:304,headers:response.headers});
    return options.notModified;
  }
  let decoded=true;
  const contentType=(response.headers?.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
  const binaryRequested=options.headers?.Accept===TRACE_BINARY_TYPE,geometryRequested=options.headers?.Accept===TRACE_GEOMETRY_TYPE;
  if(contentType===TRACE_BINARY_TYPE&&!binaryRequested||contentType===TRACE_GEOMETRY_TYPE&&!geometryRequested||
    binaryRequested&&response.ok&&![TRACE_BINARY_TYPE,'application/json'].includes(contentType)||
    geometryRequested&&response.ok&&contentType!==TRACE_GEOMETRY_TYPE)
    throw Error('Unexpected trace response representation. No plot is shown.');
  const data = contentType===TRACE_GEOMETRY_TYPE?decodeTraceGeometry(await response.arrayBuffer()):contentType===TRACE_BINARY_TYPE?decodeTraceBinary(await response.arrayBuffer()):
    await response.json().catch(() => {decoded=false;return {};});
  if(response.status===202&&data?.status==='preparing'&&data?.preparation?.status==='pending')throw new PreparationRequiredError(data);
  if (!response.ok) {const message=typeof data.error==='string'?data.error:typeof data.error?.message==='string'?data.error.message:typeof data.message==='string'?data.message:`Request failed (${response.status})`;const error=new Error(message);error.status=response.status;error.data=data;if(data.saved===true)error.saved=true;if(data.persistence)error.persistence=data.persistence;throw error;}
  if(decoded&&typeof options.onResponse==='function')options.onResponse({status:response.status,headers:response.headers});
  return data;
}
export function useResource(path, revision = 0, delayMs = 0, options = {}) {
  const inherited=useWorkspaceRequestScope(),owner=options.requestPort===undefined?inherited:options.requestPort;
  const transport=owner?(typeof owner.request==='function'?owner.request:()=>Promise.reject(Error('Workspace request authority is unavailable.'))):api;
  const cached=!owner&&options.cache===true,warmEpoch=!owner&&options.warmEpoch===true,paused=options.paused===true;
  const retainedView=useRetainedView(),retentionIdentity=retainedView?.identity,active=retainedView?.active!==false;
  const retained=!!retainedView&&!owner&&!options.initialRead&&!cached&&retainablePresentationRead(path);
  const completedRead=useRef(null);
  const [state, setState] = useState({data: null, loading: true, error: null});
  const [nonce, setNonce] = useState(0);
  const initialConsumer=useRef({}),initialLifetime=useRef(null),retiredOffers=useRef(new WeakSet()),initialRead=options.initialRead;
  // The caller owns the offer; this hook owns its one mounted read lifetime.
  // Owner/path/revision/pause/reload changes retire it before effects, including
  // A-B-A transitions. Custom ports and caches never consume an HTTP offer.
  if(!initialLifetime.current||initialLifetime.current.offer!==initialRead){
    if(initialLifetime.current?.offer&&typeof initialLifetime.current.offer==='object')retiredOffers.current.add(initialLifetime.current.offer);
    initialLifetime.current={offer:initialRead,path,revision,owner,retired:nonce!==0||paused||!active||!!owner||cached||!!initialRead&&retiredOffers.current.has(initialRead)};
  }else if(initialLifetime.current.path!==path||initialLifetime.current.revision!==revision||initialLifetime.current.owner!==owner||nonce!==0||paused||!active||cached)initialLifetime.current.retired=true;
  if(initialLifetime.current.retired&&initialRead&&typeof initialRead==='object')retiredOffers.current.add(initialRead);

  const reload = useCallback(() => {if(cached)epochResourceCache.invalidate(path,{related:warmEpoch});setNonce(n => n + 1);}, [path,cached,warmEpoch]);
  useEffect(() => {
    // A draft write invalidates its read token before the replacement receipt
    // arrives. Cancel delayed/in-flight reads while retaining inert content.
    // Pending writes may keep a hidden Activity mounted. Read demand follows
    // retained visibility independently; write/command owners stay untouched.
    if(paused||!active)return;
    if (!path) {completedRead.current=null;setState({data: null, loading: false, error: null}); return;}
    const completed=completedRead.current;
    if(retained&&completed?.path===path&&completed.revision===revision&&completed.nonce===nonce&&completed.retentionIdentity===retentionIdentity)return;
    if(!initialLifetime.current.retired&&typeof initialRead?.claim==='function'){
      try{
        const data=initialRead.claim({consumer:initialConsumer.current,path,revision});
        if(data!==undefined){setState({data,loading:false,error:null,path,revision,nonce,owner,initialRead,fromInitialRead:true});return;}
      }catch(error){setState({data:null,loading:false,error:error.message,path,revision,nonce,owner,initialRead});return;}
    }
    const complete=cached&&warmEpoch?peekEpochWithTrace(path,revision):undefined;
    if(complete!==undefined){epochResourceCache.get(path,revision);setState({data:complete,loading:false,error:null,path,revision,nonce,owner,initialRead});return;}
    setState(previous => previous.path === path && previous.owner===owner ? {...previous, loading:true, error:null} : {data:null,loading:true,error:null,path});
    const request=cached?(url,{signal})=>(warmEpoch?requestEpochWithTrace:cachedResourceRequest)(url,{request:api,signal,revision}):transport;
    return startResourceRequest({path,delayMs,request,
      onData:data=>{const next={data,loading:false,error:null,path,revision,nonce,owner,initialRead,retentionIdentity};completedRead.current=next;setState(next);},
      onError:error=>{completedRead.current=null;setState({data:null,loading:false,error:error.message,preparation:error.preparation||null,errorStatus:Number.isInteger(error.status)?error.status:null,path,revision,nonce,owner,initialRead,retentionIdentity});}});
  }, [path, revision, nonce, delayMs,cached,warmEpoch,paused,active,owner,transport,initialRead,retained,retentionIdentity]);
  // Complete metadata/trace pairs publish in the same render; partial snapshots
  // start I/O immediately unless the caller explicitly requests a delay.
  // Both paths retain exact path/revision/reload publication fences.
  const hit=cached&&path?(warmEpoch?peekEpochWithTrace(path,revision):epochResourceCache.peek(path,revision)):undefined;
  const visible=visibleResourceState({state:(!retained||state.retentionIdentity===retentionIdentity)&&state.owner===owner&&state.initialRead===initialRead&&(!state.fromInitialRead||!initialLifetime.current.retired)?state:{},path,revision,nonce,hit});
  return {...visible,loading:paused&&!!path||visible.loading,reload};
}
export function useEpochResource(path,revision=0,delayMs=0){return useResource(path,revision,delayMs,{cache:true,warmEpoch:true});}
export function prefetchResources(paths,revision=0,{delayMs=180}={}){return prefetchEpochMetadata(paths,{request:api,revision,delayMs});}
export function useEpochPrefetch(paths,revision=0,delayMs=180,{traces=false,traceOnly=false,progressive=false,concurrency=1}={}){
  const owner=useWorkspaceRequestScope(),active=useRetainedView()?.active!==false;
  const identity=JSON.stringify(paths||[]);
  useEffect(()=>!active||owner?undefined:traceOnly?prefetchTraceWindows(JSON.parse(identity),{request:api,revision,delayMs,progressive,concurrency}):traces?prefetchEpochTraces(JSON.parse(identity),{request:api,revision,delayMs,progressive,concurrency}):prefetchResources(JSON.parse(identity),revision,{delayMs}),[identity,revision,delayMs,owner,active,traces,traceOnly,progressive,concurrency]);
}
export const number = value => Number(value || 0).toLocaleString();
export const duration = seconds => seconds == null ? 'Unknown' : seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
export const humanize = value => String(value || '').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^RGC\\/, '').replace(/Cur Inject/g, 'current injection');
export const time = value => value ? new Date(value).toLocaleString(undefined, {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}) : '—';

// Individual epoch controls must never inherit an unrelated bulk selection.
export function resolveCurationTargets(focused, targets = [], scope = 'selection') {
  if (!['selection', 'focused'].includes(scope)) throw new Error('Unknown curation action scope');
  if (scope === 'focused') return focused ? [focused] : [];
  return targets.length ? [...new Set(targets)] : focused ? [focused] : [];
}

// Review is an optional export filter; excluded epochs never become eligible.
export function eligibleExportCount(counts, policy) {
  const value = policy === 'include_unreviewed' ? counts.included :
    policy === 'approved_only' ? (counts.approved_exportable ?? counts.exportable) : undefined;
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}
