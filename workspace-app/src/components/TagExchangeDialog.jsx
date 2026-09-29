import {useEffect,useRef,useState} from 'react';
import {Check,Download,FileJson,Upload,X} from 'lucide-react';
import {api,number} from '../api.js';
import {useAnnotationProfile} from '../annotationProfile.js';
import {readTagDocument,tagExportUrl,tagPreviewSummary} from '../tagExchange.js';
import './TagExchange.css';
export default function TagExchangeDialog({mode,epoch,onClose,onChanged}){
 const dialog=useRef(null),fileInput=useRef(null),request=useRef(null),generation=useRef(0);
 const profile=useAnnotationProfile();
 const [document,setDocument]=useState(null),[filename,setFilename]=useState(''),[preview,setPreview]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState(null);
 const [scope,setScope]=useState('project'),[format,setFormat]=useState('rieke');
 useEffect(()=>{const node=dialog.current;node.showModal();return()=>{node.close();generation.current++;request.current?.abort();};},[]);
 async function choose(file){
   if(!file)return;const current=++generation.current;request.current?.abort();const controller=new AbortController();request.current=controller;
   setFilename(file.name);setPreview(null);setDocument(null);setResult(null);setError('');setBusy(true);
   try{const value=await readTagDocument(file);if(current!==generation.current)return;setDocument(value);const receipt=await api('/annotations/import/preview',{method:'POST',body:{document:value},signal:controller.signal});if(current===generation.current)setPreview(receipt);}
   catch(error){if(current===generation.current&&!controller.signal.aborted)setError(error.message);}
   finally{if(current===generation.current)setBusy(false);}
 }
 async function apply(){
   if(busy||profile.loading||profile.error||!preview?.preview_token||!profile.profileUuid)return;setBusy(true);setError('');
   try{const receipt=await api('/annotations/import/apply',{method:'POST',body:{document,preview_token:preview.preview_token,profile_uuid:profile.profileUuid}});if(receipt?.applied!==true)throw new Error('The server did not confirm the import. Recheck the file before retrying.');setResult(receipt);setPreview(null);profile.reload?.();}
   catch(error){setError(error.message);setPreview(null);}finally{setBusy(false);}
 }
 async function recheck(){if(!document||busy)return;setBusy(true);setError('');try{setPreview(await api('/annotations/import/preview',{method:'POST',body:{document}}));}catch(error){setError(error.message);}finally{setBusy(false);}}
 function close(){if(result)onChanged?.();onClose();}
 const summary=tagPreviewSummary(preview);
 return <dialog ref={dialog} className="tag-exchange-dialog" aria-labelledby="tag-exchange-title" onCancel={event=>{event.preventDefault();if(!busy)close();}}><header><h2 id="tag-exchange-title">{mode==='import'?<Upload size={18}/>:<Download size={18}/>} {mode==='import'?'Import tags':'Export tags'}</h2><button className="icon-button" aria-label="Close tag exchange" disabled={busy} onClick={close}><X size={18}/></button></header><div className="tag-exchange-body">
 {mode==='import'?<>{!profile.profileUuid&&<p className="tag-exchange-note">Choose an author to record this import. <button onClick={profile.openProfile}>Choose profile</button></p>}<p>Import cell and epoch tags from MATLAB or a shared tag file. Cell tags also appear on linked epochs.</p><input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={event=>{const file=event.target.files?.[0];event.target.value='';choose(file);}}/><button className="tag-file-picker" disabled={busy} onClick={()=>fileInput.current?.click()}><FileJson size={22}/><span><strong>{filename||'Choose tag JSON'}</strong><small>Rieke tag exchange or Samarjit UUID tag files · up to 8 MB</small></span><Upload size={16}/></button>
 {busy&&<p role="status">{preview?'Importing tags…':'Checking tag identities and existing tags…'}</p>}
 {preview&&<><div className="tag-import-counts"><div><strong>+{number(summary.added)}</strong><span>New tags</span></div><div><strong>{number(summary.unchanged)}</strong><span>Already saved</span></div><div><strong>{number(summary.targets)}</strong><span>Cells / epochs</span></div></div><p className="tag-exchange-note">Existing tags are preserved. Imported author names stay attached; this import is recorded by {profile.profileName||'your selected profile'}.</p>{summary.rows.length>0&&<div className="tag-preview-list">{summary.rows.slice(0,12).map((row,index)=><div key={index}><span className="tag-preview-scope">{row.target_kind}</span><span className="tag-preview-target"><code>{row.target_uuid}</code><small>{(row.tags||[]).map(tag=>typeof tag==='string'?tag:`${tag.tag} · ${tag.author_name}`).join('; ')||'No direct tags'}</small></span></div>)}{summary.rows.length>12&&<small>And {number(summary.rows.length-12)} more targets</small>}</div>}{preview.warnings?.map((warning,index)=><p className="tag-exchange-note" key={index}>{typeof warning==='string'?warning:warning.message}</p>)}</>}
 {result&&<div className="tag-import-success" role="status"><Check size={18}/><span>Tags imported. They are now available in epoch browsing and tag predicates.</span></div>}
 <details><summary>MATLAB and selection masks</summary><p>In EpicTreeGUI, use Tags → Tag selected epochs (or cells), then Save tag JSON. You can also use readWorkspaceTags, workspaceTag, and writeWorkspaceTags in MATLAB. Import the saved JSON here and review the additions.</p><p>A .ugm file stores inclusion decisions. Import those under Selection masks; it does not replace or remove tags.</p></details>
 </>:<><p>Save the current annotation snapshot with cell and epoch UUIDs, scope, and author attribution.</p><label>Which tags<select aria-label="Tag export scope" value={scope} onChange={event=>setScope(event.target.value)}><option value="project">All project tags</option>{epoch?.cell_uuid&&<option value="cell">Focused cell’s direct tags</option>}{epoch?.epoch_uuid&&<option value="epoch">Focused epoch’s direct tags</option>}</select></label><label>File format<select aria-label="Tag export format" value={format} onChange={event=>setFormat(event.target.value)}><option value="rieke">Rieke tag JSON · MATLAB round trip</option><option value="samarjit">Samarjit hierarchical tag JSON</option></select></label><p className="tag-exchange-note">Cell and epoch tags keep their original scope. Protocol-specific dataset tags and inclusion masks remain separate.</p></>}
 {(error||mode==='import'&&profile.error)&&<div className="tag-exchange-error" role="alert">{error||profile.error}{document&&!preview&&!result&&<button disabled={busy} onClick={recheck}>Recheck file</button>}</div>}
 </div><footer><button disabled={busy} onClick={close}>{result?'Done':'Cancel'}</button>{mode==='import'?<button className="primary" disabled={busy||profile.loading||!!profile.error||!preview?.preview_token||!profile.profileUuid} onClick={apply}><Upload size={14}/> {busy?'Working…':'Import tags'}</button>:<a className="button primary" href={tagExportUrl({format,scope,epoch})} download><Download size={14}/> Download tags</a>}</footer></dialog>;
}
