import {useEffect,useRef,useState} from 'react';
import {FolderOpen,LoaderCircle} from 'lucide-react';
import {browseFolder} from '../folderBrowser.js';
import './FolderPathInput.css';

export default function FolderPathInput({value,onChange,disabled=false,purpose='existing',title='Choose a folder',suggestedName,onBusyChange,...inputProps}){
  const [choosing,setChoosing]=useState(false),[error,setError]=useState('');
  const mounted=useRef(false),browseButton=useRef(null),restoreFocus=useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(!choosing&&!disabled&&restoreFocus.current){restoreFocus.current=false;browseButton.current?.focus({preventScroll:true});}},[choosing,disabled]);
  async function browse(){
    if(disabled||choosing)return;
    setChoosing(true);setError('');onBusyChange?.(true);
    try{
      const directory=await browseFolder({directory:value,purpose,title,suggestedName});
      if(mounted.current&&directory!==null)onChange(directory);
    }catch(error){if(mounted.current)setError(error.message||'The folder chooser could not open.');}
    finally{if(mounted.current){restoreFocus.current=true;setChoosing(false);onBusyChange?.(false);}}
  }
  return <div className="folder-path-field"><div className="folder-path-control"><input {...inputProps} readOnly value={value} title={value||'Choose a folder with Browse'} placeholder="Choose a folder with Browse…" disabled={disabled||choosing}/><button ref={browseButton} type="button" disabled={disabled||choosing} aria-label={`Browse: ${title}`} onClick={browse}>{choosing?<LoaderCircle size={15} className="spin"/>:<FolderOpen size={15}/>}Browse…</button></div>{error&&<span className="folder-path-error" role="alert">{error}</span>}</div>;
}
