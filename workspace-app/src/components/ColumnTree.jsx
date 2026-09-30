import EpochInclusionToggle from './EpochInclusionToggle.jsx';
import {useDelayedLoading} from './NavigationLoading.jsx';
import {revealWithin} from '../epochListScroll.js';
import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,ChevronRight,FolderOpen,Home,Activity,GitBranch} from 'lucide-react';
import {api,number,duration} from '../api.js';
import {treePageRequest,treeNavigationStart,treeNavigationSnapshot} from '../pagedTreeRequest.js';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from '../treeBranchPresentation.js';
import {columnAncestorPages,canReuseColumn,columnSelectionNeedsAnchor,columnBranchNavigation,columnWheelDelta} from '../columnTreeNavigation.js';
import {datedCellLabel} from '../recordingIdentity.js';
import './TreePreview.css';
import './ColumnTree.css';
import AnnotationIndicator from './AnnotationIndicator.jsx';

// Preserve the column interaction while loading at most one 60-row page per level.
export default function ColumnTree(props){
  const {protocolId,predicate,filters={},splits='',revision=0,expectedRevision,initialNavigation,selected}=props;
  const scopeKey=JSON.stringify({protocolId,predicate,filters,splits,revision,expectedRevision});
  const callbacks=useRef(props);callbacks.current=props;
  const saved=useRef(initialNavigation),initialScope=useRef(scopeKey),restored=useRef(false);
  const [state,setState]=useState({columns:[],loading:true,error:null});
  const showLoading=useDelayedLoading(state.loading&&!state.error);
  const current=useRef([]),controller=useRef(null),serial=useRef(0),pending=useRef(true);
  const latestSelected=useRef(selected),previousSelected=useRef(selected);latestSelected.current=selected;
  const strip=useRef(null),panes=useRef(new Map()),scrollRestore=useRef(null);
  function positions(){return current.current.map(page=>({offset:page.offset,scrollTop:panes.current.get(page.depth)?.scrollTop||0}));}
  function remember(){
    const last=current.current.at(-1);if(!last||pending.current)return;
    callbacks.current.onNavigationChange?.({...treeNavigationSnapshot(last,panes.current.get(last.depth)?.scrollTop||0),columnPositions:positions(),scrollLeft:strip.current?.scrollLeft||0});
  }
  useEffect(()=>{
    const element=strip.current;
    if(!element)return;
    const wheel=event=>{
      const delta=columnWheelDelta(event,element.clientWidth);
      if(!delta)return;
      // Consume the gesture even at the boundary; it must not navigate browser history.
      event.preventDefault();element.scrollLeft+=delta;
    };
    element.addEventListener('wheel',wheel,{passive:false});
    return()=>element.removeEventListener('wheel',wheel);
  },[]);
  const load=useCallback(async({path=[],offset=0,reset=false,revisionOverride=null,columnPositions=[],scrollTop=0,scrollLeft=null,anchor=null}={})=>{
    controller.current?.abort();const request=new AbortController();controller.current=request;const token=++serial.current;pending.current=true;
    const prior=current.current,priorPositions=prior.map(page=>({offset:page.offset,scrollTop:panes.current.get(page.depth)?.scrollTop||0}));
    if(reset)current.current=[];
    // Retain the last columns visually while the new scope loads; blocked rows
    // cannot act on the previous revision. Commit the replacement atomically.
    setState(old=>({columns:old.columns,loading:true,error:null}));callbacks.current.onStatus?.({loading:true,error:null});
    const scope=JSON.parse(scopeKey);
    const fetchPage=(pagePath,pageOffset,pageRevision,pageAnchor=null)=>api('/tree-pages',{method:'POST',signal:request.signal,body:treePageRequest(scope,{path:pagePath,offset:pageOffset,anchor:pageAnchor,reset:reset&&!pageRevision,currentRevision:pageRevision})});
    try{
      const page=await fetchPage(path,offset,revisionOverride||(!reset?prior.at(-1)?.revision:null),anchor);
      // Restore ancestors against the SAME revision, never a fresh membership.
      const targets=columnAncestorPages(page,{anchor:!!anchor,columnPositions});
      const parents=await Promise.all(targets.map(target=>{
        const cached=prior[target.depth];
        if(!reset&&canReuseColumn(cached,target))return cached;
        return fetchPage(target.path,target.offset,page.revision);
      }));
      if(request.signal.aborted||token!==serial.current)return;
      const columns=[...parents,page];current.current=columns;restored.current=true;
      scrollRestore.current={vertical:columns.map((column,depth)=>depth===page.path.length?scrollTop:(columnPositions[depth]?.scrollTop??priorPositions[depth]?.scrollTop??0)),horizontal:scrollLeft};
      pending.current=false;setState({columns,loading:false,error:null});callbacks.current.onStatus?.({loading:false,error:null});callbacks.current.onMetadata?.({...page,count:page.total_epochs});
    }catch(error){if(!request.signal.aborted&&token===serial.current){setState(old=>({...old,loading:false,error:error.message}));callbacks.current.onStatus?.({loading:false,error:error.message});}}
    finally{if(token===serial.current)pending.current=false;}
  },[scopeKey]);
  useEffect(()=>{
    const start=!restored.current&&initialScope.current===scopeKey?treeNavigationStart(saved.current,splits):null;
    const navigation=start?{...start,columnPositions:saved.current?.columnPositions||[],scrollLeft:saved.current?.scrollLeft??null}:{reset:true};
    // Mount/presentation changes follow the externally focused epoch. Ordinary
    // branch clicks below never trigger this selection effect again.
    if(initialScope.current===scopeKey&&latestSelected.current)navigation.anchor=latestSelected.current;
    load(navigation);
    return()=>controller.current?.abort();
  },[load]);
  useEffect(()=>{
    if(previousSelected.current===selected)return;
    previousSelected.current=selected;
    if(columnSelectionNeedsAnchor(current.current,selected,pending.current))load({anchor:selected});
  },[selected,load]);
  useEffect(()=>{
    if(state.loading||!scrollRestore.current)return;
    const target=scrollRestore.current;scrollRestore.current=null;
    target.vertical.forEach((value,depth)=>{const pane=panes.current.get(depth);if(pane)pane.scrollTop=Number.isFinite(value)?Math.max(0,value):0;});
    if(strip.current)strip.current.scrollLeft=Number.isFinite(target.horizontal)?Math.max(0,target.horizontal):strip.current.scrollWidth;
    remember();
  },[state.columns,state.loading]);
  useEffect(()=>{
    if(state.loading||state.error||!selected)return;
    const frame=requestAnimationFrame(()=>{
      const leaf=current.current.at(-1),pane=panes.current.get(leaf?.depth);
      const element=Array.from(pane?.querySelectorAll('[data-epoch-uuid]')||[]).find(item=>item.dataset.epochUuid===selected);
      if(!element)return;
      // Keep the selected path visible, adjusting each pane only as needed.
      for(const page of current.current.slice(0,-1)){const parent=panes.current.get(page.depth);revealWithin(parent,parent?.querySelector('.tp-branch.selected'));}
      revealWithin(pane,element);
      revealWithin(strip.current,pane?.closest('.tp-column'),{horizontal:true,vertical:false});
      remember();
    });
    return()=>cancelAnimationFrame(frame);
  },[selected,state.columns,state.loading,state.error]);
  const last=state.columns.at(-1),root=state.columns[0],path=last?.path||[];
  const ancestors=last?.ancestors||path.map((key,depth)=>state.columns[depth]?.branches?.find(branch=>branch.key===key)).filter(Boolean);
  return <section className="tree-preview column-tree" aria-label="Tree column overview" aria-busy={state.loading}>
    {props.design&&<header className="tp-total"><strong>{root?`${number(root.total_epochs)} epochs`:'Loading tree…'}</strong><span>{root?`${number(root.cells)} cells · ${duration(root.duration_seconds)}`:''}</span><small>{last?.split_order.length??splits.split(',').filter(Boolean).length} split levels</small></header>}
    {props.design&&<nav className="tp-path" aria-label="Tree ancestry"><button disabled={state.loading} onClick={()=>load({path:[]})}><Home size={14}/> All matching epochs</button>{ancestors.map((node,index)=><span key={node.key}><ChevronRight size={12}/><button disabled={state.loading} onClick={()=>load({path:path.slice(0,index+1)})} title={branchTooltip(node)}>{branchLabel(node)}</button></span>)}</nav>}
    {state.error&&<div className="pt-error" role="alert">{state.error}<button onClick={()=>expectedRevision?callbacks.current.onRefreshPreview?.():load({reset:true})}>Reload tree overview</button></div>}
    <div className="tp-columns" ref={strip} onScroll={remember} aria-busy={state.loading}>
      {state.columns.map((page,depth)=>{
        const terminal=page.kind==='epochs',entries=terminal?page.epochs.map(item=>props.inclusionForEpoch?props.inclusionForEpoch(item):item):page.branches,field=page.levels?.[depth],combined=entries.some(item=>item.components?.length),blocked=state.loading||!!state.error;
        return <section className={`tp-column ${terminal?'tp-terminal':''} ${combined?'tp-combined-column':''}`} key={`${depth}:${page.path.join(':')}`} aria-label={`${depth+1}. ${terminal?'Epochs':readableField(field?.label,field?.field)}`}>
          <header className="tp-level-heading"><span>{terminal?<Activity size={14}/>:depth+1}</span><div><strong title={field?.field}>{terminal?'Epochs':readableField(field?.label,field?.field)}</strong><small>{number(page.total)} {terminal?'epochs':'groups'} · {number(page.selection?.count??page.total_epochs)} epochs in scope</small></div></header>
          <div className="tp-column-content" ref={element=>{if(element)panes.current.set(depth,element);else panes.current.delete(depth);}} onScroll={remember}>
            {entries.map((item,index)=>terminal?<div key={item.epoch_uuid} style={{display:'flex',alignItems:'center'}}><button style={{flex:1,minWidth:0}} className={`tp-epoch ${(props.selectedEpochs?.includes(item.epoch_uuid)||(!props.selectedCell&&selected===item.epoch_uuid))?'selected':''}`} data-epoch-uuid={item.epoch_uuid} aria-current={(props.selectedEpochs?.includes(item.epoch_uuid)||(!props.selectedCell&&selected===item.epoch_uuid))?'true':undefined} key={item.epoch_uuid} disabled={blocked} title={item.epoch_uuid} onClick={event=>{remember();callbacks.current.onSelectEpoch?.(item.epoch_uuid,item,event,page,index);}}><strong>{epochLeafLabel(item)} {item.curation?.included===false&&<small className="tree-analysis-excluded">Excluded from analysis</small>}</strong><span className="column-epoch-protocol" title={item.protocol_name}>{item.protocol_name?.split('.').at(-1)}</span></button>{props.onToggleInclusion&&<EpochInclusionToggle epoch={item} label={`epoch ${epochLeafLabel(item)}`} disabled={blocked||props.actionsDisabled} onToggle={props.onToggleInclusion}/>}</div>:<button className={`tp-branch ${path[depth]===item.key?'selected':''}`} key={item.key} aria-expanded={path[depth]===item.key} disabled={blocked} title={branchTooltip(item,field?.field)} onClick={()=>{const navigation=columnBranchNavigation(page,item,path[depth]);load(navigation);if(navigation.opening)callbacks.current.onSelectBranch?.(item,field,page.revision);}}>
              <div className="tp-branch-title"><FolderOpen size={15}/><strong>{item.components?.length?'Matching combination':branchLabel(item,field?.field)}</strong><ChevronRight size={14}/></div>
              {!!item.components?.length&&<dl className="tp-combination">{item.components.map((part,index)=><div key={part.field} className={`joint-color-${index%3}`}><dt title={part.field}>{componentLabel(part)}</dt><dd>{componentValue(part)}</dd></div>)}</dl>}
              {field?.field==='cell'&&<AnnotationIndicator epoch={props.cells?.find(cell=>cell.cell_uuid===item.value)} level="cell"/>}{field?.field!=='cell'&&<div className="tp-branch-counts"><span><b>{number(item.count)}</b> epochs</span><span>{number(item.cells)} {item.cells===1?'cell':'cells'}</span></div>}
              <div className="tp-distribution" aria-hidden="true"><span style={{width:`${Math.min(100,100*item.count/Math.max(1,page.selection?.count??page.total_epochs))}%`}}/></div><small>{duration(item.duration_seconds)}</small>
            </button>)}
            {!entries.length&&!state.loading&&<p className="tp-no-groups">No matching epochs.</p>}
          </div>
          <footer className="tp-pagination"><button disabled={blocked||!page.offset} aria-label={`Previous page in column ${depth+1}`} onClick={()=>load({path:page.path,offset:Math.max(0,page.offset-60)})}><ArrowLeft size={13}/></button><span>{page.total?page.offset+1:0}–{page.offset+entries.length} / {number(page.total)}</span><button disabled={blocked||!page.has_more} aria-label={`Next page in column ${depth+1}`} onClick={()=>load({path:page.path,offset:page.offset+60})}><ArrowRight size={13}/></button></footer>
        </section>;
      })}
      {state.loading&&!state.columns.length?<div className="tp-prompt" role="status">{showLoading?'Loading tree…':''}</div>:last?.kind!=='epochs'&&!state.error&&<div className="tp-prompt"><GitBranch size={24}/><strong>Choose a group</strong><p>Its next split opens alongside this column.</p></div>}
    </div>
    {showLoading&&!!state.columns.length&&<div className="tp-loading-notice" role="status">Updating tree…</div>}
    <footer className="tp-footer"><span>Tree splits preserve the full selection.</span><span>Scroll left or right between levels. Select an epoch here, then use Back to epochs to inspect it.</span></footer>
  </section>;
}
