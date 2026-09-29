import {useEffect,useState} from 'react';
import {ArrowLeft,ArrowRight,Check,ChevronDown,ChevronUp,Database,RefreshCw} from 'lucide-react';
import {api,humanize,number} from '../api.js';
import {Empty,Status} from './Common.jsx';
import ProtocolDiff,{CompactProtocolDiff} from './ProtocolDiff.jsx';
import './SourcePropagation.css';

export default function SourcePropagation({source,onBack,onChange,onProtocol}){
  const [generation,setGeneration]=useState(0),[preview,setPreview]=useState({data:null,loading:true,error:null});
  const [expanded,setExpanded]=useState(null),[busy,setBusy]=useState(null),[error,setError]=useState(''),[message,setMessage]=useState(''),[invalidated,setInvalidated]=useState(false),[limit,setLimit]=useState(30);
  useEffect(()=>{
    const controller=new AbortController();setPreview({data:null,loading:true,error:null});setInvalidated(false);
    api(`/data-stores/${source.source_sha256}/propagation-preview`,{method:'POST',body:{},signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setPreview({data,loading:false,error:null});})
      .catch(error=>{if(!controller.signal.aborted)setPreview({data:null,loading:false,error:error.message});});
    return()=>controller.abort();
  },[source.source_sha256,source.state?.version,generation]);
  async function propagate(protocol){
    if(busy||invalidated||!protocol.expected_preview_revision)return;
    setBusy(protocol.protocol_uuid);setError('');setMessage('');
    try{
      const result=await api(`/data-stores/${source.source_sha256}/propagate`,{method:'POST',body:{protocol_uuid:protocol.protocol_uuid,expected_preview_revision:protocol.expected_preview_revision}});
      if(result.protocol_uuid!==protocol.protocol_uuid||!result.event_uuid)throw new Error('The server did not confirm a recorded protocol update. Refresh before retrying.');
      setMessage(`${humanize(protocol.name)} working dataset updated.`);onChange?.();setGeneration(value=>value+1);
    }catch(error){setError(error.message);setInvalidated(true);}finally{setBusy(null);}
  }
  const rows=preview.data?.protocols || [];
  const excluded=preview.data?.source_scope?.registrations?.find(item=>item.source_sha256===source.source_sha256)?.query_excluded ?? source.state?.query_excluded;
  return <section className="source-propagation"><div className="sp-heading"><button disabled={!!busy} onClick={onBack}><ArrowLeft size={14}/> Back to data store</button><button disabled={!!busy||preview.loading} onClick={()=>{setError('');setGeneration(value=>value+1);}}><RefreshCw size={14}/> Refresh proposal</button></div>
    <div className="sp-title"><Database size={21}/><div><h2>Propagate source changes</h2><p>{source.filename}</p></div><span className={excluded===true?'sp-excluded':excluded===false?'sp-included':'sp-unknown'}>{excluded===true?'Excluded from new queries':excluded===false?'Eligible for new queries':'Query participation not reported'}</span></div>
    <p className="sp-intro">Each proposal reruns the complete saved query across all query-eligible sources, including other new data. Apply protocols individually; earlier saved exports stay unchanged.</p>
    {message&&<div className="sp-result" role="status"><Check size={15}/>{message}</div>}{error&&<div className="sp-error" role="alert">{error}<span>Refresh the proposal before retrying this protocol.</span></div>}
    <Status {...preview} retry={()=>setGeneration(value=>value+1)}>{rows.length?<div className="sp-protocol-list">{rows.slice(0,limit).map(protocol=>{
      const diff=protocol.diff_summary;
      const comparison={diff_summary:diff,diff:protocol.diff,previous_count:diff?.current?.epochs,next_count:diff?.proposed?.epochs};
      const added=protocol.diff?.added?.length || 0,removed=protocol.diff?.removed?.length || 0,changed=protocol.diff?.changed?.length || 0;
      const hasDiff=!!diff&&['added','removed','changed'].every(key=>Array.isArray(protocol.diff?.[key]));
      const noChanges=hasDiff&&added+removed+changed===0;
      const canApply=typeof protocol.expected_preview_revision==='string'&&protocol.expected_preview_revision.length>0&&protocol.can_apply===true&&hasDiff&&!protocol.error;
      return <article className="sp-protocol" key={protocol.protocol_uuid}><div className="sp-protocol-heading"><div><h3>{humanize(protocol.name)}</h3><p>{protocol.binding_version>0?`Current working dataset · version ${protocol.binding_version}`:'Saved source query'} · {!hasDiff?'Comparison unavailable':noChanges?'No membership or metadata changes':`${number(added)} added · ${number(removed)} removed · ${number(changed)} changed`}</p></div><div className="sp-row-actions"><button disabled={!diff} aria-expanded={expanded===protocol.protocol_uuid} onClick={()=>setExpanded(value=>value===protocol.protocol_uuid?null:protocol.protocol_uuid)}>{expanded===protocol.protocol_uuid?<ChevronUp size={13}/>:<ChevronDown size={13}/>} Details</button><button className="primary" disabled={!!busy||preview.loading||invalidated||!canApply} onClick={()=>propagate(protocol)}>{busy===protocol.protocol_uuid?'Applying…':noChanges?'Up to date':'Apply update'}<ArrowRight size={13}/></button></div></div>
        {protocol.error?<p className="sp-error">{protocol.error}</p>:diff?<CompactProtocolDiff comparison={comparison}/>:<p className="sp-unavailable">Comparison counts were not supplied for this protocol.</p>}
        {expanded===protocol.protocol_uuid&&<div className="sp-expanded"><ProtocolDiff comparison={comparison}/>{protocol.view_adaptation&&<p className="sp-intro">Tree layout: {protocol.view_adaptation.applied_group_by.join(" → ")}. The original grouping ({protocol.view_adaptation.original_group_by.join(", ")}) stays recorded with this revision.</p>}{onProtocol&&<button disabled={!!busy} onClick={()=>onProtocol(protocol.protocol_uuid)}>Open current protocol workspace <ArrowRight size={13}/></button>}</div>}
      </article>;
    })}{rows.length>limit&&<button className="sp-more" onClick={()=>setLimit(value=>value+30)}>Show more protocols</button>}</div>:<Empty title="No protocol updates to compare">No protocol workspace was returned for this source.</Empty>}</Status>
  </section>;
}
