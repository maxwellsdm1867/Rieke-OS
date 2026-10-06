import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,ChevronDown,ChevronUp,Database,RefreshCw} from 'lucide-react';
import {api,humanize} from "../../api.js";
import ProtocolDiff,{CompactProtocolDiff} from './ProtocolDiff.jsx';

export default function ProtocolApplyPanel({candidate,protocols,disabled=false,onApplied,initialProtocolId=null,targetGroups=null,onBusyChange,pinnedExport=false}) {
  const [target,setTarget]=useState(initialProtocolId || ''),[generation,setGeneration]=useState(0);
  const [rawComparison,setComparison]=useState({data:null,loading:false,error:null});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState(null);
  const [expanded,setExpanded]=useState(true);
  const operation=useRef(null),lifetime=useRef(0);
  useEffect(()=>()=>{lifetime.current++;},[]);
  const revisionId=candidate?.revision_uuid;
  const comparisonKey=JSON.stringify([revisionId,target]);
  const comparison=rawComparison.key===comparisonKey?rawComparison:{data:null,loading:!!revisionId&&!!target,error:null};
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  useEffect(()=>{setExpanded(true);operation.current=null;lifetime.current++;setBusy(false);},[revisionId,target,generation]);
  useEffect(()=>{if(initialProtocolId)setTarget(initialProtocolId);},[initialProtocolId]);
  useEffect(()=>{
    setSuccess(null);setError('');
    if(!revisionId||!target){setComparison({data:null,loading:false,error:null});return;}
    const controller=new AbortController();setComparison({data:null,loading:true,error:null});
    api(`/explore/revisions/${revisionId}/compare-to-protocol`,{method:'POST',body:{protocol_uuid:target},signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setComparison({data,loading:false,error:null,key:comparisonKey});})
      .catch(error=>{if(!controller.signal.aborted)setComparison({data:null,loading:false,error:error.message,key:comparisonKey});});
    return()=>controller.abort();
  },[revisionId,target,generation]);
  async function apply(){
    if(!comparison.data||disabled||busy||!comparison.data.compatibility?.compatible)return;
    const token=lifetime.current;
    const request=operation.current||{root:`/explore/revisions/${revisionId}/propose-to-protocol`,body:{protocol_uuid:target,expected_binding_version:comparison.data.expected_binding_version,expected_query_revision:comparison.data.expected_query_revision,operation_uuid:crypto.randomUUID()}};
    operation.current=request;setBusy(true);setError('');
    try{
      const result=await api(request.root,{method:'POST',body:request.body});
      if(token!==lifetime.current)return;
      if(result.contract_version!==1||result.review_kind!=='replacement'||result.operation_uuid!==request.body.operation_uuid||result.protocol_uuid!==request.body.protocol_uuid||typeof result.candidate_revision_uuid!=='string')throw new Error('The proposal service did not return a frozen review identity.');
      setSuccess(result);onApplied?.(target,result);
    }catch(error){if(token===lifetime.current){setError(error.message);if(error.status===409&&!error.saved){operation.current=null;setComparison(value=>({...value,data:null}));}}}finally{if(token===lifetime.current)setBusy(false);}
  }
  const canApply=comparison.data?.compatibility?.compatible&&Number.isInteger(comparison.data.expected_binding_version)&&typeof comparison.data.expected_query_revision==='string';
  return <section className="mx-protocol-apply" aria-label="Apply candidate selection to protocol">
    <div className="mx-protocol-target"><Database size={16}/><div><strong>Protocol working dataset</strong></div>
      <select aria-label="Target protocol" value={target} disabled={busy||!!operation.current} onChange={event=>setTarget(event.target.value)}><option value="">Choose a protocol…</option>{targetGroups?targetGroups.map(group=><optgroup key={group.label} label={group.label}>{group.protocols.map(protocol=><option key={protocol.protocol_uuid} value={protocol.protocol_uuid}>{humanize(protocol.name)}</option>)}</optgroup>):protocols.map(protocol=><option key={protocol.protocol_uuid} value={protocol.protocol_uuid}>{humanize(protocol.name)}</option>)}</select>
      {target&&comparison.data&&<button className="protocol-diff-toggle" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?<ChevronUp size={13}/>:<ChevronDown size={13}/>} {expanded?'Hide changes':'Show changes'}</button>}
    </div>
    {target&&<>
      {comparison.data?.compatibility&&<div className="protocol-identity-summary"><strong>Destination Protocol ID</strong><code>{comparison.data.compatibility.expected_protocol_id}</code>{comparison.data.compatibility.compatible?<span>All {comparison.data.compatibility.epoch_count.toLocaleString()} selected epochs match this acquisition protocol.</span>:<p role="alert">{comparison.data.compatibility.epoch_count?`${comparison.data.compatibility.incompatible_epoch_count.toLocaleString()} epochs belong to a different acquisition protocol. Choose a matching destination or create a new pinned protocol.`:'No epochs selected. Change your search before updating.'}</p>}{!comparison.data.compatibility.compatible&&comparison.data.compatibility.protocols.map(row=><div key={row.protocol_id}><code>{row.protocol_id}</code><span>{row.epoch_count.toLocaleString()} epochs</span></div>)}</div>}
      {expanded&&comparison.data&&!comparison.loading&&<ProtocolDiff key={`${revisionId}:${target}:${generation}`} comparison={comparison.data} showProtocolCount={!pinnedExport}/>}
      {comparison.data?.diff_counts?.removed>0&&<p>These removals require explicit approval in Workbench. Submitting this proposal keeps the current pinned dataset unchanged.</p>}
      <div className="mx-protocol-comparison protocol-diff-actions">
        {comparison.loading?<span>Comparing the saved candidate…</span>:comparison.error?<span role="alert">{comparison.error}</span>:!expanded&&comparison.data?<CompactProtocolDiff comparison={comparison.data}/>:null}
        <button aria-label="Refresh protocol comparison" disabled={busy||comparison.loading||!!operation.current} onClick={()=>setGeneration(value=>value+1)}><RefreshCw size={13}/></button>
        <button className="primary" disabled={disabled||busy||!canApply||comparison.loading||!!success} onClick={apply}>{busy?'Submitting…':'Review in Workbench'}<ArrowRight size={13}/></button>
      </div>
    </>}
    {disabled&&target&&<p>Save the current candidate revision before applying it to this protocol.</p>}
    {error&&<p role="alert" className="mx-validation">{error} Retry submission to recover an uncertain result. If the comparison is stale, refresh it before retrying.</p>}
    {success&&<p><Check size={13}/> Proposal saved for Workbench review. The pinned dataset is unchanged.</p>}
  </section>;
}
