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

export default function IncomingSelectionSummary({projectId,protocolId,readContext,selected=[],paused=false}){
  const port=useWorkspaceRequestScope(),request=port?.request??api;
  const ids=selectedSummaryIds(selected),key=JSON.stringify([projectId,protocolId,readContext,ids,port?.identity]);
  const identity=useMemo(()=>({key}),[key,request,paused]),current=useRef(null);
  const [state,setState]=useState(null),[retry,setRetry]=useState(0);
  useLayoutEffect(()=>{current.current=identity;return()=>{current.current=null;};},[identity]);
  const enabled=readContext?.selection_summary===true&&Number.isSafeInteger(readContext.expected_binding_version)&&readContext.expected_binding_version>=0;
  useEffect(()=>{
    if(paused||!enabled||!ids?.length)return;
    const controller=new AbortController();
    setState({identity,loading:true});
    Promise.resolve().then(()=>{
      frozenReadQuery(readContext);
      return request(`${readContext.root}/selection-summary`,{method:'POST',signal:controller.signal,body:{candidate_scope_revision:readContext.candidate_scope_revision,epoch_uuids:ids}});
    }).then(value=>{
      if(controller.signal.aborted||current.current!==identity)return;
      setState({identity,data:validateSelectionSummary(value,ids,readContext)});
    }).catch(error=>{if(!controller.signal.aborted&&current.current===identity)setState({identity,error:error.message});});
    return()=>controller.abort();
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
