import {useEffect,useRef,useState} from 'react';
import {api} from '../../api.js';
import {workbenchCandidateRoot} from '../workbenchAuthority.js';
import ProtocolDiff from '../../protocol-overview/ui/ProtocolDiff.jsx';

function ReplacementReview({protocolId,item,onHistory,onChange,onSession,session={}}){
  const root=workbenchCandidateRoot(protocolId,item.candidate_revision_uuid);
  const [preview,setPreview]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[confirmed,setConfirmed]=useState(false),[nonce,setNonce]=useState(0),[receipt,setReceipt]=useState(session.replacementReceipt||null);
  const pending=useRef(session.replacementPending?.root===root?session.replacementPending.body:null);
  const accepted=!!receipt||item.status==='accepted'&&!pending.current;
  const mounted=useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    if(accepted||pending.current)return;
    const cancel=new AbortController();setPreview(null);setConfirmed(false);setError('');
    api(`${root}/replacement-preview`,{signal:cancel.signal}).then(value=>{
      if(cancel.signal.aborted)return;
      if(value.contract_version!==1||value.review_kind!=='replacement'||value.candidate_revision_uuid!==item.candidate_revision_uuid||typeof value.expected_candidate_scope_revision!=='string'||!Number.isSafeInteger(value.expected_binding_version)||typeof value.expected_query_revision!=='string'||typeof value.preview_sha256!=='string'||!Number.isSafeInteger(value.diff_counts?.removed)||value.diff_counts.removed<0)throw new Error('The frozen change preview is incomplete. Refresh before reviewing.');
      setPreview(value);
    }).catch(error=>{if(!cancel.signal.aborted)setError(error.message);});
    return()=>cancel.abort();
  },[root,nonce]);
  async function accept(){
    if(busy||accepted||!pending.current&&(!preview?.compatibility?.compatible||preview.diff_counts.removed>0&&!confirmed))return;
    const body=pending.current||{expected_candidate_scope_revision:preview.expected_candidate_scope_revision,expected_binding_version:preview.expected_binding_version,expected_query_revision:preview.expected_query_revision,preview_sha256:preview.preview_sha256,operation_uuid:crypto.randomUUID(),confirm_removals:confirmed};
    pending.current=body;onSession?.({...session,replacementPending:{root,body}});setBusy(true);setError('');
    try{
      const result=await api(`${root}/replacement-accept`,{method:'POST',body});
      if(result.contract_version!==1||result.operation_uuid!==body.operation_uuid||result.candidate_revision_uuid!==item.candidate_revision_uuid||typeof result.event_uuid!=='string')throw new Error('Acceptance receipt is incomplete. Retry to recover the same operation.');
      if(mounted.current){pending.current=null;onSession?.({...session,replacementPending:null,replacementReceipt:result});onChange?.();setReceipt(result);}
    }catch(error){if(mounted.current){if(error.status===409&&!error.saved){pending.current=null;onSession?.({...session,replacementPending:null});setPreview(null);setConfirmed(false);}setError(error.message);}}finally{if(mounted.current)setBusy(false);}
  }
  return <section className="incoming-proposal" aria-label="Frozen protocol change review">
    <header><h2>Review protocol changes</h2><button disabled={busy} onClick={onHistory}>Back to Workbench</button></header>
    <p>This frozen proposal replaces the pinned dataset after approval. Review added, removed and updated cells below. Original recordings and shared tags remain stored.</p>
    {pending.current&&!receipt&&<p role="status">An approval response is unconfirmed. Recover its receipt to learn whether these changes were accepted.</p>}
    {!preview&&!error&&!accepted&&!pending.current&&<p role="status">Loading frozen comparison…</p>}
    {preview&&<ProtocolDiff comparison={preview} showProtocolCount={false}/>}
    {preview?.diff_counts.removed>0&&!accepted&&<label><input type="checkbox" checked={confirmed} disabled={busy||!!pending.current} onChange={event=>setConfirmed(event.target.checked)}/>Approve removing {preview.diff_counts.removed.toLocaleString()} epochs from this pinned dataset.</label>}
    {error&&<p role="alert">{error}</p>}
    {accepted?<p role="status">Protocol changes accepted{receipt?.event_uuid?` · ${receipt.event_uuid}`:""}</p>:<div className="incoming-actions">
      <button disabled={busy||!!pending.current} onClick={()=>setNonce(value=>value+1)}>Refresh comparison</button>
      <button className="primary" disabled={busy||!pending.current&&(!preview?.compatibility?.compatible||preview.diff_counts.removed>0&&!confirmed)} onClick={accept}>{busy?'Saving approval…':pending.current?'Recover approval receipt':'Accept protocol changes'}</button>
    </div>}
  </section>;
}

export default function ReplacementIncomingReview(props){
  return <ReplacementReview key={`${props.protocolId}:${props.item.candidate_revision_uuid}`} {...props}/>;
}
