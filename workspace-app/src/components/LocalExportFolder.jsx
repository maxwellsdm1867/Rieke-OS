import {useState} from 'react';
import {FolderOpen,Copy} from 'lucide-react';
import {api} from '../api.js';

export default function LocalExportFolder({path}){
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(!path)return null;
  async function copy(){try{await navigator.clipboard.writeText(path);setMessage('Folder path copied.');}catch{setMessage('Select and copy the folder path below.');}}
  async function open(){
    if(busy)return;
    setBusy(true);setError('');
    try{await api('/exports/open-folder',{method:'POST',body:{}});}
    catch(error){setError(error.message||'The export folder could not open.');}
    finally{setBusy(false);}
  }
  return <section className="section local-export-folder"><h2><FolderOpen size={18}/> Local export folder</h2>
    <p>Point Wheeler, MATLAB, or another service here once. All this project’s exports stay together.</p>
    <div><code>{path}</code><button type="button" disabled={busy} onClick={open}><FolderOpen size={14}/>{busy?'Opening…':'Open exports folder'}</button><button type="button" onClick={copy}><Copy size={14}/> Copy folder path</button></div>
    <small>Tags return through each export’s annotations folder. Refresh metadata checks updated selection masks here.</small>
    {error&&<p role="alert">{error}</p>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
