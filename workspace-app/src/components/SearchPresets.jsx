import QueryPresetHistory from './QueryPresetHistory.jsx';
import {useRef,useState} from 'react';
import {ArrowRight,Clock3,Search,Filter,Pin,PinOff,Pencil,RefreshCw,Sparkles,Download,Upload,Database,Users,Activity} from 'lucide-react';
import {number,time} from '../api.js';
import {predicateSummary,suggestedSearches,presetKey,searchRunSummary} from '../searchPresets.js';
import {parsePresetRecipe,sortedProjectPresets} from '../projectSearchPresets.js';
import './SearchPresets.css';
export default function SearchPresets({entries,fields,history,onRun,onEdit,onPin,onProjectPin,onImportRecipe,onProjectPage,projectPresets,busy,error}){
 const [search,setSearch]=useState(''),[fileError,setFileError]=useState('');const fileInput=useRef(null);
 async function importFile(event){const file=event.target.files?.[0];event.target.value='';if(!file)return;setFileError('');try{if(file.size>1024*1024)throw new Error('Query recipe files are limited to 1 MiB.');const recipe=parsePresetRecipe(await file.text());await onImportRecipe(recipe);}catch(error){setFileError(error.message);}}

 const matches=item=>`${item.name||''} ${item.description||''} ${item.predicate?predicateSummary(item.predicate):''}`.toLowerCase().includes(search.toLowerCase());
 const projectKeys=new Set((projectPresets?.data?.presets||[]).map(item=>presetKey(item.predicate)));
 const deviceEntries=entries.filter(item=>!projectKeys.has(presetKey(item.predicate)));
 const pinned=deviceEntries.filter(item=>item.pinned&&matches(item)),recent=deviceEntries.filter(item=>!item.pinned&&matches(item));
 const suggestions=suggestedSearches(fields).filter(item=>!projectKeys.has(item.id)).filter(item=>!entries.some(saved=>saved.id===item.id)).filter(matches);
 const saved=sortedProjectPresets(projectPresets?.data?.presets||[]).filter(matches);
 function row(item){const name=item.name&&item.name!=='Metadata selection'?item.name:item.predicate?predicateSummary(item.predicate):'Saved search';const run=searchRunSummary(item);return <div className="search-preset-entry" key={item.preset_uuid||item.id||item.revision_uuid}><div className="search-preset-row">
   <button className="search-preset-run" disabled={busy} onClick={()=>onRun(item)} title="Run against the current project data"><Search size={16}/><span><strong>{name}</strong><small>{item.predicate?predicateSummary(item.predicate):`Saved ${time(item.created_at)}`}</small>{item.description&&<small className="search-preset-description">{item.description}</small>}{item.preset_uuid&&<small>Project query · v{item.version} · {time(item.updated_at)}{item.pinned?' · Pinned':''}</small>}</span><span className="search-preset-stats" role="group" aria-label="Last run summary">
    {run.at||run.epochs!==null?<><span className="preset-run-time" title={run.at||'Run time not recorded'}><small>Last run</small><span>{run.at?time(run.at):'Time not recorded'}</span></span><span><strong><Activity size={13}/>{run.epochs===null?'—':number(run.epochs)}</strong><small>epochs</small></span><span><strong><Users size={13}/>{run.cells===null?'—':number(run.cells)}</strong><small>cells</small></span></>:<small>No run recorded</small>}
   </span><ArrowRight size={16}/></button>
   <button className="icon-button" disabled={busy} onClick={()=>onEdit(item)} aria-label={`Edit ${name}`} title="Edit predicate"><Pencil size={14}/></button>
   <button className="icon-button" disabled={busy||(!!item.preset_uuid&&projectPresets?.loading)} onClick={()=>item.preset_uuid?onProjectPin(item):onPin(item)} aria-label={`${item.pinned?'Unpin':'Pin'} ${name}`} title={item.pinned?'Unpin search':'Pin search'}>{item.pinned?<PinOff size={14}/>:<Pin size={14}/>}</button>
 {item.preset_uuid&&<a className="icon-button" href={`/api/search-presets/${item.preset_uuid}/download?version=${item.version}`} download aria-label={`Download ${name} query JSON`} title="Download reusable query JSON"><Download size={14}/></a>}
 </div>{item.preset_uuid&&<QueryPresetHistory preset={item} onEdit={onEdit} disabled={busy}/>}</div>;}
 return <div className="search-presets"><div className="search-presets-intro"><div><h2>Pick a search. Browse the epochs.</h2><p>Rerun a predicate on current data, including newly imported recordings.</p></div><div className="search-preset-tools"><input ref={fileInput} hidden type="file" accept=".json,application/json" onChange={importFile}/><button disabled={busy} onClick={()=>fileInput.current?.click()}><Upload size={14}/> Import query</button><input aria-label="Find a search preset" placeholder="Find a saved search…" value={search} onChange={event=>setSearch(event.target.value)}/></div></div>
 {(error||fileError)&&<p className="error" role="alert">{fileError||error}</p>}{busy&&<p className="search-presets-progress" role="status"><RefreshCw size={14} className="spin"/> Preparing search…</p>}
 <section><h3><Database size={15}/> Project saved searches <small>{saved.length}</small><button className="icon-button" disabled={projectPresets?.loading} onClick={projectPresets?.reload} aria-label="Refresh project saved searches"><RefreshCw size={13}/></button></h3>
 {projectPresets?.error?<p className="search-presets-load-error" role="alert">Project searches could not load: {projectPresets.error} <button onClick={projectPresets.reload}>Retry</button></p>:projectPresets?.loading&&!projectPresets.data?<p role="status">Loading project searches…</p>:saved.length?saved.map(row):<p className="search-presets-empty">{search?'No project searches match this text.':'Run a search, then choose Save query preset to name it and share it with this project.'}</p>}
 {projectPresets?.data?.total>50&&<div className="search-project-pages"><button disabled={busy||projectPresets.loading||!projectPresets.data.offset} onClick={()=>onProjectPage(Math.max(0,projectPresets.data.offset-50))}>Previous searches</button><span>{projectPresets.data.offset+1}–{projectPresets.data.offset+projectPresets.data.presets.length} of {number(projectPresets.data.total)}</span><button disabled={busy||projectPresets.loading||!projectPresets.data.has_more} onClick={()=>onProjectPage(projectPresets.data.offset+50)}>Next searches</button></div>}
 {search&&projectPresets?.data?.total>50&&<p className="search-presets-note">Text filters the currently loaded project page and recent shortcuts.</p>}
 </section>
 {pinned.length>0&&<section><h3><Pin size={15}/> Pinned search shortcuts <small>{pinned.length}</small></h3>{pinned.length?pinned.map(item=>row(item)):<p className="search-presets-empty">Pin a search below to keep it here.</p>}</section>}
 {suggestions.length>0&&<section><h3><Sparkles size={15}/> Suggested predicates</h3>{suggestions.map(item=>row(item))}</section>}
 <section><h3><Clock3 size={15}/> Recent project searches</h3>{recent.length?recent.map(item=>row(item)):<p className="search-presets-empty">Your recent searches will appear here.</p>}</section>
 <details className="search-presets-history"><summary>Saved query revisions <span>{history.data?.total??history.data?.revisions?.length??0}</span></summary>{history.loading?<p>Loading saved queries…</p>:history.error?<p role="alert">{history.error}</p>:(history.data?.revisions||[]).map(item=>row(item))}</details>
 <p className="search-presets-note">Saved searches, pinned shortcuts and recent searches travel with this project. Rerunning uses current data. Counts marked “last run” are historical. Saved selection revisions preserve exact past membership. Imported query JSON is opened for review before saving.</p>
 </div>;
}
