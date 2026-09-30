import {useState} from 'react';
import {Check,Copy,FolderCheck,Package,X} from 'lucide-react';
import './ProjectClosedNotice.css';

export default function ProjectClosedNotice({onPrepare}){
  const [path,setPath]=useState(()=>new URLSearchParams(window.location.search).get('closed_project'));
  const [copied,setCopied]=useState(false),[error,setError]=useState('');
  if(!path)return null;
  const name=path.replace(/\/+$/,'').split('/').pop()||path;
  async function copy(){try{await navigator.clipboard.writeText(path);setCopied(true);setError('');}catch{setError('Copy the path here:');}}
  function dismiss(){setPath(null);const url=new URL(window.location.href);url.searchParams.delete('closed_project');window.history.replaceState(window.history.state,'',url);}
  return <section className="project-closed-notice compact" role="status"><span className="project-closed-icon"><FolderCheck size={22} aria-hidden="true"/></span><div className="project-closed-identity"><small><Check size={11} aria-hidden="true"/> Closed</small><strong title={path} aria-label={`Closed project folder: ${path}`}>{name}</strong></div>{onPrepare&&<button className="primary" onClick={()=>onPrepare(path)}><Package size={15} aria-hidden="true"/> Prepare portable copy</button>}<button className="icon-button" onClick={copy} aria-label={copied?'Folder path copied':'Copy folder path'} title={copied?'Folder path copied':'Copy folder path'}>{copied?<Check size={16}/>:<Copy size={16}/>}</button><button className="icon-button" onClick={dismiss} aria-label="Dismiss closed project notice" title="Dismiss"><X size={16}/></button>{error&&<div className="project-closed-copy-error" role="alert"><span>{error}</span><input readOnly value={path} aria-label="Project folder path to copy" onFocus={event=>event.target.select()}/></div>}</section>;
}
