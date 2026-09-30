import {useState} from 'react';
import {FolderOpen} from 'lucide-react';
import {api} from '../api.js';
import './H5Inbox.css';

export default function H5Inbox(){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function open(){setBusy(true);setError('');try{await api('/import-inbox/open-folder',{method:'POST',body:{}});}catch(error){setError(error.message);}finally{setBusy(false);}}
  return <span className="h5-folder-action"><button disabled={busy} onClick={open} title="Open the project's H5 folder. Files dropped here import automatically while the project is open."><FolderOpen size={16}/> {busy?'Opening…':'Open H5 folder'}</button>{error&&<span role="alert">{error}</span>}</span>;
}
