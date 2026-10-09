import {canonicalReadIdentity} from '../../search-activation/pageReadCache.js';
import {epochIncluded} from '../../incoming-workbench/incomingReviewDecision.js';
import EpochInclusionToggle from '../../epoch-browser/ui/EpochInclusionToggle.jsx';
import {useDelayedLoading} from '../../components/NavigationLoading.jsx';
import {revealWithin} from '../../epoch-browser/epochListScroll.js';
import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,ChevronRight,FolderOpen,Home,Activity,GitBranch} from 'lucide-react';
import {api,number} from '../../api.js';
import {useTreeBranchReads} from '../../tree-ancestors/treeBranchReads.jsx';
import {loadColumnTreePages} from '../../tree-ancestors/columnTreeReads.js';
import {treeNavigationStart,treeNavigationSnapshot} from '../../pagedTreeRequest.js';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from '../treeBranchPresentation.js';
import {columnSelectionNeedsAnchor,columnBranchNavigation,columnWheelDelta} from '../columnTreeNavigation.js';
import {datedCellLabel} from '../../recording-import/recordingIdentity.js';
import './TreePreview.css';
import './ColumnTree.css';
import {IncomingEpochSelect,useIncomingTreeSelection} from '../../incoming-workbench/ui/IncomingTreeSelection.jsx';
import IncomingSelectionSummary from '../../incoming-workbench/ui/IncomingSelectionSummary.jsx';
import {TreeGroupTagButton,useTreeGroupTags} from '../../annotations/ui/TreeGroupTags.jsx';
import AnnotationIndicator from '../../annotations/ui/AnnotationIndicator.jsx';
import {incomingRowAnnotation} from '../../annotations/annotationTags.js';
import {treeCellUuid} from '../../annotations/useTreeCellSelection.js';

// Preserve the column interaction while loading at most one 60-row page per level.
export default function ColumnTree(props){
  const {protocolId,readContext,predicate,filters={},splits='',revision=0,expectedRevision,initialNavigation,selected}=props;
  const active=props.active!==false;
  const readOwner=useTreeBranchReads(),ownerIdentity=readOwner?.identity||'';
  const [state,setState]=useState({columns:[],loading:true,error:null,ownerIdentity:null});
  const ownerBlocked=!active||state.activation!==props.presentationActivation||state.ownerIdentity!==ownerIdentity||!!readOwner&&!readOwner.active();
  const actionProps={...props,actionsDisabled:props.actionsDisabled||ownerBlocked||state.loading||!!state.error};
  const groupTags=useTreeGroupTags(actionProps);
  const scopeKey=JSON.stringify({protocolId,readContext,predicate,filters,splits,revision,expectedRevision,annotationRevision:groupTags.revision,ownerIdentity,active,activation:props.presentationActivation});
  const presentationScope=canonicalReadIdentity({protocolId:protocolId??null,readContext:readContext??null,predicate:predicate??null,filters,splits,revision,expectedRevision:expectedRevision??null,annotationRevision:groupTags.revision,ownerIdentity});
  const groupSelection=useIncomingTreeSelection(actionProps,state.loadedScope===scopeKey&&!state.loading&&!state.error&&!ownerBlocked?state.columns[0]:null);
  // Presentation offsets never authorize reads or actions. Reuse only after the
  // fresh response confirms the same pages, revisions, scope and focus.
  const presentation=useRef(initialNavigation?.columnPresentation||null);
  const scrollIntent=useRef(0);
  const callbacks=useRef(props);callbacks.current=props;
  const visible=useRef(active),permitted=useRef(false);permitted.current=active&&!ownerBlocked&&!state.loading&&!state.error&&!props.actionsDisabled;
  const navigationIdentity=useMemo(()=>({scopeKey}),[scopeKey,readOwner]);
  const liveNavigation=useRef(null),navigationPermitted=useRef(false);
  navigationPermitted.current=(!state.loading||!props.onSelectBranch)&&active&&!ownerBlocked&&!state.error&&state.loadedScope===scopeKey&&!(props.navigationDisabled??props.actionsDisabled);
  const canNavigate=()=>visible.current&&liveNavigation.current===navigationIdentity&&navigationPermitted.current&&(!readOwner||readOwner.active());
  const canAct=()=>canNavigate()&&!pending.current&&permitted.current;
  const saved=useRef(initialNavigation),initialScope=useRef(scopeKey),restored=useRef(false);
  const showLoading=useDelayedLoading(state.loading&&!state.error);
  const retryIntent=useRef(null);
  const navigationIntent=useRef(null);
  const current=useRef([]),controller=useRef(null),serial=useRef(0),pending=useRef(true);
  const pathContains=(parent,path)=>parent.length<=path.length&&parent.every((key,index)=>key===path[index]);
  const canNavigatePath=target=>canNavigate()&&pathContains(target,navigationIntent.current?.path||current.current.at(-1)?.path||[]);
  const canNavigatePage=page=>canNavigate()&&current.current.includes(page)&&(!props.design||!navigationIntent.current||pathContains(page.path,navigationIntent.current.path));
  const latestSelected=useRef(selected),previousSelected=useRef(selected);latestSelected.current=selected;
  const strip=useRef(null),panes=useRef(new Map()),scrollRestore=useRef(null);
  function positions(){return current.current.map(page=>({offset:page.offset,scrollTop:panes.current.get(page.depth)?.scrollTop||0}));}
  function remember(){
    const last=current.current.at(-1);if(!last||pending.current)return;
    const columnPositions=positions(),scrollLeft=strip.current?.scrollLeft||0;
    presentation.current={scope:presentationScope,selected:latestSelected.current,columns:current.current.map((page,depth)=>({path:[...page.path],offset:page.offset,revision:page.revision,scrollTop:columnPositions[depth].scrollTop})),scrollLeft};
    callbacks.current.onNavigationChange?.({...treeNavigationSnapshot(last,panes.current.get(last.depth)?.scrollTop||0),columnPositions,scrollLeft,columnPresentation:presentation.current});
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
  const load=useCallback(async({path=[],offset=0,reset=false,revisionOverride=null,columnPositions=[],scrollTop=0,scrollLeft=null,anchor=null,freshContinuation=false,restorePresentation=null}={})=>{
    if(!active||!visible.current||liveNavigation.current!==navigationIdentity||readOwner&&!readOwner.active())return;
    const observer=callbacks.current; // Completion belongs to the initiating scope.
    retryIntent.current={scopeKey,options:{path:[...path],offset,anchor,columnPositions:columnPositions.map(position=>({...position})),scrollTop,scrollLeft}};
    controller.current?.abort();const request=new AbortController();controller.current=request;const token=++serial.current;pending.current=true;navigationIntent.current={token,path:[...path],offset};
    const startedScrollIntent=scrollIntent.current;
    const prior=current.current,priorPositions=prior.map(page=>({offset:page.offset,scrollTop:panes.current.get(page.depth)?.scrollTop||0}));
    if(reset)current.current=[];
    // Retain verified receipts, but Edit Tree immediately follows the requested
    // path. Old descendants must not appear to belong to the newly opened group.
    setState(old=>({...old,loading:true,error:null,requestedPath:anchor?null:[...path]}));observer.onStatus?.({loading:true,error:null});
    const scope=JSON.parse(scopeKey);
    try{
      const columns=await loadColumnTreePages({scope,path,offset,anchor,revisionOverride:revisionOverride||(!reset?prior.at(-1)?.revision:null),columnPositions,freshContinuation,retainedPages:reset?[]:prior,readOwner,load:api,signal:request.signal,isCurrent:()=>token===serial.current});
      const page=columns.at(-1);
      if(request.signal.aborted||token!==serial.current)return;
      const preserve=restorePresentation?.scope===presentationScope&&restorePresentation.selected===latestSelected.current&&restorePresentation.columns.length===columns.length&&columns.every((column,depth)=>{const old=restorePresentation.columns[depth];return old.revision===column.revision&&old.offset===column.offset&&JSON.stringify(old.path)===JSON.stringify(column.path);});
      const returnPositions=preserve?(scrollIntent.current!==startedScrollIntent?restorePresentation.columns.map((_,depth)=>({scrollTop:panes.current.get(depth)?.scrollTop||0})):restorePresentation.columns):null;
      const returnLeft=preserve?(scrollIntent.current!==startedScrollIntent?strip.current?.scrollLeft:restorePresentation.scrollLeft):null;
      current.current=columns;restored.current=true;
      scrollRestore.current=preserve?{vertical:returnPositions.map(position=>position.scrollTop),horizontal:returnLeft}:{vertical:columns.map((column,depth)=>depth===page.path.length?scrollTop:(columnPositions[depth]?.scrollTop??priorPositions[depth]?.scrollTop??0)),horizontal:scrollLeft};
      pending.current=false;setState({columns,loading:false,error:null,loadedScope:scopeKey,ownerIdentity,activation:props.presentationActivation,preservedSelection:preserve?latestSelected.current:undefined});observer.onStatus?.({loading:false,error:null});observer.onMetadata?.({...page,count:page.total_epochs});
    }catch(error){if(error.name!=='AbortError'&&!request.signal.aborted&&token===serial.current&&(!readOwner||readOwner.active())){setState(old=>({...old,loading:false,error:error.message}));observer.onStatus?.({loading:false,error:error.message});}}
    finally{if(token===serial.current){pending.current=false;navigationIntent.current=null;}}
  },[scopeKey,readOwner,navigationIdentity]);
  function retry(){
    if(!visible.current||!active||readOwner&&!readOwner.active())return;
    const intent=retryIntent.current;
    if(intent?.scopeKey!==scopeKey)return;
    if(expectedRevision){callbacks.current.onRefreshPreview?.();return;}
    load({...intent.options,reset:true,revisionOverride:null,freshContinuation:true});
  }
  useLayoutEffect(()=>{liveNavigation.current=navigationIdentity;navigationIntent.current=null;visible.current=active;controller.current?.abort();serial.current++;return()=>{liveNavigation.current=null;navigationIntent.current=null;retryIntent.current=null;visible.current=false;permitted.current=false;controller.current?.abort();serial.current++;};},[navigationIdentity]);
  useEffect(()=>{
    if(!active){pending.current=true;setState(old=>({...old,loading:true}));return;}
    const start=!restored.current&&initialScope.current===scopeKey?treeNavigationStart(saved.current,splits):null;
    const navigation=start?{...start,columnPositions:saved.current?.columnPositions||[],scrollLeft:saved.current?.scrollLeft??null}:{reset:true};
    // Mount/presentation changes follow the externally focused epoch. Ordinary
    // branch clicks below never trigger this selection effect again.
    if((initialScope.current===scopeKey||props.presentationActivation!==undefined)&&latestSelected.current)navigation.anchor=latestSelected.current;
    const previous=presentation.current;
    if(previous?.scope===presentationScope&&previous.selected===latestSelected.current)navigation.restorePresentation=previous;
    load(navigation);
    return()=>controller.current?.abort();
  },[load]);
  useEffect(()=>{
    if(!active||previousSelected.current===selected)return;
    previousSelected.current=selected;
    if(columnSelectionNeedsAnchor(current.current,selected,pending.current))load({anchor:selected});
  },[active,selected,load]);
  useEffect(()=>{
    if(!active||state.loading||!scrollRestore.current)return;
    const target=scrollRestore.current;scrollRestore.current=null;
    target.vertical.forEach((value,depth)=>{const pane=panes.current.get(depth);if(pane)pane.scrollTop=Number.isFinite(value)?Math.max(0,value):0;});
    if(strip.current)strip.current.scrollLeft=Number.isFinite(target.horizontal)?Math.max(0,target.horizontal):strip.current.scrollWidth;
    remember();
  },[state.columns,state.loading]);
  useEffect(()=>{
    if(!active||pending.current||state.loading||state.error||!selected||state.preservedSelection===selected)return;
    const token=serial.current;
    const frame=requestAnimationFrame(()=>{
      if(!visible.current||pending.current||token!==serial.current||latestSelected.current!==selected)return;
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
  const revealedTrace=useRef(null);
  useEffect(()=>{
    if(!active||state.loading||state.error||ownerBlocked||!props.trailingPane||!props.trailingPaneKey||state.columns.at(-1)?.kind!=='epochs'||!state.columns.at(-1)?.epochs.some(item=>item.epoch_uuid===selected))return;
    if(revealedTrace.current===props.trailingPaneKey)return;
    revealedTrace.current=props.trailingPaneKey;
    const pane=strip.current?.querySelector('.tree-trace-pane');
    if(pane)revealWithin(strip.current,pane,{horizontal:true,vertical:false});
  },[active,state.loading,state.error,state.columns,ownerBlocked,props.trailingPane,props.trailingPaneKey]);
  useEffect(()=>{if(!props.trailingPaneKey)revealedTrace.current=null;},[props.trailingPaneKey]);
  const requestedPath=props.design&&state.loadedScope===scopeKey?state.requestedPath:null;
  const columns=requestedPath?state.columns.filter(page=>pathContains(page.path,requestedPath)):state.columns;
  const last=columns.at(-1),root=columns[0],path=requestedPath||last?.path||[];
  const pathAncestors=()=>path.map((key,depth)=>columns[depth]?.branches?.find(branch=>branch.key===key)).filter(Boolean);
  const ancestors=requestedPath?pathAncestors():last?.ancestors||pathAncestors();
  return <section className={`tree-preview column-tree${props.design?' is-edit-tree':''}`} aria-label="Tree column overview" aria-busy={state.loading||active&&!state.error&&ownerBlocked}>
    {active&&!ownerBlocked&&groupTags.dialog}{active&&groupSelection.feedback}
    {active&&!props.refreshingLabelOwned&&(state.loading||!state.error&&ownerBlocked)&&state.columns.length>0&&<p className="tree-transient-status" role="status">Refreshing — previous view. Actions are unavailable until validation completes.</p>}
    {props.design&&(readContext?<IncomingSelectionSummary projectId={props.projectId} protocolId={protocolId} readContext={readContext} selected={props.selectedEpochs} paused={props.selectionSummaryPaused}/>:<header className="tp-total"><strong>{root?`Current view · ${number(root.total_epochs)} epochs`:'Loading tree…'}</strong><small>{last?.split_order.length??splits.split(',').filter(Boolean).length} split levels</small></header>)}
    {props.design&&<nav className="tp-path" aria-label="Tree ancestry"><button disabled={!canNavigate()} onClick={()=>{if(canNavigate())load({path:[]});}}><Home size={14}/> All matching epochs</button>{ancestors.map((node,index)=><span key={node.key}><ChevronRight size={12}/><button disabled={!canNavigate()} onClick={()=>{const target=path.slice(0,index+1);if(canNavigatePath(target))load({path:target});}} title={branchTooltip(node)}>{branchLabel(node)}</button></span>)}</nav>}
    {state.error&&<div className="pt-error" role="alert">{state.error}<button onClick={retry}>Reload tree overview</button></div>}
    <div className="tp-columns" ref={strip} onScroll={()=>{scrollIntent.current++;remember();}} aria-busy={state.loading||active&&!state.error&&ownerBlocked}>
      {columns.map((page,depth)=>{
        const terminal=page.kind==='epochs',entries=terminal?page.epochs.map(item=>props.inclusionForEpoch?props.inclusionForEpoch(item):item):page.branches,field=page.levels?.[depth],combined=entries.some(item=>item.components?.length),blocked=state.loading||!!state.error||ownerBlocked;
        return <section className={`tp-column ${terminal?'tp-terminal':''} ${combined?'tp-combined-column':''}`} key={`${depth}:${page.path.join(':')}`} aria-label={`${depth+1}. ${terminal?'Epochs':readableField(field?.label,field?.field)}`}>
          <header className="tp-level-heading"><span>{terminal?<Activity size={14}/>:depth+1}</span><div><strong title={field?.field}>{terminal?'Epochs':readableField(field?.label,field?.field)}</strong><small>{terminal?`${number(page.total)} epochs`:`${number(page.total)} groups · ${number(page.selection?.count??page.total_epochs)} epochs in scope`}</small></div></header>
          <div className="tp-column-content" ref={element=>{if(element)panes.current.set(depth,element);else panes.current.delete(depth);}} onScroll={()=>{scrollIntent.current++;remember();}}>
            {entries.map((item,index)=>{const branchOn=readContext&&!terminal&&!state.error&&!ownerBlocked&&state.loadedScope===scopeKey&&groupSelection.on(item,page);const tags=readContext&&(terminal||field?.field==='cell')?incomingRowAnnotation(terminal?item:props.cells?.find(cell=>cell.cell_uuid===item.value),terminal?'effective':'cell'):undefined;return terminal?<div key={item.epoch_uuid} className={`tp-epoch-row ${props.highlightedEpochs?.includes(item.epoch_uuid)?'is-highlighted':''} ${selected===item.epoch_uuid?'is-focused':''} ${readContext?props.selectedEpochs?.includes(item.epoch_uuid)?'incoming-epoch-on':'incoming-epoch-off':''}`} style={{display:'flex',alignItems:'center'}}>{readContext&&<IncomingEpochSelect epoch={item} selected={props.selectedEpochs} onSelect={props.setSelectedEpochs} onToggle={props.onSelectEpochToggle?event=>callbacks.current.onSelectEpochToggle(item.epoch_uuid,item,event,page,index):undefined} disabled={blocked||props.actionsDisabled}/>}<button style={{flex:1,minWidth:0}} className={`tp-epoch ${readContext?props.selectedEpochs?.includes(item.epoch_uuid)?'incoming-epoch-on':'incoming-epoch-off':''} ${tags?'has-saved-tags':''} ${(props.selectedEpochs?.includes(item.epoch_uuid)||(!readContext&&!props.selectedCell&&selected===item.epoch_uuid))?'selected':''}`} data-epoch-uuid={item.epoch_uuid} aria-pressed={props.highlightedEpochs?props.highlightedEpochs.includes(item.epoch_uuid):undefined} onMouseDown={event=>{if(event.shiftKey)event.preventDefault();}} aria-current={(props.selectedEpochs?.includes(item.epoch_uuid)||(!readContext&&!props.selectedCell&&selected===item.epoch_uuid))?'true':undefined} key={item.epoch_uuid} disabled={blocked} aria-description={tags} title={[item.epoch_uuid,tags].filter(Boolean).join('\n')} onClick={event=>{if(!canAct())return;remember();callbacks.current.onSelectEpoch?.(item.epoch_uuid,item,event,page,index);}}><strong>{epochLeafLabel(item)} {epochIncluded(item,!!props.readContext)===false&&<small className="tree-analysis-excluded">{props.readContext?'Excluded from incoming draft':'Excluded from analysis'}</small>}</strong>{tags&&<small className="tree-tag-marker" title={tags}>Tagged</small>}<span className="column-epoch-protocol" title={item.protocol_name}>{item.protocol_name?.split('.').at(-1)}</span></button>{readContext&&<><TreeGroupTagButton showLabel label="Tag This Epoch" count={1} disabled={blocked||props.actionsDisabled} onClick={event=>groupTags.openEpoch(item,event)}/></>}{props.onToggleInclusion&&<EpochInclusionToggle incoming={!!props.readContext} epoch={item} label={`epoch ${epochLeafLabel(item)}`} disabled={blocked||props.actionsDisabled} onToggle={(...args)=>{if(canAct())callbacks.current.onToggleInclusion?.(...args);}}/>}</div>:<div className={`tp-group-tag-wrap ${props.onToggleCell&&treeCellUuid(item,field)?'tp-cell-selectable':''}`} key={item.key}>{props.onToggleCell&&treeCellUuid(item,field)&&<input className="tp-cell-select" type="checkbox" aria-label={`Select cell ${branchLabel(item,field.field)} for shared tags`} checked={props.selectedCells?.includes(item.value)||false} disabled={blocked||props.actionsDisabled||(!props.selectedCells?.includes(item.value)&&props.selectedCells?.length>=1000)} onChange={event=>canAct()&&callbacks.current.onToggleCell({cell_uuid:item.value,label:branchLabel(item,field.field)},page.revision,event.target.checked)}/>}<button className={`tp-branch ${readContext?branchOn?'incoming-branch-on':'incoming-branch-off':''} ${path[depth]===item.key?'selected':''} ${props.design&&path[depth]===item.key?'is-active-path':''}`} aria-description={tags} key={item.key} aria-expanded={path[depth]===item.key} aria-current={props.design&&path[depth]===item.key?'step':undefined} disabled={!canNavigatePage(page)} onContextMenu={event=>groupTags.open(item,field,page,event)} onKeyDown={event=>{if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10')groupTags.open(item,field,page,event);}} title={[branchTooltip(item,field?.field),tags].filter(Boolean).join('\n')} onClick={()=>{if(!canNavigatePage(page))return;const notify=canAct(),navigation=columnBranchNavigation(page,item,(navigationIntent.current?.path||path)[depth]);load(navigation);if(notify&&navigation.opening)callbacks.current.onSelectBranch?.(item,field,page.revision);}}>
              <div className="tp-branch-title"><FolderOpen size={15}/><strong>{item.components?.length?'Matching combination':branchLabel(item,field?.field)}</strong><ChevronRight size={14}/></div>
              {!!item.components?.length&&<dl className="tp-combination">{item.components.map((part,index)=><div key={part.field} className={`joint-color-${index%3}`}><dt title={part.field}>{componentLabel(part)}</dt><dd>{componentValue(part)}</dd></div>)}</dl>}
              {!readContext&&field?.field==='cell'&&<AnnotationIndicator epoch={props.cells?.find(cell=>cell.cell_uuid===item.value)} level="cell"/>}<div className="tp-branch-counts"><span><b>{number(item.count)}</b> epochs</span></div>

            </button><TreeGroupTagButton selectionLimit={readContext?.selection_manifests?Infinity:1000} selectionOn={branchOn} selectionPendingOn={groupSelection.pending(item,page)?.on} label={readContext&&field?.field==='cell'?'Tag This Cell':'Tag this group'} onSelect={groupSelection.select?event=>groupSelection.select(item,page,event):undefined} disabled={blocked||props.actionsDisabled} count={item.count} onClick={event=>groupTags.open(item,field,page,event)}/></div>;})}
            {!entries.length&&!state.loading&&<p className="tp-no-groups">No matching epochs.</p>}
          </div>
          <footer className="tp-pagination"><button disabled={!canNavigatePage(page)||!(navigationIntent.current&&JSON.stringify(navigationIntent.current.path)===JSON.stringify(page.path)?navigationIntent.current.offset:page.offset)} aria-label={`Previous page in column ${depth+1}`} onClick={()=>{if(canNavigatePage(page)){const offset=navigationIntent.current&&JSON.stringify(navigationIntent.current.path)===JSON.stringify(page.path)?navigationIntent.current.offset:page.offset;load({path:page.path,offset:Math.max(0,offset-60)});}}}><ArrowLeft size={13}/></button><span>{page.total?page.offset+1:0}–{page.offset+entries.length} / {number(page.total)}</span><button disabled={!canNavigatePage(page)||(navigationIntent.current&&JSON.stringify(navigationIntent.current.path)===JSON.stringify(page.path)?navigationIntent.current.offset+60>=page.total:!page.has_more)} aria-label={`Next page in column ${depth+1}`} onClick={()=>{if(canNavigatePage(page)){const offset=navigationIntent.current&&JSON.stringify(navigationIntent.current.path)===JSON.stringify(page.path)?navigationIntent.current.offset:page.offset;if(offset+60<page.total)load({path:page.path,offset:offset+60});}}}><ArrowRight size={13}/></button></footer>
        </section>;
      })}
      {last?.kind==='epochs'&&!state.loading&&!state.error&&!ownerBlocked&&last.epochs.some(item=>item.epoch_uuid===selected)&&props.trailingPane}
      {requestedPath&&state.loading&&columns.length>0&&<div className="tp-column tp-pending-column" role="status">Loading group…</div>}
      {state.loading&&!state.columns.length?<div className="tp-prompt" role="status">{showLoading?'Loading tree…':''}</div>:last?.kind!=='epochs'&&!state.error&&!state.loading&&<div className="tp-prompt"><GitBranch size={24}/><strong>Choose a group</strong><p>Its next split opens alongside this column.</p></div>}
    </div>
    {showLoading&&!!state.columns.length&&<div className="tp-loading-notice" role="status">Updating tree…</div>}
    <footer className="tp-footer"><span>Tree splits preserve the full selection.</span><span>Scroll between levels. Select an epoch to view its recording alongside the columns.</span></footer>
  </section>;
}
