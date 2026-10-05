import {useState} from 'react';
import {Download,Upload} from 'lucide-react';
import TagExchangeDialog from './TagExchangeDialog.jsx';
export default function TagExchangeControls({epoch,onChanged,disabled=false}){
 const [mode,setMode]=useState(null);
 return <><div className="tag-exchange-controls"><button disabled={disabled} onClick={()=>setMode('import')}><Upload size={12}/> Import tags</button><button disabled={disabled} onClick={()=>setMode('export')}><Download size={12}/> Export tags</button></div>{mode&&<TagExchangeDialog mode={mode} epoch={epoch} onClose={()=>setMode(null)} onChanged={onChanged}/>}</>;
}
