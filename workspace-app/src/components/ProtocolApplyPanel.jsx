import {useEffect,useState} from 'react';
import {ArrowRight,Check,ChevronDown,ChevronUp,Database,RefreshCw} from 'lucide-react';
import {api,humanize} from '../api.js';
import ProtocolDiff,{CompactProtocolDiff} from './ProtocolDiff.jsx';

export default function ProtocolApplyPanel({candidate,protocols,disabled=false,onApplied,initialProtocolId=null,targetGroups=null,onBusyChange,pinnedExport=false}) {
  const [target,setTarget]=useState(initialProtocolId || ''),[generation,setGeneration]=useState(0);
  const [rawComparison,setComparison]=useState({data:null,loading:false,error:null});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState(null);
  const [expanded,setExpanded]=useState(true),[acceptRemoval,setAcceptRemoval]=useState(false);
  const revisionId=candidate?.revision_uuid;
  const comparisonKey=JSON.stringify([revisionId,target]);
  const comparison=rawComparison.key===comparisonKey?rawComparison:{data:null,loading:!!revisionId&&!!target,error:null};
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  useEffect(()=>{setExpanded(true);setAcceptRemoval(false);},[revisionId,target,generation]);
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
    if(!comparison.data||disabled||busy||!comparison.data.compatibility?.compatible||(comparison.data.diff_counts?.removed>0&&!acceptRemoval))return;
    setBusy(true);setError('');
    try{
      const result=await api(`/explore/revisions/${revisionId}/apply-to-protocol`,{method:'POST',body:{protocol_uuid:target,expected_binding_version:comparison.data.expected_binding_version,expected_query_revision:comparison.data.expected_query_revision}});
      setSuccess(result);onApplied?.(target);
    }catch(error){setError(error.message);setComparison(value=>({...value,data:null}));}finally{setBusy(false);}
  }
  const targetName=protocols.find(protocol=>protocol.protocol_uuid===target)?.name;
  const canApply=comparison.data?.compatibility?.compatible&&(!(comparison.data.diff_counts?.removed>0)||acceptRemoval)&&Number.isInteger(comparison.data.expected_binding_version)&&typeof comparison.data.expected_query_revision==='string';
  return <section className="mx-protocol-apply" aria-label="Apply candidate selection to protocol">
    <div className="mx-protocol-target"><Database size={16}/><div><strong>Protocol working dataset</strong></div>
      <select aria-label="Target protocol" value={target} disabled={busy} onChange={event=>setTarget(event.target.value)}><option value="">Choose a protocol…</option>{targetGroups?targetGroups.map(group=><optgroup key={group.label} label={group.label}>{group.protocols.map(protocol=><option key={protocol.protocol_uuid} value={protocol.protocol_uuid}>{humanize(protocol.name)}</option>)}</optgroup>):protocols.map(protocol=><option key={protocol.protocol_uuid} value={protocol.protocol_uuid}>{humanize(protocol.name)}</option>)}</select>
      {target&&comparison.data&&<button className="protocol-diff-toggle" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?<ChevronUp size={13}/>:<ChevronDown size={13}/>} {expanded?'Hide changes':'Show changes'}</button>}
    </div>
    {target&&<>
      {comparison.data?.compatibility&&<div className="protocol-identity-summary"><strong>Destination Protocol ID</strong><code>{comparison.data.compatibility.expected_protocol_id}</code>{comparison.data.compatibility.compatible?<span>All {comparison.data.compatibility.epoch_count.toLocaleString()} selected epochs match this acquisition protocol.</span>:<p role="alert">{comparison.data.compatibility.epoch_count?`${comparison.data.compatibility.incompatible_epoch_count.toLocaleString()} epochs belong to a different acquisition protocol. Choose a matching destination or create a new pinned protocol.`:'No epochs selected. Change your search before updating.'}</p>}{!comparison.data.compatibility.compatible&&comparison.data.compatibility.protocols.map(row=><div key={row.protocol_id}><code>{row.protocol_id}</code><span>{row.epoch_count.toLocaleString()} epochs</span></div>)}</div>}
      {expanded&&comparison.data&&!comparison.loading&&<ProtocolDiff key={`${revisionId}:${target}:${generation}`} comparison={comparison.data} showProtocolCount={!pinnedExport}/>}
      {comparison.data?.compatibility?.compatible&&comparison.data.diff_counts?.removed>0&&<label className="protocol-removal-review"><input type="checkbox" checked={acceptRemoval} disabled={busy} onChange={event=>setAcceptRemoval(event.target.checked)}/>Use this narrower selection: remove {comparison.data.diff_counts.removed.toLocaleString()} epochs from this pinned dataset. Original recordings and shared tags remain stored.</label>}
      <div className="mx-protocol-comparison protocol-diff-actions">
        {comparison.loading?<span>Comparing the saved candidate…</span>:comparison.error?<span role="alert">{comparison.error}</span>:!expanded&&comparison.data?<CompactProtocolDiff comparison={comparison.data}/>:null}
        <button aria-label="Refresh protocol comparison" disabled={busy||comparison.loading} onClick={()=>setGeneration(value=>value+1)}><RefreshCw size={13}/></button>
        <button className="primary" disabled={disabled||busy||!canApply||comparison.loading||!!success} onClick={apply}>{busy?'Applying…':pinnedExport?'Update pinned protocol':`Apply to ${humanize(targetName || 'protocol')}`}<ArrowRight size={13}/></button>
      </div>
    </>}
    {disabled&&target&&<p>Save the current candidate revision before applying it to this protocol.</p>}
    {error&&<p role="alert" className="mx-validation">{error} Re-evaluate and save the candidate if its sources changed; refresh this comparison before retrying.</p>}
    {success&&<p><Check size={13}/> This protocol now uses revision {revisionId.slice(0,8)} for inspection and export.</p>}
  </section>;
}
