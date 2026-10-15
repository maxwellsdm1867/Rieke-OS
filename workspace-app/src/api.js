import {decodeTraceGeometry,TRACE_GEOMETRY_TYPE} from './traces/traceDisplayGeometry.js';
import {decodeTraceBinary,TRACE_BINARY_TYPE} from './traces/traceBinary.js';
import {useRetainedView,retainablePresentationRead} from './retainedWorkspaceViews.js';
import {useWorkspaceRequestScope} from './workspaceRequest.js';
import {mutationUndo,isUndoableRequest} from "./undo/mutationUndo.js";
import {startResourceRequest,visibleResourceState} from './resourceRequest.js';
import {cachedResourceRequest,epochResourceCache,peekEpochWithTrace,prefetchEpochMetadata,prefetchEpochTraces,prefetchTraceWindows,requestEpochWithTrace} from './resourceCache.js';
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

// Canonical global trace reads reuse the prefetch key while checking the selected
// source/descriptor. Scoped/imported viewers retain their supplied request owner.
// Cache generations, stale warm/in-flight responses and fresh admission stay here,
// outside presentation. Cancellation and mismatch errors are never hidden.
export async function requestTraceWindow(path,{revision=0,signal,epoch,stream,window:{start,count}}){
  const matches=value=>value?.epoch_uuid===epoch.epoch_uuid&&value.stream_uuid===stream.uuid&&value.start===start&&value.count===count&&value.values?.length===count&&
    (!epoch.source_sha256||value.source_sha256===epoch.source_sha256)&&(!Number.isFinite(stream.sample_rate)||value.sample_rate===stream.sample_rate)&&
    (stream.units===undefined||value.units===stream.units);
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
      onError:error=>{completedRead.current=null;setState({data:null,loading:false,error:error.message,errorStatus:Number.isInteger(error.status)?error.status:null,path,revision,nonce,owner,initialRead,retentionIdentity});}});
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
