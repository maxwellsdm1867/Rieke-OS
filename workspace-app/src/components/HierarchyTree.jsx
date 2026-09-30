import EpochInclusionToggle from './EpochInclusionToggle.jsx';
import {revealWithin} from '../epochListScroll.js';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Activity,ArrowLeft,ArrowRight,ChevronDown,ChevronRight,Folder,FolderOpen,LoaderCircle,RefreshCw} from 'lucide-react';
import {api,number,duration} from '../api.js';
import {treePageRequest} from '../pagedTreeRequest.js';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from '../treeBranchPresentation.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {hierarchyKey,pathContains,mergeHierarchyPage,collapseHierarchy,expandHierarchy,hierarchySnapshot,hierarchyRestore,cancelUnloadedExpansion} from '../hierarchyTreeState.js';
import './HierarchyTree.css';

const blank=()=>({pages:[],expanded:[],loading:true,error:null,loadingPath:[],notice:''});
export default function HierarchyTree(props){
  const {protocolId,predicate,filters={},splits='',revision=0,expectedRevision,initialNavigation,selected}=props;
  const scopeKey=JSON.stringify({protocolId,predicate,filters,splits,revision,expectedRevision});
  const callbacks=useRef(props);callbacks.current=props;
  const [state,setState]=useState(blank),current=useRef(state),controller=useRef(null),serial=useRef(0),scroll=useRef(null),container=useRef(null);
  const firstScope=useRef(scopeKey),saved=useRef(initialNavigation),initialized=useRef(false),restoreTop=useRef(null),restoreLeft=useRef(null),scrollFrame=useRef(null);
  const commit=useCallback(update=>{current.current=typeof update==='function'?update(current.current):update;setState(current.current);},[]);
  function remember(){if(current.current.loading||current.current.error)return;const snapshot=hierarchySnapshot(current.current,scroll.current?.scrollTop||0,scroll.current?.scrollLeft||0);if(snapshot)callbacks.current.onNavigationChange?.(snapshot);}
  const load=useCallback(async({path=[],offset=0,reset=false,anchor=null,restore=null}={})=>{
    controller.current?.abort();const request=new AbortController();controller.current=request;const token=++serial.current;
    commit(old=>({...(reset?blank():cancelUnloadedExpansion(old,path)),loading:true,error:null,loadingPath:path}));callbacks.current.onStatus?.({loading:true,error:null});
    const scope=JSON.parse(scopeKey),root=current.current.pages.find(page=>!page.path.length);
    let pinned=scope.expectedRevision||restore?.revision||(!reset?root?.revision:null);
    async function fetchPage(pagePath,pageOffset=0,focus=null){
      const result=await api('/tree-pages',{method:'POST',signal:request.signal,
        body:treePageRequest(scope,{path:pagePath,offset:pageOffset,anchor:focus,reset:!pinned,currentRevision:pinned})});
      if(pinned&&result.revision!==pinned)throw new Error('Tree revision changed. Refresh the preview before continuing.');
      pinned=result.revision;return result;
    }
    try{
      let result;
      if(restore){
        for(const savedPage of restore.pages){result=await fetchPage(savedPage.path,savedPage.offset);if(request.signal.aborted||token!==serial.current)return;commit(old=>mergeHierarchyPage(old,result));}
        commit(old=>({...old,expanded:restore.expanded}));restoreTop.current=restore.scrollTop;restoreLeft.current=restore.scrollLeft;
      }else if(anchor){
        result=await fetchPage([],0,anchor);
        const ancestry=result.ancestors||[];
        // The locator supplies each ancestor's parent page, including groups
        // past the first60. Fetch only this path and retain existing siblings.
        for(let depth=0;depth<result.path.length;depth++){
          const parentPath=result.path.slice(0,depth),parentKey=hierarchyKey(parentPath);
          const desiredOffset=ancestry[depth]?.parent_offset??0;
          const cached=current.current.pages.find(page=>hierarchyKey(page.path)===parentKey&&page.revision===pinned&&page.offset===desiredOffset);
          if(!cached){const parent=await fetchPage(parentPath,desiredOffset);if(request.signal.aborted||token!==serial.current)return;commit(old=>mergeHierarchyPage(old,parent));}
        }
        if(request.signal.aborted||token!==serial.current)return;
        commit(old=>{let next=mergeHierarchyPage(old,result);for(let depth=1;depth<=result.path.length;depth++)next=expandHierarchy(next,result.path.slice(0,depth));return next;});
      }else{
        result=await fetchPage(path,offset);
        if(request.signal.aborted||token!==serial.current)return;
        commit(old=>{const next=mergeHierarchyPage(old,result);return {...next,notice:next.evicted?'Older branches were collapsed to keep the tree responsive. Reopen them when needed.':old.notice};});
      }
      if(request.signal.aborted||token!==serial.current)return;
      initialized.current=true;commit(old=>({...old,loading:false,loadingPath:null,error:null}));callbacks.current.onStatus?.({loading:false,error:null});
      const receipt=current.current.pages.find(page=>!page.path.length)||result;
      callbacks.current.onMetadata?.({...receipt,count:receipt.total_epochs});
    }catch(error){if(!request.signal.aborted&&token===serial.current){commit(old=>({...old,loading:false,error:error.message,loadingPath:null}));callbacks.current.onStatus?.({loading:false,error:error.message});}}
  },[scopeKey,commit]);
  useEffect(()=>{
    const restore=!initialized.current&&firstScope.current===scopeKey?hierarchyRestore(saved.current,splits):null;
    load({reset:true,...(restore?{restore}:selected?{anchor:selected}:{})});
    return()=>{controller.current?.abort();if(scrollFrame.current)cancelAnimationFrame(scrollFrame.current);};
  },[load]);
  const previousSelected=useRef(selected),revealSelected=useRef(selected),focusScroll=useRef(initialNavigation?null:selected);
  useEffect(()=>{
    if(previousSelected.current!==selected){previousSelected.current=selected;revealSelected.current=selected;focusScroll.current=selected;}
    if(current.current.loading||current.current.error||!revealSelected.current)return;
    const target=revealSelected.current;revealSelected.current=null;
    const visible=current.current.pages.some(page=>page.kind==='epochs'&&page.epochs.some(epoch=>epoch.epoch_uuid===target)&&page.path.every((_,index)=>current.current.expanded.some(open=>hierarchyKey(open)===hierarchyKey(page.path.slice(0,index+1)))));
    if(!visible){focusScroll.current=target;load({anchor:target});}
  },[selected,load,state.pages,state.loading,state.error]);
  useEffect(()=>{
    if(state.loading||state.error)return;
    if(restoreTop.current!==null&&scroll.current){scroll.current.scrollTop=restoreTop.current;scroll.current.scrollLeft=restoreLeft.current||0;restoreTop.current=null;restoreLeft.current=null;}
    remember();
  },[state.pages,state.expanded,state.loading,state.error]);
  useEffect(()=>{if(!state.loading&&focusScroll.current){const node=container.current?.querySelector(`[data-epoch-uuid="${focusScroll.current}"]`);if(node){revealWithin(scroll.current,node);focusScroll.current=null;}}},[selected,state.pages,state.loading]);
  function toggle(branch){
    if(current.current.error)return false;
    const key=hierarchyKey(branch.path),opened=current.current.expanded.some(path=>hierarchyKey(path)===key);
    if(opened){
      revealSelected.current=null;focusScroll.current=null;
      if(current.current.loadingPath&&pathContains(branch.path,current.current.loadingPath)){controller.current?.abort();serial.current++;callbacks.current.onStatus?.({loading:false,error:null});}
      commit(old=>({...collapseHierarchy(old,branch.path),loading:old.loadingPath&&pathContains(branch.path,old.loadingPath)?false:old.loading,loadingPath:old.loadingPath&&pathContains(branch.path,old.loadingPath)?null:old.loadingPath}));
    }else{
      commit(old=>expandHierarchy(old,branch.path));
      if(!current.current.pages.some(page=>hierarchyKey(page.path)===key))load({path:branch.path});
    }
    return !opened;
  }
  function collapseAll(){
    controller.current?.abort();serial.current++;
    revealSelected.current=null;focusScroll.current=null;
    commit(old=>({...old,expanded:[],loading:false,loadingPath:null}));
    callbacks.current.onStatus?.({loading:false,error:null});
  }
  const previousCollapseRequest=useRef(props.collapseRequest);
  useEffect(()=>{if(previousCollapseRequest.current!==props.collapseRequest){previousCollapseRequest.current=props.collapseRequest;collapseAll();}},[props.collapseRequest]);
  function branchKeys(event,branch,opened){
    if(event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();if(!opened)toggle(branch);else event.currentTarget.closest('li')?.querySelector('ul button')?.focus({preventScroll:true});}
    if(event.key==='ArrowLeft'){event.preventDefault();event.stopPropagation();if(opened)toggle(branch);else event.currentTarget.closest('ul')?.closest('li')?.querySelector(':scope > button')?.focus({preventScroll:true});}
  }
  const root=state.pages.find(page=>!page.path.length),blocked=!!state.error;
  function renderPage(page,isRoot=false){
    const entries=page.kind==='epochs'?page.epochs:page.branches,field=page.levels?.[page.depth];
    const label=page.kind==='epochs'?'Epochs':readableField(field?.label,field?.field);
    return <ul className={isRoot?'ht-root':'ht-children'} role={isRoot?'tree':'group'} aria-label={isRoot?'Recording hierarchy':label}>
      {entries.map((item,index)=>{
        if(page.kind==='epochs'){const epoch=props.inclusionForEpoch?props.inclusionForEpoch(item):item;return <li className="ht-leaf" key={item.epoch_uuid} role="treeitem" aria-selected={props.selectedEpochs?.includes(item.epoch_uuid)||(!props.selectedCell&&selected===item.epoch_uuid)}><button data-epoch-uuid={item.epoch_uuid} className={(props.selectedEpochs?.includes(item.epoch_uuid)||(!props.selectedCell&&selected===item.epoch_uuid))?'selected':''} disabled={blocked||state.loading||props.actionsDisabled} title={item.epoch_uuid} onKeyDown={event=>{if(event.key==='ArrowLeft'){event.preventDefault();event.stopPropagation();event.currentTarget.closest('ul')?.closest('li')?.querySelector(':scope > button')?.focus({preventScroll:true});}}} onClick={event=>{remember();callbacks.current.onSelectEpoch?.(item.epoch_uuid,item,event,page,index);}}><Activity size={14}/><span className="ht-value">{epochLeafLabel(item)}<small>{datedCellLabel(item)}</small></span></button>{props.onToggleInclusion&&<EpochInclusionToggle epoch={epoch} label={`epoch ${epochLeafLabel(item)}`} disabled={blocked||state.loading||props.actionsDisabled} onToggle={props.onToggleInclusion}/>}{!props.onToggleInclusion&&<span className={`ht-inclusion-state ${epoch.curation?.included===false?'excluded':''}`}>{epoch.curation?.included===false?'Excluded':'Included'}</span>}</li>;}
        const key=hierarchyKey(item.path),opened=state.expanded.some(path=>hierarchyKey(path)===key),children=state.pages.find(child=>hierarchyKey(child.path)===key),loading=state.loading&&hierarchyKey(state.loadingPath||[])===key;
        return <li key={item.key} role="treeitem" aria-expanded={opened} className={opened?'ht-branch expanded':'ht-branch'}><button className={field?.field==='cell'&&props.selectedCell===item.value?'selected':''} aria-expanded={opened} disabled={blocked} onClick={()=>{if(toggle(item))callbacks.current.onSelectBranch?.(item,field,page.revision);}} onKeyDown={event=>branchKeys(event,item,opened)} title={[branchTooltip(item,field?.field),item.start_time&&`Recorded start: ${item.start_time}`].filter(Boolean).join('\n')}>{loading?<LoaderCircle size={14} className="spin"/>:opened?<ChevronDown size={14}/>:<ChevronRight size={14}/>}<span className="ht-folder">{opened?<FolderOpen size={15}/>:<Folder size={15}/>}</span><span className="ht-value"><span className="ht-field">{!item.components?.length&&`${label}: `}</span>{item.components?.length?<span className="ht-combination">{item.components.map(part=><span key={part.field}><small>{componentLabel(part)}</small> {componentValue(part)}</span>)}</span>:field?.field==='block'&&item.start_time?item.start_time:branchLabel(item,field?.field)}</span>{field?.field!=='cell'&&<span className="ht-count">{number(item.count)} <small>epochs</small></span>}</button>{opened&&(children?renderPage(children):<div className="ht-loading" role="status">{loading?'Loading branch…':'Branch is not loaded.'}</div>)}</li>;
      })}
      {!entries.length&&<li className="ht-empty">No matching epochs.</li>}
      {(page.offset>0||page.has_more)&&<li role="none" className="ht-pagination"><button disabled={blocked||state.loading||!page.offset} aria-label={`Previous ${label} page`} onClick={()=>load({path:page.path,offset:Math.max(0,page.offset-60)})}><ArrowLeft size={13}/></button><span>{page.offset+1}–{page.offset+entries.length} / {number(page.total)}</span><button disabled={blocked||state.loading||!page.has_more} aria-label={`Next ${label} page`} onClick={()=>load({path:page.path,offset:page.offset+60})}><ArrowRight size={13}/></button></li>}
    </ul>;
  }
  return <section ref={container} className="hierarchy-tree" style={{'--hierarchy-min-width':`${Math.max(400,(root?.levels.length||0)*23+320)}px`}} aria-label="Expandable recording tree" onKeyDown={props.onKeyDown}>
    {props.design&&<header className="ht-heading"><strong>{root?`${number(root.total_epochs)} matching epochs`:'Loading hierarchy…'}</strong><span>{root?`${number(root.cells)} cells · ${duration(root.duration_seconds)}`:''}</span></header>}
    <div className="ht-splits" aria-label="Tree split sequence">{root?.levels.length?root.levels.map((field,index)=><span key={field.field}>{index>0&&<ChevronRight size={11}/>}<b>{index+1}</b>{readableField(field.label,field.field)}</span>):<span>Flat epoch list</span>}</div>
    {state.error&&<div className="ht-error" role="alert">{state.error}<button onClick={()=>expectedRevision?callbacks.current.onRefreshPreview?.():load({reset:true})}><RefreshCw size={13}/> Refresh tree</button></div>}
    {state.notice&&<div className="ht-notice" role="status">{state.notice}</div>}
    <div className="ht-scroll" ref={scroll} aria-busy={state.loading} onScroll={()=>{if(!scrollFrame.current)scrollFrame.current=requestAnimationFrame(()=>{scrollFrame.current=null;remember();});}}>{root?renderPage(root,true):!state.error&&<p className="ht-loading" role="status">Loading tree…</p>}</div>
    {!props.externalCollapseControl&&<footer className="ht-footer"><button disabled={blocked||!state.expanded.length} onClick={collapseAll}>Collapse all</button></footer>}
  </section>;
}
