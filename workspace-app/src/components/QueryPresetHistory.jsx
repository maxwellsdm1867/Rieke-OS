import {useState} from 'react';
import {Clock3,ChevronDown} from 'lucide-react';
import {useResource,time} from '../api.js';
import {predicateSummary,presetKey} from '../searchPresets.js';
export default function QueryPresetHistory({preset,onEdit,disabled}){
 const [open,setOpen]=useState(false),[offset,setOffset]=useState(0);
 const history=useResource(open?`/search-presets/${preset.preset_uuid}/versions?limit=10&offset=${offset}`:null,preset.version);
 return <div className="preset-version-history"><button className="preset-history-toggle" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><Clock3 size={12}/> Version history · v{preset.version}<ChevronDown size={12}/></button>{open&&<div className="preset-history-content">
 {history.loading?<p role="status">Loading versions…</p>:history.error?<p role="alert">{history.error}<button onClick={history.reload}>Retry</button></p>:<>{(history.data?.versions||[]).map(version=><div className="preset-history-version" key={version.preset_version}><strong>v{version.preset_version}</strong><span>{predicateSummary(version.predicate)}<small>{time(version.updated_at)} · {version.actor}</small></span><button disabled={disabled} onClick={()=>onEdit({...preset,...version,version:preset.version,last_run:presetKey(version.predicate)===presetKey(preset.predicate)?preset.last_run:null})}>Load into editor</button></div>)}<p>Loading a version opens its conditions for review. Saving an edit creates a new version.</p>{(offset>0||history.data?.has_more)&&<div><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-10))}>Newer</button><button disabled={!history.data?.has_more} onClick={()=>setOffset(offset+10)}>Older</button></div>}</>}
 </div>}</div>;
}
