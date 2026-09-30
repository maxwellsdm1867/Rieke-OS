import {useEffect,useId,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ArrowLeft,ArrowRight,ChevronRight,Folder,FolderOpen,FolderPlus,Home,LoaderCircle,MapPin,Pencil,X} from 'lucide-react';
import {api} from '../api.js';
import {absoluteFolderPath,folderParentPath,newFolderPath,readFolderListing,shouldCreateNewFolder} from '../folderBrowser.js';
import './FolderBrowserDialog.css';

export function openFolderBrowserDialog(options){
  if(!globalThis.document?.body)throw new Error('The folder browser is unavailable. Reopen the app and try again.');
  return new Promise(resolve=>{
    const host=document.createElement('div');host.className='folder-browser-host';document.body.appendChild(host);
    const root=createRoot(host);let finished=false;
    const finish=value=>{if(finished)return;finished=true;resolve(value);queueMicrotask(()=>{root.unmount();host.remove();});};
    root.render(<FolderBrowserDialog {...options} onChoose={finish}/>);
  });
}

export default function FolderBrowserDialog({purpose='existing',title='Choose a folder',initialDirectory='',initialName='New project',request=api,onChoose}){
  const dialog=useRef(null),nameInput=useRef(null),chooseButton=useRef(null),titleId=useId(),nameId=useId();
  const [directory,setDirectory]=useState(initialDirectory),[offset,setOffset]=useState(0),[data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [name,setName]=useState(initialName),[editingPath,setEditingPath]=useState(false),[pathDraft,setPathDraft]=useState(initialDirectory),[retry,setRetry]=useState(0);
  const [createNew,setCreateNew]=useState(true);
  const usesNew=purpose==='new'||purpose==='create'&&createNew;
  useEffect(()=>{const element=dialog.current;element.showModal();if(purpose!=='existing')nameInput.current?.focus();return()=>element.close();},[purpose]);
  useEffect(()=>{
    if(purpose==='create'&&!usesNew&&!loading&&!dialog.current.contains(document.activeElement))chooseButton.current?.focus();
  },[purpose,usesNew,loading]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');
    readFolderListing({directory,offset,request:(path)=>request(path,{signal:controller.signal})}).then(listing=>{
      if(controller.signal.aborted)return;setData(listing);setLoading(false);if(purpose==='create')setCreateNew(shouldCreateNewFolder(listing));
    }).catch(failure=>{if(!controller.signal.aborted){setData(null);setLoading(false);setError(`Cannot browse this folder: ${failure.message}`);}});
    return()=>controller.abort();
  },[directory,offset,retry,request,purpose]);
  const location=data?.directory||directory;
  const parent=data?.parent??(location?folderParentPath(location):null);
  let proposed=null,nameError='';
  if(usesNew&&location){
    try{proposed=newFolderPath(location,name);if(data?.folders.some(folder=>folder.name===name.trim()))nameError='A folder with this name already exists.';}
    catch(failure){nameError=failure.message;}
  }
  function navigate(path){setDirectory(path);setOffset(0);setEditingPath(false);setRetry(value=>value+1);}
  function enterPath(event){event.preventDefault();try{navigate(absoluteFolderPath(pathDraft.trim()));}catch(failure){setError(failure.message);}}
  function choose(){if(loading||!data||nameError||usesNew&&!proposed||purpose==='create'&&!usesNew&&!data.empty)return;onChoose(usesNew?{directory:data.directory,name:name.trim()}:data.directory);}
  function trapFocus(event){
    if(event.key!=='Tab')return;
    const controls=[...dialog.current.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])')].filter(element=>!element.hidden&&element.getClientRects().length);
    if(!controls.length)return;
    event.preventDefault();
    const index=controls.indexOf(document.activeElement),step=event.shiftKey?-1:1;
    controls[index<0?(event.shiftKey?controls.length-1:0):(index+step+controls.length)%controls.length].focus();
  }
  const locations=data?.locations||[];
  return <dialog ref={dialog} className="folder-browser-dialog" aria-labelledby={titleId} onKeyDown={trapFocus} onCancel={event=>{event.preventDefault();onChoose(null);}}>
    <header><span className="folder-browser-mark">{purpose!=='existing'?<FolderPlus size={22}/>:<FolderOpen size={22}/>}</span><div><small>{purpose==='new'?'NEW FOLDER':purpose==='create'?'PROJECT FOLDER':'FOLDER BROWSER'}</small><h2 id={titleId}>{title}</h2></div><button className="icon-button" aria-label="Cancel folder selection" onClick={()=>onChoose(null)}><X size={18}/></button></header>
    <div className="folder-browser-location"><button className="icon-button" disabled={!parent||loading} aria-label="Go to parent folder" title="Parent folder" onClick={()=>navigate(parent)}><ArrowLeft size={17}/></button><code title={location||'Home'}>{location||'Home'}</code><button className="icon-button" aria-label="Enter a folder path" title="Enter a folder path" onClick={()=>{setPathDraft(location);setEditingPath(value=>!value);}}><Pencil size={14}/></button></div>
    {editingPath&&<form className="folder-browser-path-form" onSubmit={enterPath}><input autoFocus aria-label="Folder path" value={pathDraft} onChange={event=>setPathDraft(event.target.value)} placeholder="/absolute/folder/path"/><button type="submit"><ArrowRight size={15}/> Go</button></form>}
    <div className="folder-browser-body"><nav aria-label="Folder locations"><button disabled={loading} onClick={()=>navigate('')}><Home size={16}/> Home</button>{locations.filter(place=>place.name!=='Home').map(place=><button key={place.path} disabled={loading} onClick={()=>navigate(place.path)}><MapPin size={16}/><span>{place.name}</span></button>)}</nav><section className="folder-browser-folders" aria-label="Folders in the current location" aria-busy={loading}>
      {loading?<div className="folder-browser-status" role="status"><LoaderCircle size={22} className="spin"/><span>Loading folders…</span></div>:error?<div className="folder-browser-status" role="alert"><FolderOpen size={22}/><span>{error}</span><button onClick={()=>setRetry(value=>value+1)}>Retry</button></div>:<>{data?.folders.map(folder=><button className="folder-browser-folder" key={folder.path} title={folder.path} aria-label={`Open folder ${folder.name}`} onClick={()=>navigate(folder.path)}><Folder size={19}/><span>{folder.name}</span><ChevronRight size={15}/></button>)}{data&&!data.folders.length&&<div className="folder-browser-status"><FolderOpen size={25}/><span>{data.empty?'Empty folder':'No subfolders'}</span><small>{usesNew?'Name a new folder below.':'You can choose this folder.'}</small></div>}</>}
    </section></div>
    {data&&(data.has_more||data.offset>0)&&<div className="folder-browser-pages"><button disabled={loading||!data.offset} onClick={()=>setOffset(Math.max(0,data.offset-200))}><ArrowLeft size={14}/> Previous</button><span>{data.offset+1}–{data.offset+data.folders.length} of {data.total}</span><button disabled={loading||!data.has_more} onClick={()=>setOffset(data.next_offset)}>Next <ArrowRight size={14}/></button></div>}
    {data?.truncated&&<div className="folder-browser-limit" role="status">Some folders are not listed. Use “Enter a folder path” to reach them.</div>}
    {purpose==='create'&&data&&<label className="folder-browser-create-option"><input type="checkbox" checked={createNew} disabled={loading||!data.empty} onChange={event=>setCreateNew(event.target.checked)}/><FolderPlus size={15}/> Create a new folder inside this location</label>}
    {usesNew&&<div className="folder-browser-new"><label htmlFor={nameId}><FolderPlus size={16}/> New folder name</label><input id={nameId} ref={nameInput} value={name} maxLength={255} onChange={event=>setName(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();choose();}}}/>{nameError?<small className="folder-browser-name-error" role="status">{nameError}</small>:proposed&&<code title={proposed}>{proposed}</code>}</div>}
    <footer><button onClick={()=>onChoose(null)}>Cancel</button><button ref={chooseButton} className="primary" disabled={loading||!data||!!nameError||usesNew&&!proposed||purpose==='create'&&!usesNew&&!data.empty} onClick={choose}>{usesNew?<FolderPlus size={16}/>:<FolderOpen size={16}/>} {usesNew?'Use new folder':purpose==='create'?'Use this empty folder':'Choose folder'}</button></footer>
  </dialog>;
}
