import {useEffect,useState} from 'react';
import {useResource} from '../api.js';
import {useWorkspaceRequestScope} from '../workspaceRequest.js';

// Values are optional. An admitted page row owns the lightweight trace identity;
// a one-shot value request never follows focus or request-authority changes.
export function useEpochInspection({focused,path,row,scope,revision=0,cache=true,paused=false,reloadRow,readContext=null}){
  const owner=useWorkspaceRequestScope();
  const [live,setLive]=useState(()=>{try{return localStorage.getItem('workspace.inspector.liveMetadata')==='true';}catch{return false;}});
  const [demand,setDemand]=useState(null),[selected,setSelected]=useState(null);
  const key=JSON.stringify([scope,focused,path,revision,paused]);
  useEffect(()=>setDemand(previous=>previous?.key===key&&previous.owner===owner?previous:null),[key,owner]);
  const requested=live||demand?.key===key&&demand.owner===owner;
  const selectedRow=selected?.scope===scope&&selected.owner===owner&&selected.row?.epoch_uuid===focused?selected.row:null;
  const candidate=row?.epoch_uuid===focused?row:selectedRow;
  const lightweight=candidate&&Array.isArray(candidate.streams)?candidate:null;
  // A scoped page may omit the attested trace descriptor. Its existing detail
  // endpoint remains required until the owner supplies that descriptor in rows.
  // Hidden values never authorize a global trace fallback.
  const needsDescriptor=!!owner&&!readContext&&!lightweight?.trace_read_context&&!owner.traceReadContext&&
    (!lightweight||lightweight.streams.some(stream=>stream.kind==='responses'&&stream.sample_count!==0));
  const values=useResource(requested||needsDescriptor?path:null,revision,0,{cache,paused});
  const matchingValues=values.data?.epoch_uuid===focused?values.data:null;
  const descriptor=needsDescriptor&&matchingValues?.trace_read_context&&Array.isArray(matchingValues.streams)?
    {...lightweight,epoch_uuid:focused,streams:matchingValues.streams,trace_read_context:matchingValues.trace_read_context}:null;
  // Metadata values can arrive independently; the admitted row already owns
  // trace identity in live mode too. Required scoped descriptors still gate it.
  const data=paused?null:needsDescriptor?descriptor:lightweight??(live?matchingValues:null);
  const missingLocator=needsDescriptor?!!matchingValues&&!descriptor:!live&&candidate&&!lightweight;
  const resource={data,loading:!!focused&&!data&&!missingLocator&&!((needsDescriptor||live&&!lightweight)&&values.error),
    error:missingLocator?'Trace information is unavailable in this epoch page. Refresh the epoch list.':needsDescriptor||live&&!lightweight?values.error:null,reload:needsDescriptor||live&&!lightweight?values.reload:reloadRow};
  function toggle(value){setLive(value);setDemand(null);try{localStorage.setItem('workspace.inspector.liveMetadata',String(value));}catch{}}
  function load(){if(!path||!focused||paused)return;if(requested)values.reload();else setDemand({key,owner});}
  return {live,resource,selectRow:next=>setSelected({row:next,scope,owner}),
    metadata:{live,row:paused?null:lightweight,onLiveChange:toggle,requested:!!path&&requested,load,
      values:{...values,data:requested&&!paused?matchingValues:null},canLoad:!!path&&!!focused&&!paused}};
}
