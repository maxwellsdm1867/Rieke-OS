import {createWorkbenchSelection} from '../workbenchAuthority.js';
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Activity,Shapes,RefreshCw} from 'lucide-react';
import {api,number} from '../../api.js';
import {useWorkspaceRequestScope} from '../../workspaceRequest.js';
import {frozenReadQuery} from '../../epoch-browser/frozenReadContext.js';
import NeuronIcon from '../../components/NeuronIcon.jsx';
import IncomingCellTypes from './IncomingCellTypes.jsx';
import {incomingCellTypes} from '../incomingCellTypes.js';
import {isUnclassifiedType} from '../../cell-qc/cellTypes.js';
import {selectedSummaryIds,validateSelectionSummary} from '../incomingSelectionSummary.js';
import './IncomingSelectionSummary.css';

// Selection toggles arrive in bursts; each read may upload a large manifest.
const SUMMARY_SETTLE_MS=250;

export default function IncomingSelectionSummary({projectId,protocolId,readContext,selected=[],paused=false,settleMs=SUMMARY_SETTLE_MS}){
  const port=useWorkspaceRequestScope(),request=port?.request??api;
  // Memoized on the selection array reference: sorting and serializing 10k ids
  // happens once per selection change, not on every render.
  const ids=useMemo(()=>selectedSummaryIds(selected),[selected]),idsKey=useMemo(()=>JSON.stringify(ids),[ids]);
  const key=JSON.stringify([projectId,protocolId,readContext,port?.identity])+idsKey;
  const identity=useMemo(()=>({key}),[key,request,paused]),current=useRef(null),started=useRef(false),manifestCache=useRef(null);
  const [state,setState]=useState(null),[retry,setRetry]=useState(0);
  useLayoutEffect(()=>{current.current=identity;return()=>{current.current=null;};},[identity]);
  const enabled=readContext?.selection_summary===true&&Number.isSafeInteger(readContext.expected_binding_version)&&readContext.expected_binding_version>=0;
  useEffect(()=>{
    if(paused||!enabled||!ids?.length)return;
    const controller=new AbortController();
    setState({identity,loading:true});
    // The first read is immediate; later selection changes settle first.
    const delay=started.current?settleMs:0;started.current=true;
    // One manifest token per exact selection and scope: pause/resume and
    // repeated reads of the same selection reuse it instead of re-uploading.
    const manifestKey=JSON.stringify([readContext.root,readContext.candidate_scope_revision,readContext.expected_binding_version,port?.identity])+idsKey;
    let usedCached=false;
    const run=async()=>{
      frozenReadQuery(readContext);
      let token=null;
      if(ids.length>1000&&readContext.selection_manifests===true){
        if(manifestCache.current?.key===manifestKey){token=manifestCache.current.token;usedCached=true;}
        else{
          const manifest=await createWorkbenchSelection({root:readContext.root,context:{...readContext,draft:{draft_version:0}},ids,signal:controller.signal},request);
          token=manifest.selection_token;manifestCache.current={key:manifestKey,token};
        }
      }
      return request(`${readContext.root}/selection-summary`,{method:'POST',signal:controller.signal,body:{candidate_scope_revision:readContext.candidate_scope_revision,...(token?{selection_token:token}:{epoch_uuids:ids})}});
    };
    const timer=setTimeout(()=>{run().then(value=>{
      if(controller.signal.aborted||current.current!==identity)return;
      setState({identity,data:validateSelectionSummary(value,ids,readContext)});
    }).catch(error=>{
      // A refused cached token is never retried silently; Retry uploads afresh.
      if(usedCached&&manifestCache.current?.key===manifestKey)manifestCache.current=null;
      if(!controller.signal.aborted&&current.current===identity)setState({identity,error:error.message});
    });},delay);
    return()=>{clearTimeout(timer);controller.abort();};
  },[identity,enabled,paused,retry]);
  const empty=ids?.length===0,data=empty?{cells:[],counts:{cells:0}}:!paused&&state?.identity===identity&&!state.loading?state.data:null;
  const groups=data?incomingCellTypes(data.cells,data.counts.cells):null;
  const typeCount=groups?.filter(group=>!isUnclassifiedType(group.type)).length;
  const error=!paused&&state?.identity===identity?state.error:null;
  const count=value=>value==null?'—':number(value);
  const live=empty||!!data,status=live?'Live':paused?'Paused':error||!enabled?'Unavailable':'Updating';
  return <header className="selection-summary" aria-label="Current selection" aria-busy={!empty&&!!ids&&enabled&&!paused&&!data&&!error}>
    <div className="selection-summary-heading"><strong>Current selection</strong><small className="selection-summary-live" data-live={live}><i aria-hidden="true"/>{status}</small></div>
    <div className="selection-summary-metric" aria-label={`${count(ids?.length)} selected epochs`}><Activity size={14} aria-hidden="true"/><span><strong key={count(ids?.length)}>{count(ids?.length)}</strong><small>Epochs</small></span></div>
    <div className="selection-summary-metric" aria-label={`${count(data?.counts.cells)} selected cells`}><NeuronIcon size={14}/><span><strong key={count(data?.counts.cells)}>{count(data?.counts.cells)}</strong><small>Cells</small></span></div>
    <div className="selection-summary-types">
      <IncomingCellTypes cells={data?.cells} count={data?.counts.cells} scope="Current selection" trigger={<span className="selection-summary-metric"><Shapes size={14} aria-hidden="true"/><span><strong key={count(typeCount)}>{count(typeCount)}</strong><small title="Recorded types; unclassified cells appear in the breakdown">Cell types</small></span></span>}/>
      {error&&<button className="selection-summary-retry" aria-label="Retry selection details" title={error} onClick={()=>setRetry(value=>value+1)}><RefreshCw size={12}/></button>}
    </div>
    <span className="selection-summary-announcement" role="status">{live?`Current selection: ${count(ids?.length)} epochs, ${count(data?.counts.cells)} cells, ${count(typeCount)} recorded cell types.`:`Current selection: ${count(ids?.length)} epochs. Selection details ${status.toLowerCase()}.`}</span>
  </header>;
}
