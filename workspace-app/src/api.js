import {startResourceRequest,visibleResourceState} from './resourceRequest.js';
import {cachedResourceRequest,epochResourceCache,prefetchEpochMetadata,requestEpochWithTrace} from './resourceCache.js';
import { useCallback, useEffect, useState } from 'react';
import {trackWrite} from './desktopLifecycle.js';
export function api(path,options={}){
  const operation=requestApi(path,options);
  return ['POST','PUT','PATCH','DELETE'].includes((options.method||'GET').toUpperCase())?trackWrite(operation):operation;
}
async function requestApi(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options, headers: { 'Content-Type': 'application/json', 'X-Workspace-Request': '1', ...options.headers },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.message || `Request failed (${response.status})`);
  return data;
}
export function useResource(path, revision = 0, delayMs = 0, options = {}) {
  const cached=options.cache===true,warmEpoch=options.warmEpoch===true;
  const [state, setState] = useState({data: null, loading: true, error: null});
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => {if(cached)epochResourceCache.invalidate(path,{related:warmEpoch});setNonce(n => n + 1);}, [path,cached,warmEpoch]);
  useEffect(() => {
    if (!path) {setState({data: null, loading: false, error: null}); return;}
    setState(previous => previous.path === path ? {...previous, loading:true, error:null} : {data:null,loading:true,error:null,path});
    const request=cached?(url,{signal})=>(warmEpoch?requestEpochWithTrace:cachedResourceRequest)(url,{request:api,signal,revision}):api;
    return startResourceRequest({path,delayMs,request,
      onData:data=>setState({data,loading:false,error:null,path,revision,nonce}),
      onError:error=>setState({data:null,loading:false,error:error.message,path,revision,nonce})});
  }, [path, revision, nonce, delayMs,cached,warmEpoch]);
  // A warmed trace is available during render, before a newly focused epoch can
  // paint beside the old waveform. Warm-epoch publication still waits for I/O.
  const hit=cached&&!warmEpoch&&path?epochResourceCache.peek(path,revision):undefined;
  const visible=visibleResourceState({state,path,revision,nonce,hit});
  return {...visible, reload};
}
export function useEpochResource(path,revision=0,delayMs=80){return useResource(path,revision,delayMs,{cache:true,warmEpoch:true});}
export function prefetchResources(paths,revision=0,{delayMs=180}={}){return prefetchEpochMetadata(paths,{request:api,revision,delayMs});}
export function useEpochPrefetch(paths,revision=0,delayMs=180){
  const identity=JSON.stringify(paths||[]);
  useEffect(()=>prefetchResources(JSON.parse(identity),revision,{delayMs}),[identity,revision,delayMs]);
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
