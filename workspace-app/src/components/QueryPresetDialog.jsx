import {useEffect,useRef,useState} from 'react';
import {Pin,Search,X} from 'lucide-react';
import {api} from '../api.js';
import {searchPresetPayload,validatePresetReceipt,resolvedPresetMatch,presetSaveTarget,samePresetTarget} from '../projectSearchPresets.js';
import {predicateSummary} from '../searchPresets.js';
import './SearchPresets.css';

export default function QueryPresetDialog({predicate,splits,preset=null,defaults={},onClose,onSaved,onRefresh}){
  const dialog=useRef(null),[mode,setMode]=useState(preset?'update':'new');
  const [name,setName]=useState(preset?.name||defaults.name||predicateSummary(predicate).slice(0,160));
  const [description,setDescription]=useState(preset?.description||defaults.description||'');
  const [pinned,setPinned]=useState(preset?.pinned??defaults.pinned??false);
  const [replaceLayout,setReplaceLayout]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [resolution,setResolution]=useState({loading:true,ready:false,match:null}),[check,setCheck]=useState(0);
  useEffect(()=>{const node=dialog.current;node.showModal();return()=>node.close();},[]);
  useEffect(()=>{const controller=new AbortController();setResolution({loading:true,ready:false,match:null});setError('');
    api('/search-presets/resolve',{method:'POST',body:{predicate},signal:controller.signal}).then(result=>{
      if(controller.signal.aborted)return;const match=resolvedPresetMatch(result);setResolution({loading:false,ready:true,match});
      if(match){setName(match.name);setDescription(match.description||'');setPinned(!!match.pinned);}
    }).catch(error=>{if(!controller.signal.aborted){setResolution({loading:false,ready:false,match:null});setError(error.message);}});
    return()=>controller.abort();
  },[predicate,check]);
  const target=resolution.match||(mode==='update'?preset:null),locked=busy||resolution.loading||!resolution.ready;
  async function save(event){
    event.preventDefault();if(locked)return;setBusy(true);setError('');
    try{const match=resolvedPresetMatch(await api('/search-presets/resolve',{method:'POST',body:{predicate}}));
      const existing=presetSaveTarget(match,preset,mode),displayed=presetSaveTarget(resolution.match,preset,mode);
      if(!samePresetTarget(existing,displayed)){setResolution({loading:false,ready:true,match});setError('The saved search changed while this dialog was open. Review the destination shown below, then save again.');return;}
      const body=searchPresetPayload({name,description,pinned,predicate,splits:existing&&!replaceLayout?existing.splits:splits},existing);
      const result=validatePresetReceipt(await api(existing?`/search-presets/${existing.preset_uuid}`:'/search-presets',{method:existing?'PUT':'POST',body}));onSaved(result);
    }catch(error){setError(error.message);}finally{setBusy(false);}
  }
  return <dialog ref={dialog} className="query-preset-dialog" aria-labelledby="query-preset-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}><form onSubmit={save}>
    <header><h2 id="query-preset-title"><Search size={18}/> Save search predicate</h2><button type="button" className="icon-button" disabled={busy} onClick={onClose} aria-label="Close save query"><X size={18}/></button></header>
    <p>The predicate and tree layout are saved in this project. Each run finds current matching epochs; this does not freeze a selection or update a protocol.</p>
    {resolution.loading?<p role="status">Checking existing searches…</p>:resolution.match?<p role="status">Already saved as <strong>{resolution.match.name}</strong> · version {resolution.match.version}. Changes stay in this entry’s version history; no duplicate is created.</p>:preset&&<label>Save destination<select disabled={locked} value={mode} onChange={event=>setMode(event.target.value)}><option value="update">Update “{preset.name}” · version {preset.version}</option><option value="new">Create a new saved search</option></select></label>}
    <label>Search name<input autoFocus required disabled={locked} value={name} maxLength={160} onChange={event=>setName(event.target.value)} placeholder="e.g. History noise · NBQX"/></label>
    <label>Description <small>Optional</small><textarea disabled={locked} value={description} maxLength={2000} rows={3} onChange={event=>setDescription(event.target.value)} placeholder="What this search is for"/></label>
    <label className="query-preset-pin"><input type="checkbox" checked={pinned} disabled={locked} onChange={event=>setPinned(event.target.checked)}/><Pin size={14}/> Pin in project searches</label>
    {target&&target.splits!==splits&&<label className="query-preset-pin"><input type="checkbox" checked={replaceLayout} disabled={locked} onChange={event=>setReplaceLayout(event.target.checked)}/> Update saved tree layout to the current arrangement</label>}
    <details><summary>Query to save</summary><p>{predicateSummary(predicate)}</p><pre>{JSON.stringify({predicate,splits:target&&!replaceLayout?target.splits:splits},null,2)}</pre></details>
    {error&&<div className="query-preset-error" role="alert">{error}<button type="button" disabled={busy||resolution.loading} onClick={()=>{onRefresh?.();setCheck(value=>value+1);}}>Recheck saved searches</button><small>No save is retried automatically.</small></div>}
    <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="primary" disabled={locked||!name.trim()}>{busy?'Saving search…':target?'Save existing search':'Save new search'}</button></footer>
  </form></dialog>;
}
