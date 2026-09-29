import {useState} from 'react';
import {Check, Database, Download, FileJson, GitBranch, History, RefreshCw} from 'lucide-react';
import {api, number, time, useResource} from '../api.js';
import {exportDownloadLabel, exportFormatLabel} from '../exportFormats.js';
import {Empty, Status} from './Common.jsx';
import './ProtocolExports.css';

const destinations = [
  {format:'epictree-mat',title:'EpicTreeGUI',detail:'MATLAB bundle · tree + selection mask',icon:GitBranch},
  {format:'wheeler-sqlite',title:'Wheeler SQL database',detail:'SQLite · queryable epoch metadata + H5 links',icon:Database},
];
export function ExportDestination({value,onChange,disabled}) {
  return <fieldset className="export-destinations" disabled={disabled}>
    <legend>Export to</legend>
    <div className="export-destination-options">{destinations.map(({format,title,detail,icon:Icon})=><label key={format} className={value===format?'selected':''}>
      <input type="radio" name="export-destination" value={format} checked={value===format} onChange={()=>onChange(format)}/>
      <Icon size={22}/><span><strong>{title}</strong><small>{detail}</small></span>{value===format&&<Check size={17} className="destination-check"/>}
    </label>)}</div>
    <details key={value==='reference-json'?'reference':'primary'} open={value==='reference-json'||undefined}><summary>Advanced formats{value==='reference-json'?' · Reference JSON selected':''}</summary><label className="reference-destination"><input type="radio" name="export-destination" checked={value==='reference-json'} onChange={()=>onChange('reference-json')}/><FileJson size={16}/> Reference JSON · query + frozen membership</label></details>
  </fieldset>;
}

export default function ProtocolExports({protocolId,revision,onReuse,disabled}) {
  const history=useResource(`/exports?protocol_uuid=${encodeURIComponent(protocolId)}`,revision);
  const [error,setError]=useState(''),[reusing,setReusing]=useState(null),[limit,setLimit]=useState(10);
  const exports=(history.data?.exports||[]).filter(item=>item.protocol_uuid===protocolId);
  async function reuse(item) {
    setReusing(item.dataset_uuid);setError('');
    try {
      const recipe=await api(`/exports/${item.dataset_uuid}/reuse`);
      if(recipe.protocol_uuid!==protocolId)throw new Error('This export belongs to another protocol. Its settings were not applied.');
      onReuse(protocolId,recipe);
    }catch(e){setError(e.message);}finally{setReusing(null);}
  }
  return <section className="section protocol-export-history">
    <div className="section-heading"><h2><History size={17}/> Exports from this protocol <span className="muted">{exports.length}</span></h2><button className="quiet" onClick={history.reload} disabled={history.loading} aria-label="Refresh protocol exports"><RefreshCw size={15}/></button></div>
    {error&&<div className="error" role="alert">{error}</div>}
    <Status {...history} retry={history.reload}>{exports.length?<div>{exports.slice(0,limit).map(item=><div className="saved-export" key={item.dataset_uuid}>
      {item.format==='wheeler-sqlite'?<Database size={20}/>:item.format==='epictree-mat'?<GitBranch size={20}/>:<FileJson size={20}/>}
      <div><strong>{item.name}</strong><p>{exportFormatLabel(item.format)} · {number(item.epoch_count)} epochs · {time(item.created_at)}</p><details><summary>Export record & provenance</summary><pre>{JSON.stringify(item,null,2)}</pre></details></div>
      <button disabled={disabled||reusing!==null} onClick={()=>reuse(item)}><RefreshCw size={14} className={reusing===item.dataset_uuid?'spin':''}/> Reuse settings</button>
      {item.download_url&&<a className="button" href={item.download_url} download><Download size={14}/> {exportDownloadLabel(item.format)}</a>}
    </div>)}{exports.length>limit&&<button className="quiet" onClick={()=>setLimit(count=>count+10)}>Show more exports</button>}</div>:<Empty title="No exports from this protocol yet">Choose a destination above. Each export saves its query, selection and exact epoch identities.</Empty>}</Status>
  </section>;
}
