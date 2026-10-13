import {useAuthoredDraft} from '../../presentation/useAuthoredDraft.js';
import {useEffect,useState} from 'react';
import {Pin} from 'lucide-react';
import {api,useResource,number} from "../../api.js";

export default function NewPinnedProtocol({candidate,defaultName,disabled,onBusyChange,onCreated}){
  const options=useResource(candidate?.revision_uuid?`/explore/revisions/${candidate.revision_uuid}/protocol-options`:null);
  const [name,setName,nameDraft]=useAuthoredDraft(candidate?.revision_uuid?['new-pinned-protocol',candidate.revision_uuid,'name']:null,defaultName||'');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[reviewed,setReviewed]=useState(false);
  useEffect(()=>setReviewed(false),[candidate?.revision_uuid]);
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  const protocols=options.data?.protocols||[],single=protocols.length===1,canCreate=protocols.length>0&&(single||reviewed);
  async function create(event){
    event.preventDefault();if(disabled||busy||!canCreate||!name.trim()||options.loading||options.error)return;
    setBusy(true);setError('');
    try{const result=await api(`/explore/revisions/${candidate.revision_uuid}/create-protocol`,{method:'POST',body:{name:name.trim(),protocol_ids:protocols.map(row=>row.protocol_id),expected_recipe_sha256:options.data.expected_recipe_sha256}});
      if(!result.protocol_uuid)throw new Error('Protocol creation did not return an identity. Reload before retrying.');
      nameDraft.clear();onCreated?.(result.protocol_uuid);
    }catch(error){setError(error.message);}finally{setBusy(false);}
  }
  return <form className="new-pinned-protocol" onSubmit={create}>
    <h3>Create a pinned protocol</h3>
    <p>Your current selection becomes its first working dataset. Existing pinned protocols stay unchanged.</p>
    {options.loading?<p role="status">Checking recorded Protocol IDs…</p>:options.error?<p role="alert">{options.error}<button type="button" onClick={options.reload}>Retry</button></p>:<>
      <div className="protocol-identity-summary"><strong>Recorded Protocol ID</strong>{protocols.map(row=><div key={row.protocol_id}><code>{row.protocol_id}</code><span>{number(row.epoch_count)} epochs</span></div>)}</div>
      {protocols.length?<p>{number(options.data.cell_count)} cells · {number(options.data.epoch_count)} epochs · {protocols.length} recorded Protocol IDs</p>:<p role="alert">No matching epochs. Change the search before creating a pinned protocol.</p>}
      {protocols.length>1&&<label><input type="checkbox" checked={reviewed} disabled={busy} onChange={event=>setReviewed(event.target.checked)}/>Keep all {protocols.length} recorded protocols together in this pinned dataset. Each epoch retains its original Protocol ID.</label>}
      <label>Protocol name<input value={name} onChange={event=>setName(event.target.value)} maxLength={120} disabled={busy} placeholder="Name this pinned protocol"/></label>
      <button type="submit" className="primary" disabled={disabled||busy||!canCreate||!name.trim()}><Pin size={15}/>{busy?'Creating…':'Create pinned protocol'}</button>
    </>}
    {error&&<p role="alert">{error}</p>}
  </form>;
}
