import {useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {MessageCircle,Plus,X,Search,ChevronDown,UserRound,CornerDownRight} from 'lucide-react';
import {api,useResource,number} from '../api.js';
import {useAnnotationProfile} from '../annotationProfile.js';
import {annotationTagColor,annotationChange,annotationGroups,canRemoveAnnotation,annotationPredicate,bulkAnnotationChange,navigateAfterTagSave} from '../annotationTags.js';
import './AnnotationTags.css';
import {confirmAnnotationReceipt,fastAnnotationReceipt} from '../annotationReceipts.js';
import {epochResourceCache} from '../resourceCache.js';

export default function AnnotationTags({epoch,revision,disabled=false,onChange,onFilter,focusRequest=0,epochFocusRequest=0,onNavigateEpoch,tools,children,selectedEpochs=[],targetScope=null,refreshWithEpoch=false,reconcileReceipt=false}){
  const {profileUuid,profileName,openProfile,loading:profileLoading,error:profileError}=useAnnotationProfile();
  const [refreshAfter,setRefreshAfter]=useState(null);
  const [tabLocked,setTabLocked]=useState(()=>{try{return localStorage.getItem('workspace.tags.tabNavigation')!=='false';}catch{return true;}});
  const handledEpochFocus=useRef(0),restoreInput=useRef(false);
  function toggleTabLock(checked){setTabLocked(checked);try{localStorage.setItem('workspace.tags.tabNavigation',String(checked));}catch{}input.current?.focus();}
  const [manualScope,setScope]=useState('epoch'),[value,setValue]=useState(''),[query,setQuery]=useState(''),[open,setOpen]=useState(false),[active,setActive]=useState(-1),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const scope=targetScope||manualScope;
  const input=useRef(null),handledFocus=useRef(0),listId=useId(),identity=epoch?.epoch_uuid,currentIdentity=useRef(identity);currentIdentity.current=identity;
  const refreshPending=refreshAfter?.identity===identity&&refreshAfter.annotations===epoch?.annotations;
  const remoteNeeded=!epoch?.annotations||((!refreshWithEpoch||refreshAfter?.force)&&refreshPending);
  const awaitingEpoch=refreshWithEpoch&&!refreshAfter?.force&&refreshPending;
  const scopeIdentity=JSON.stringify([identity,epoch?.cell_uuid,scope,profileUuid,revision,selectedEpochs]);
  const committedScope=useRef(null),generation=useRef(0),mounted=useRef(false),mutation=useRef(null);
  const navigationIdentity=JSON.stringify([identity,epoch?.cell_uuid,scope,profileUuid,selectedEpochs]),committedNavigation=useRef(navigationIdentity);
  useLayoutEffect(()=>{committedNavigation.current=navigationIdentity;},[navigationIdentity]);
  useLayoutEffect(()=>{
    mounted.current=true;committedScope.current=scopeIdentity;generation.current++;
    return()=>{mounted.current=false;committedScope.current=null;generation.current++;mutation.current?.abort();};
  },[scopeIdentity]);
  const annotations=useResource(identity&&remoteNeeded?`/epochs/${identity}/annotations`:null,revision);
  const annotationData=remoteNeeded?(annotations.data||epoch?.annotations):epoch?.annotations;
  const suggestions=useResource(open?`/annotation-tags?q=${encodeURIComponent(query)}&limit=12`:null,revision,120);
  const groups=annotationGroups(annotationData),items=suggestions.data?.tags||[];
  const editingLocked=disabled||busy||awaitingEpoch||(remoteNeeded&&annotations.loading)||!!annotations.error||!annotationData;
  const locked=editingLocked||profileLoading||!profileUuid;
  useEffect(()=>{setValue('');setQuery('');setActive(-1);setMessage('');setError('');setOpen(false);setScope('epoch');setRefreshAfter(null);},[identity]);
  // One request debounce; clear the active choice immediately when the text changes.
  useEffect(()=>{if(focusRequest&&focusRequest!==handledFocus.current&&!editingLocked&&!profileLoading){setScope(selectedEpochs.length?'selected':'epoch');if(!profileUuid){openProfile?.();return;}handledFocus.current=focusRequest;input.current?.focus();setOpen(true);}},[focusRequest,editingLocked,profileLoading,profileUuid,selectedEpochs.length]);
  useEffect(()=>{
    if(editingLocked||profileLoading)return;
    if(epochFocusRequest&&epochFocusRequest!==handledEpochFocus.current){handledEpochFocus.current=epochFocusRequest;setScope('epoch');input.current?.focus();setOpen(true);}
    else if(restoreInput.current){restoreInput.current=false;input.current?.focus();}
  },[epochFocusRequest,editingLocked,profileLoading]);
  useEffect(()=>setActive(-1),[query]);
  useEffect(()=>{if(scope==='selected'&&!selectedEpochs.length)setScope('epoch');},[scope,selectedEpochs.length]);
  async function mutate(tag,targetKind=scope,remove=false){
    if(locked||mutation.current||committedScope.current!==scopeIdentity)return false;
    const controller=new AbortController(),token=generation.current;
    mutation.current=controller;
    const isCurrent=()=>mounted.current&&generation.current===token&&committedScope.current===scopeIdentity;
    restoreInput.current=true;setBusy(true);setError('');setMessage('');
    try{
      let body;
      if(targetKind==='selected'){
        const read=await api('/annotations/read',{method:'POST',signal:controller.signal,body:{target_kind:'epoch',target_uuids:[...new Set(selectedEpochs)]}});
        if(!isCurrent())return false;
        body=bulkAnnotationChange({targetUuids:selectedEpochs,profileUuid,tag,read});
      }else body=annotationChange({epoch,targetKind,profileUuid,annotations:annotationData,tag,remove});
      if(!isCurrent())return false;
      // A submitted durable mutation is never cancelled or automatically retried.
      const result=await api('/annotations',{method:'POST',body});
      let confirmed=null;
      if(reconcileReceipt){
        try{confirmed=confirmAnnotationReceipt(result,body);}catch(error){onChange?.(result);throw error;}
        epochResourceCache.invalidateAnnotations(confirmed);
      }else if(!result||!Object.hasOwn(result,'changed'))throw new Error('The server did not return an annotation receipt. Refresh tags before retrying.');
      if(isCurrent()){
        setValue('');setQuery('');setActive(-1);setOpen(false);
        setMessage(`${remove?'Removed':'Saved'} ${targetKind==='selected'?`${number(body.target_uuids.length)} selected epoch`:targetKind} tag “${tag}”.`);
        setRefreshAfter(fastAnnotationReceipt(confirmed)?null:{identity,annotations:epoch?.annotations});
        // Inspector already refreshes the authoritative epoch with its new view
        // revision. Standalone tag editors retain their explicit annotation read.
        if(!refreshWithEpoch)annotations.reload();
      }
      onChange?.(result,isCurrent()?confirmed:null);return true;
    }catch(error){if(isCurrent())setError(error.message);return false;}
    finally{if(mutation.current===controller)mutation.current=null;if(mounted.current)setBusy(false);}
  }
  async function tagKeys(event){
    if(scope!=='epoch'||event.target!==input.current||!onNavigateEpoch||!tabLocked||event.key!=='Tab'||event.altKey||event.ctrlKey||event.metaKey||event.isComposing||event.nativeEvent?.isComposing)return;
    if(event.target.closest('dialog,[role="dialog"],.annotation-legacy'))return;
    event.preventDefault();event.stopPropagation();
    if(editingLocked||profileLoading)return;
    const direction=event.shiftKey?-1:1,current=identity,navigationAtSave=committedNavigation.current,draft=open&&items[active]?items[active].tag:value;
    setOpen(false);
    // Never discard a draft: save first, and stay here if that save fails.
    if(draft.trim()&&!profileUuid){openProfile?.();return;}
    await navigateAfterTagSave({draft,save:tag=>mutate(tag),isCurrent:()=>currentIdentity.current===current&&committedNavigation.current===navigationAtSave,navigate:direction=>onNavigateEpoch(direction,{afterSave:!!draft.trim()}),direction});
  }
  function choose(tag){setValue(tag);setQuery(tag.trim());setOpen(false);setActive(-1);input.current?.focus();}
  function submitTag(event){
    event.preventDefault();
    if(editingLocked)return;
    if(!profileUuid){setOpen(false);openProfile?.();return;}
    if(!value.trim()){input.current?.focus();setOpen(true);return;}
    mutate(value.trim());
  }
  function chips(rows,kind){return rows.map(chip=><span className={`annotation-chip ${kind} tag-color-${annotationTagColor(chip.tag)}`} key={`${kind}:${chip.profile_uuid}:${chip.tag}`} title={`${kind==='cell'?'Inherited from cell':'Direct epoch annotation'} · ${chip.author_name||'Author not recorded'}`}>
    {kind==='cell'?<CornerDownRight size={11}/>:<MessageCircle size={11}/>}<strong>{chip.tag}</strong><small>{chip.author_name||'Unknown author'}</small>
    {onFilter&&<button type="button" disabled={disabled||busy} title={`Find ${kind}-tagged epochs: ${chip.tag}`} aria-label={`Filter by ${kind} tag ${chip.tag}`} onClick={()=>onFilter(annotationPredicate(kind,chip.tag))}><Search size={11}/></button>}
    {canRemoveAnnotation(chip,profileUuid)&&(kind==='epoch'||scope==='cell')&&<button type="button" disabled={locked} aria-label={`Remove my ${kind} tag ${chip.tag}${kind==='cell'?' from the entire cell':''}`} title={kind==='cell'?'Remove this cell tag from all its epochs':'Remove from this epoch only'} onClick={()=>mutate(chip.tag,kind,true)}><X size={11}/></button>}
  </span>);}
  return <section className="annotation-tags" aria-label="Shared cell and epoch tags" onKeyDown={tagKeys}><header><MessageCircle size={14}/><strong>Tags</strong><button type="button" className="annotation-author" onClick={openProfile} disabled={busy}><UserRound size={12}/>{profileName||'Choose profile'}</button>{tools}</header>
    {onNavigateEpoch&&scope==='epoch'&&<label className="tag-tab-lock"><input type="checkbox" checked={tabLocked} onChange={event=>toggleTabLock(event.target.checked)}/> Tab → next epoch <small>Shift+Tab back · drafts save before moving</small></label>}
    {!profileUuid&&!profileLoading&&<p className="annotation-scope-note">Enter a tag below. Choose an author when you save it.</p>}
    {!targetScope&&<div className="annotation-scope" role="group" aria-label="Annotation target"><button disabled={disabled||busy} aria-pressed={scope==='epoch'} onClick={()=>setScope('epoch')}>This epoch</button><button disabled={disabled||busy} aria-pressed={scope==='cell'} onClick={()=>setScope('cell')}>Whole cell</button>{selectedEpochs.length>0&&<button disabled={disabled||busy||selectedEpochs.length>1000} aria-pressed={scope==='selected'} onClick={()=>setScope('selected')}>{number(selectedEpochs.length)} selected</button>}</div>}
    {scope==='selected'&&!targetScope&&<p className="annotation-scope-note">Tags apply to all {number(selectedEpochs.length)} selected epochs.</p>}
    {scope==='cell'&&<p className="annotation-scope-note">Tags apply to {Number.isFinite(annotationData?.cell_epoch_count)?number(annotationData.cell_epoch_count):'all'} epochs in this cell.</p>}
    <div className="annotation-composer" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false);}}><form onSubmit={submitTag}><input ref={input} role="combobox" aria-label={`Tag ${scope==='selected'?`${number(selectedEpochs.length)} selected epochs`:scope==='cell'?'cell':'this epoch'}`} aria-expanded={open} aria-controls={open?listId:undefined} aria-autocomplete="list" aria-activedescendant={open&&items[active]?`${listId}-${active}`:undefined} value={value} maxLength={255} placeholder={scope==='selected'?'Tag selected epochs…':scope==='cell'?'Add a cell tag…':'Add an epoch tag…'} disabled={editingLocked} onFocus={()=>setOpen(true)} onChange={event=>{setValue(event.target.value);setQuery(event.target.value.trim());setActive(-1);setOpen(true);}} onKeyDown={event=>{if(event.key==='Escape')setOpen(false);if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();setOpen(true);setActive(index=>Math.max(0,Math.min(items.length-1,index+(event.key==='ArrowDown'?1:-1))));}if(event.key==='Enter'&&open&&items[active]){event.preventDefault();const tag=items[active].tag;choose(tag);if(profileUuid)mutate(tag);else openProfile?.();}}}/><button type="submit" disabled={editingLocked||profileLoading} className="primary" aria-label={`Add ${scope} tag`} title={!profileUuid?'Choose an author and add this tag':'Save this tag'}><Plus size={14}/><span>{scope==='selected'?`Tag ${number(selectedEpochs.length)} epochs`:'Add tag'}</span></button></form>
    {open&&<div className="annotation-options" id={listId} role="listbox" aria-label="Saved shared tags">{suggestions.loading?<small>Finding tags…</small>:suggestions.error?<small>Suggestions unavailable; typed tags can still be saved.</small>:items.length?items.map((item,index)=><button id={`${listId}-${index}`} key={item.tag} role="option" aria-selected={index===active} disabled={editingLocked} onClick={()=>choose(item.tag)}><strong>{item.tag}</strong><small>{(item.authors||[]).map(author=>author.display_name).join(', ')}</small></button>):<small>Type a tag, then click Add tag or press Enter.</small>}</div>}</div>
    {(profileError||annotations.error||error)&&<p className="annotation-error" role="alert">{error||annotations.error||profileError}<button disabled={busy} onClick={()=>{setRefreshAfter({identity,annotations:epoch?.annotations,force:true});annotations.reload();}}>Refresh tags</button></p>}
    {remoteNeeded&&annotations.loading&&!annotationData?<small role="status">Loading annotations…</small>:<>{scope==='epoch'&&<div className="annotation-group"><span>Direct epoch tags</span><div>{chips(groups.epoch,'epoch')}{!groups.epoch.length&&<small>None</small>}</div></div>}{scope!=='selected'&&<div className="annotation-group"><span>{scope==='cell'?'Cell tags':'Inherited from cell'} {!targetScope&&<button disabled={disabled||busy} onClick={()=>{setScope('cell');input.current?.focus();}}>Edit cell tags</button>}</span><div>{chips(groups.cell,'cell')}{!groups.cell.length&&<small>None</small>}</div></div>}</>}
    {message&&<small className="annotation-result" role="status">{message}</small>}
    {children&&scope==='epoch'&&<details className="annotation-legacy"><summary><ChevronDown size={12}/> Dataset-only tags</summary><p>These existing tags belong to this protocol’s selection; they are separate from shared cell and epoch annotations.</p>{children}</details>}
  </section>;
}
