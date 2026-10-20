import {tagStore} from '../../annotations/tagStore.js';
import {useWorkspaceRequest,useWorkspaceRequestScope} from '../../workspaceRequest.js';
import {IncomingEpochSelect} from '../../incoming-workbench/ui/IncomingTreeSelection.jsx';
import {TreeGroupTagButton,useTreeGroupTags} from '../../annotations/ui/TreeGroupTags.jsx';
import {loadIncomingSelection} from '../../incoming-workbench/incomingSelection.js';
import {frozenPresentationScope} from '../frozenReadContext.js';
import StableContent from '../../components/StableContent.jsx';
import {epochIncluded} from '../../incoming-workbench/incomingReviewDecision.js';
import {memo,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import EpochInclusionToggle from './EpochInclusionToggle.jsx';
import {api as defaultApi,humanize} from '../../api.js';
import {epochPageRequest,epochPageRevision} from '../epochBrowserSource.js';
import {epochSelectionRange,toggleEpochSelection,mergeEpochSelection} from '../../epochSelection.js';
import {inspectionDates} from '../inspectionCellTree.js';
import {datedCellLabel} from '../../recording-import/recordingIdentity.js';
import {Status} from '../../components/Common.jsx';
import {incomingRowAnnotation} from '../../annotations/annotationTags.js';
import './InspectionCellTree.css';
import {useEpochBrowserPage} from '../useEpochBrowserPage.js';
import {createEpochPageReads} from '../epochPageReads.js';
import {inspectionNavigation,inspectionPageOffset,toggleInspectionBranch,restoreInspectionScroll} from '../inspectionNavigation.js';

const NO_IDS=[];
function CellEpochPage({rowRegistry,highlightedEpochs,cell,offset,restoreOffset,onFrontier,expected,onFault,revealEpoch,seen=NO_IDS,source,revision,pageReads,focused,onFocus,targets,onSelect,disabled,navigationDisabled=disabled,onToggleInclusion,inclusionForEpoch,setTargets,onTagEpoch}){
  const pageSize=useWorkspaceRequestScope()?.pageSize??60;
  const page=useEpochBrowserPage(source,{cellUuid:cell.cell_uuid,offset},JSON.stringify([revision,source.queryRevision,source.treeRevision]),pageReads);
  // Loaded rows carry author revisions: hints let selection tags write in one request.
  useEffect(()=>{if(Array.isArray(page.data?.epochs))tagStore.hint(page.data.epochs);},[page.data]);
  const [expanded,setExpanded]=useState(false);
  const tail=useRef(null);
  // Set lookups keep row rendering linear in visible rows, not rows x selection.
  const seenIds=useMemo(()=>new Set(seen),[seen]),targetIds=useMemo(()=>new Set(targets),[targets]),highlightedIds=useMemo(()=>highlightedEpochs?new Set(highlightedEpochs):null,[highlightedEpochs]);
  const childSeen=useMemo(()=>Array.isArray(page.data?.epochs)?[...seen,...page.data.epochs.map(row=>row.epoch_uuid)]:seen,[seen,page.data]);
  let receipt=null,problem=null;
  if(page.data){
    try{
      const data=page.data,rows=data.epochs;
      receipt=JSON.stringify([epochPageRevision(source,data),data.total,data.expected_binding_version??null]);
      if(!Number.isInteger(data.total)||data.total<0||data.offset!==offset||!Array.isArray(rows)||rows.length>pageSize||
          rows.length!==Math.min(pageSize,Math.max(0,data.total-offset))||
          rows.some(row=>!row||row.cell_uuid!==cell.cell_uuid||typeof row.epoch_uuid!=='string'||!row.epoch_uuid||seenIds.has(row.epoch_uuid))||new Set(rows.map(row=>row.epoch_uuid)).size!==rows.length||
          (expected!==null&&expected!==receipt))throw Error('Epoch list changed while scrolling. Reload the list.');
    }catch(error){problem=error.message;}
  }
  useLayoutEffect(()=>{if(problem)onFault(problem);else if(page.data&&!page.loading&&!page.error)onFrontier(offset);},[problem,receipt,page.loading,page.error,offset]);
  const ready=!!page.data&&!page.loading&&!page.error&&!problem;
  if(ready&&rowRegistry)for(const row of page.data.epochs)rowRegistry.add(row.epoch_uuid);
  const more=ready&&offset+page.data.epochs.length<page.data.total;
  useEffect(()=>{
    if(!more||expanded||navigationDisabled||typeof IntersectionObserver==='undefined'||!tail.current)return;
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))setExpanded(true);},
      {root:tail.current.closest('.tree-scroll'),rootMargin:'150px 0px'});
    observer.observe(tail.current);return()=>observer.disconnect();
  },[more,expanded,navigationDisabled]);
  const reveal=ready&&revealEpoch?.cell_uuid===cell.cell_uuid&&!page.data.epochs.some(row=>row.epoch_uuid===revealEpoch.epoch_uuid);
  useEffect(()=>{if(more&&reveal)setExpanded(true);},[more,reveal]);
  const content=<>
    {(ready?page.data.epochs:[]).map((record,index)=>{const epoch=inclusionForEpoch?inclusionForEpoch(record):record,tags=source.readContext?incomingRowAnnotation(epoch):undefined;return <div key={epoch.epoch_uuid} className={`epoch-row cell-tree-epoch ${tags?'has-shared-tags':''} ${highlightedIds?.has(epoch.epoch_uuid)?'is-highlighted':''} ${focused===epoch.epoch_uuid?'active':''} ${targetIds.has(epoch.epoch_uuid)?'bulk-selected':''} ${epochIncluded(epoch,!!source.readContext)===false?'analysis-excluded':''}`}>
      <button aria-description={tags} title={tags} disabled={navigationDisabled||page.loading} aria-current={focused===epoch.epoch_uuid?'true':undefined} aria-pressed={highlightedIds?highlightedIds.has(epoch.epoch_uuid):targetIds.has(epoch.epoch_uuid)||(!source.readContext&&!targets.length&&focused===epoch.epoch_uuid)} onMouseDown={event=>{if(event.shiftKey)event.preventDefault();}} onClick={event=>onSelect(event,{cellUuid:cell.cell_uuid,index:offset+index,uuid:epoch.epoch_uuid},epoch,page.data)} aria-label={`Inspect ${datedCellLabel(cell,true)} epoch ${offset+index+1}`}>
        <strong>{offset+index+1}</strong>
        <time>{epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'—'}</time>
        <span className="epoch-short-protocol" title={humanize(epoch.protocol_name?.split('.').at(-1))}>{humanize(epoch.protocol_name?.split('.').at(-1))||'—'}</span>
      </button>
      {source.readContext&&<><IncomingEpochSelect epoch={epoch} selected={targets} onSelect={setTargets} onToggle={event=>onSelect(event,{cellUuid:cell.cell_uuid,index:offset+index,uuid:epoch.epoch_uuid},epoch,page.data,true)} disabled={disabled||page.loading}/><TreeGroupTagButton showLabel label="Tag This Epoch" count={1} disabled={disabled||page.loading} onClick={event=>onTagEpoch(epoch,event)}/></>}
      {onToggleInclusion&&<EpochInclusionToggle incoming={!!source.readContext} epoch={epoch} label={`${datedCellLabel(cell,true)} epoch ${offset+index+1}`} disabled={disabled||page.loading} onToggle={onToggleInclusion}/>}
    </div>;})}
    {more&&(expanded||offset<restoreOffset||reveal)?<MemoCellEpochPage rowRegistry={rowRegistry} highlightedEpochs={highlightedEpochs} cell={cell} offset={offset+pageSize} restoreOffset={restoreOffset} onFrontier={onFrontier} expected={expected??receipt} onFault={onFault} revealEpoch={reveal?revealEpoch:null} seen={childSeen} source={source} revision={revision} pageReads={pageReads} focused={focused} onFocus={onFocus} targets={targets} onSelect={onSelect} disabled={disabled} navigationDisabled={navigationDisabled} onToggleInclusion={onToggleInclusion} inclusionForEpoch={inclusionForEpoch} setTargets={setTargets} onTagEpoch={onTagEpoch}/>:more&&<button ref={tail} className="epoch-load-more" disabled={navigationDisabled} onFocus={()=>{if(!navigationDisabled)setExpanded(true);}} onClick={()=>setExpanded(true)}>Load more epochs</button>}

  </>;
  if(source.readContext?.cohort_key)return <div data-inspection-page-ready={ready}><StableContent loading={page.loading} error={page.error} data={page.data} scope={JSON.stringify([frozenPresentationScope(source.readContext,source.protocolId,source.query),cell.cell_uuid,offset])} retry={page.reload} label="Refreshing incoming epoch list">{content}</StableContent></div>;
  return <div data-inspection-page-ready={ready}><Status {...page} retry={page.reload}>{content}</Status></div>;
}
const MemoCellEpochPage=memo(CellEpochPage);
function CellEpochs({offset,onFrontier,...props}){
  const [fault,setFault]=useState(null),[attempt,setAttempt]=useState(0),[frontier,setFrontier]=useState(-1);
  const restoredOffset=useRef(offset);
  const loaded=value=>{setFrontier(old=>Math.max(old,value));onFrontier(value);};
  if(fault)return <div data-inspection-page-ready={false} role="alert">{fault} <button onClick={()=>{setFault(null);setAttempt(value=>value+1);setFrontier(-1);}}>Reload epochs</button></div>;
  return <div data-inspection-page-ready={frontier>=restoredOffset.current}><MemoCellEpochPage key={attempt} {...props} offset={0} restoreOffset={restoredOffset.current} expected={null} onFault={setFault} onFrontier={loaded}/></div>;
}
function CellBranch({cell,dateOpen,onSelectCell,onSelectGroupCell,onTagCell,selectedCell,navigation,changeNavigation,rememberFrontier,liveTree,rowRegistries,...props}){
  const pageSize=useWorkspaceRequestScope()?.pageSize??60;
  const open=navigation.cells.includes(cell.cell_uuid);
  const setOpen=value=>{if(value!==open)changeNavigation(old=>({...old,cells:toggleInspectionBranch(old.cells,cell.cell_uuid,value)}));};
  const offset=inspectionPageOffset(navigation.offsets[cell.cell_uuid],cell.epochs,pageSize);
  const onFrontier=useMemo(()=>value=>rememberFrontier(cell.cell_uuid,value),[rememberFrontier,cell.cell_uuid]);
  const rowRegistry=rowRegistries(cell.cell_uuid);
  const tags=props.source.readContext?incomingRowAnnotation(cell,'cell'):undefined;
  return <details className={tags?'cell-tree-cell has-shared-tags':'cell-tree-cell'} open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary className={selectedCell===cell.cell_uuid?'selected-cell':''} onClick={event=>{
      // Clicking a cell targets the cell for tags (epochs target epochs); the row still opens/closes.
      // Browsing never replaces an inspected epoch from another cell.
      if(event.target.closest('button,input')||selectedCell===cell.cell_uuid)return;
      // Read live focus: a memoized branch can skip renders for unrelated focus.
      const {focusedCell,onTargetCell}=liveTree.current;
      if(!props.browseOnly||!focusedCell)onSelectCell?.(cell);else if(focusedCell===cell.cell_uuid)onTargetCell?.(cell);}} aria-label={datedCellLabel(cell,true)} aria-description={tags} title={[cell.identity_qualifier&&cell.cell_uuid,tags].filter(Boolean).join('\n')||undefined}><strong>{cell.label||cell.cell_label||'Unlabeled cell'}</strong>{cell.identity_qualifier&&<span> · {cell.identity_qualifier}</span>}{props.source.readContext&&!props.browseOnly&&<TreeGroupTagButton label="Tag This Cell" count={cell.epochs} disabled={props.disabled} onSelect={event=>onSelectGroupCell(cell,event)} onClick={event=>onTagCell(cell,event)}/>}</summary>
    {dateOpen&&open&&<CellEpochs key={props.source.readContext?.cohort_key?frozenPresentationScope(props.source.readContext,props.source.protocolId,props.source.query):JSON.stringify([props.source,props.revision,cell.cell_uuid,cell.epochs])} cell={cell} offset={offset} onFrontier={onFrontier} rowRegistry={rowRegistry} {...props}/>}
  </details>;
}
// A branch re-renders for focus/selection/highlight changes only when they
// touch its loaded rows (or its own cell); every other prop compares exactly.
function changedIds(previous=NO_IDS,next=NO_IDS,rows){
  if(previous===next)return false;
  const before=new Set(previous),after=new Set(next);
  for(const id of before)if(!after.has(id)&&rows.has(id))return true;
  for(const id of after)if(!before.has(id)&&rows.has(id))return true;
  return false;
}
function sameCellBranch(previous,next){
  const rows=next.rowRegistries(next.cell.cell_uuid),own=next.cell.cell_uuid;
  for(const key of new Set([...Object.keys(previous),...Object.keys(next)])){
    const a=previous[key],b=next[key];
    if(a===b)continue;
    if(key==='focused'){if(rows.has(a)||rows.has(b))return false;continue;}
    if(key==='focusedCell'){if(a===own||b===own)return false;continue;}
    if(key==='selectedCell'){if(a===own||b===own)return false;continue;}
    if(key==='revealEpoch'){if(a?.cell_uuid===own||b?.cell_uuid===own)return false;continue;}
    if(key==='targets'||key==='highlightedEpochs'){if(!a!==!b||changedIds(a,b,rows))return false;continue;}
    if(key==='navigation'){if(a.cells.includes(own)!==b.cells.includes(own)||a.offsets[own]!==b.offsets[own])return false;continue;}
    return false;
  }
  return true;
}
const MemoCellBranch=memo(CellBranch,sameCellBranch);
function DateBranch({group,navigation,changeNavigation,...props}){
  const open=navigation.dates.includes(group.date);
  const setOpen=value=>{if(value!==open)changeNavigation(old=>({...old,dates:toggleInspectionBranch(old.dates,group.date,value)}));};
  return <details className="cell-tree-date" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><strong>{group.date}</strong></summary>
    {group.cells.map(cell=><MemoCellBranch navigation={navigation} changeNavigation={changeNavigation} key={cell.cell_uuid} cell={cell} dateOpen={open} {...props}/>)}
  </details>;
}
const MemoDateBranch=memo(DateBranch);
export default function InspectionCellTree({cells,targets,setTargets,disabled,navigationDisabled=disabled,onFocus,onSelectCell,navigationScope,initialNavigation,onNavigationChange,membershipReady=true,navigationRequest=0,collapseRequest,cellsMore=null,...props}){
  const api=useWorkspaceRequest(defaultApi),requestScope=useWorkspaceRequestScope(),pageSize=requestScope?.pageSize??60;
  const source={...props.source,pageSize};
  const sourceIdentity=JSON.stringify(props.source);
  const stableSource=useMemo(()=>props.source,[sourceIdentity]);
  const liveTree=useRef({});
  const registries=useRef(new Map());
  const rowRegistries=useMemo(()=>cellUuid=>{let rows=registries.current.get(cellUuid);if(!rows){rows=new Set();registries.current.set(cellUuid,rows);}return rows;},[]);
  const pageReadScope=JSON.stringify([source,props.revision]);
  // Loaded-row registries only narrow re-renders; a new read scope starts empty.
  useMemo(()=>registries.current.clear(),[pageReadScope]);
  const pageReads=useMemo(()=>createEpochPageReads(api),[pageReadScope,api,requestScope]);
  const groupTags=useTreeGroupTags({readContext:props.source.readContext,protocolId:props.source.protocolId,filters:{},revision:props.revision,actionsDisabled:disabled,onAnnotationsChanged:props.onAnnotationsChanged});
  const dates=useMemo(()=>inspectionDates(cells),[cells]);
  const ordered=useMemo(()=>dates.flatMap(group=>group.cells),[dates]);
  const viewScope=navigationScope||JSON.stringify([props.source.kind,props.source.protocolId,props.source.query,props.source.readContext]);
  const [savedNavigation,setNavigation]=useState(()=>inspectionNavigation(initialNavigation,viewScope,pageSize));
  const navigation=savedNavigation.scope===viewScope?savedNavigation:inspectionNavigation(null,viewScope,pageSize);
  const navigationRef=useRef(navigation),viewCallbacks=useRef(null),treeElement=useRef(null),cancelScroll=useRef(null);
  const pendingScroll=useRef(initialNavigation?.scope===viewScope?navigation.scrollTop:null);
  const freshMembership=useRef(membershipReady);
  useLayoutEffect(()=>{navigationRef.current=navigation;freshMembership.current=membershipReady;viewCallbacks.current=onNavigationChange;});
  const rememberNavigation=value=>{navigationRef.current=value;setNavigation(value);viewCallbacks.current?.(value);};
  function rememberFrontier(cell,value){const old=navigationRef.current;if(value<=(old.offsets[cell]??-1))return;rememberNavigation({...old,offsets:{...old.offsets,[cell]:value}});}
  function cancelRestore(){cancelScroll.current?.();cancelScroll.current=null;pendingScroll.current=null;}
  function changeNavigation(update){cancelRestore();rememberNavigation(inspectionNavigation(update(navigationRef.current),viewScope,pageSize));}
  const intent=JSON.stringify([navigationRequest,props.focused]);
  const previousIntent=useRef(intent);
  useLayoutEffect(()=>{if(previousIntent.current!==intent){previousIntent.current=intent;cancelRestore();}},[intent]);
  const previousViewScope=useRef(viewScope),previousCollapse=useRef(collapseRequest);
  useLayoutEffect(()=>{
    if(previousViewScope.current!==viewScope){previousViewScope.current=viewScope;cancelRestore();rememberNavigation(inspectionNavigation(null,viewScope,pageSize));}
    if(previousCollapse.current!==collapseRequest){previousCollapse.current=collapseRequest;changeNavigation(old=>({...old,dates:[],cells:[],offsets:{},scrollTop:0}));}
  },[viewScope,collapseRequest]);
  useEffect(()=>{
    const pane=treeElement.current?.closest('.tree-scroll');if(!pane)return;
    // Activity reconnects the same DOM, but fresh page reads can temporarily
    // shrink its scroll range. Restore the last user position after ready pages.
    if(pendingScroll.current===null&&navigationRef.current.scope===viewScope&&navigationRef.current.scrollTop>0)pendingScroll.current=navigationRef.current.scrollTop;
    const saveScroll=()=>{if(pendingScroll.current===null&&freshMembership.current){const value={...navigationRef.current,scrollTop:pane.scrollTop};rememberNavigation(value);}};
    const userIntent=()=>{cancelRestore();};
    pane.addEventListener('scroll',saveScroll);
    for(const name of ['wheel','touchstart','pointerdown','keydown'])pane.addEventListener(name,userIntent);
    if(pendingScroll.current!==null)cancelScroll.current=restoreInspectionScroll({pane,top:pendingScroll.current,
      ready:()=>freshMembership.current&&!treeElement.current?.querySelector('[data-inspection-page-ready="false"]'),
      onRestored:top=>{pendingScroll.current=null;const value={...navigationRef.current,scrollTop:top};rememberNavigation(value);}});
    return()=>{cancelScroll.current?.();pane.removeEventListener('scroll',saveScroll);for(const name of ['wheel','touchstart','pointerdown','keydown'])pane.removeEventListener(name,userIntent);};
  },[viewScope]);
  useEffect(()=>{if(membershipReady)onNavigationChange?.(navigationRef.current);},[membershipReady,onNavigationChange]);

  const anchor=useRef(null),request=useRef(null),generation=useRef(0),committedScope=useRef(null),callbacks=useRef(null);
  const [selecting,setSelecting]=useState(false),[error,setError]=useState('');
  const scope=JSON.stringify({source:props.source,revision:props.revision,disabled:!!disabled,navigationDisabled:!!navigationDisabled,
    cells:ordered.map(cell=>[cell.cell_uuid,cell.epochs])});
  // Forwarders are fenced to the selection scope that created them: a handler
  // from an older scope stays inert, as before; same-scope calls use the latest
  // render, so memoized branches keep exact behavior without re-rendering.
  const actions=useMemo(()=>{const call=name=>(...args)=>liveTree.current.scope===scope?liveTree.current[name]?.(...args):undefined;return {onSelect:call('select'),onSelectCell:call('selectCell'),onSelectGroupCell:call('selectGroupCell'),
    onTagCell:(cell,event)=>liveTree.current.scope===scope?liveTree.current.selectCell(cell,event,true):undefined,changeNavigation:call('changeNavigation'),rememberFrontier:call('rememberFrontier'),onFocus:call('onFocus'),
    setTargets:call('setTargets'),onTagEpoch:call('openEpoch'),onToggleInclusion:call('onToggleInclusion'),onTargetCell:call('onTargetCell')};},[scope]);
  useLayoutEffect(()=>{callbacks.current={targets,setTargets,onFocus,onSelectCell,highlightedEpochs:props.highlightedEpochs,setHighlightedEpochs:props.setHighlightedEpochs};});
  useLayoutEffect(()=>{
    committedScope.current=scope;generation.current++;anchor.current=null;
    request.current?.abort();setSelecting(false);setError('');
    return()=>{generation.current++;committedScope.current=null;request.current?.abort();};
  },[scope]);

  async function selectCell(cell,event=null,tag=false){
    event?.preventDefault();event?.stopPropagation();
    if(navigationDisabled||committedScope.current!==scope)return;
    anchor.current=null;setError('');setSelecting(true);
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const token=generation.current,isCurrent=()=>token===generation.current&&request.current===controller&&!controller.signal.aborted;
    try{
      const {path,options}=epochPageRequest(source,{cellUuid:cell.cell_uuid,offset:0});
      const page=await pageReads.load(path,{...options,signal:controller.signal});
      if(!isCurrent())return;
      epochPageRevision(props.source,page);
      if(page.epochs?.[0]){
        if(page.offset!==0||page.epochs[0].cell_uuid!==cell.cell_uuid||typeof page.epochs[0].epoch_uuid!=='string'||!page.epochs[0].epoch_uuid)throw new Error('Cell epoch ownership changed. Refresh and select again.');
        if(tag)groupTags.openEpoch(page.epochs[0],event,true,{source:props.source,cells:ordered});else callbacks.current.onSelectCell?.(cell,page.epochs[0]);
      }
    }catch(error){if(isCurrent()&&error.name!=='AbortError')setError(error.message);}
    finally{if(isCurrent())setSelecting(false);}
  }
  async function selectGroupCell(cell,event){
    event.preventDefault();event.stopPropagation();
    if(disabled||committedScope.current!==scope)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const token=generation.current,before=JSON.stringify(callbacks.current.targets),isCurrent=()=>token===generation.current&&request.current===controller&&!controller.signal.aborted;
    setSelecting(true);setError('');
    try{
      const ids=await loadIncomingSelection({source:props.source,cells:ordered,cellUuid:cell.cell_uuid,request:api,signal:controller.signal,isCurrent});
      if(!isCurrent())return;
      if(JSON.stringify(callbacks.current.targets)!==before)throw Error('Selection changed while loading. Select this cell again.');
      callbacks.current.setTargets(mergeEpochSelection(callbacks.current.targets,ids,props.source.readContext?.selection_manifests?Infinity:1000));
    }catch(error){if(isCurrent())setError(error.message);}
    finally{if(isCurrent())setSelecting(false);}
  }
  const gestures=()=>({ids:callbacks.current.setHighlightedEpochs?callbacks.current.highlightedEpochs||[]:callbacks.current.targets,set:callbacks.current.setHighlightedEpochs||callbacks.current.setTargets});
  async function select(event,target,epoch,page,explicit=false){
    if(navigationDisabled||committedScope.current!==scope)return;
    const shift=event.shiftKey,multiple=event.metaKey||event.ctrlKey;
    if(disabled&&(explicit||shift||multiple))return;
    request.current?.abort();request.current=null;setSelecting(false);setError('');
    const selection=()=>explicit?{ids:callbacks.current.targets,set:callbacks.current.setTargets}:gestures();
    const token=generation.current;let controller;
    const isCurrent=()=>token===generation.current&&(!controller||(request.current===controller&&!controller.signal.aborted));
    try{
      target={...target,explicit,revision:epochPageRevision(props.source,page)};
      if(!epoch?.epoch_uuid||epoch.epoch_uuid!==target.uuid||epoch.cell_uuid!==target.cellUuid)throw new Error('Epoch selection ownership changed. Refresh and select again.');
      if(!explicit)callbacks.current.onFocus?.(target.uuid,epoch,page);
      if(!explicit&&!multiple&&!shift){if(callbacks.current.setHighlightedEpochs)callbacks.current.setHighlightedEpochs([target.uuid]);else if(!props.source.readContext)callbacks.current.setTargets([]);}
      if(shift&&anchor.current&&anchor.current.explicit===explicit){
        controller=new AbortController();request.current=controller;setSelecting(true);
        const before=JSON.stringify(selection().ids);
        const ids=await epochSelectionRange({limit:props.source.readContext?.selection_manifests?Infinity:1000,pageSize,cells:ordered,anchor:anchor.current,target,
          pageRevision:part=>epochPageRevision(props.source,part),loadPage:async(cellUuid,offset)=>{
          if(!isCurrent())throw new DOMException('Selection changed','AbortError');
          if(cellUuid===target.cellUuid&&offset===page.offset)return page;
          const {path,options}=epochPageRequest(source,{cellUuid,offset});return api(path,{...options,signal:controller.signal});
        }});
        if(!isCurrent())return;
        if(JSON.stringify(selection().ids)!==before)throw new Error('Selection changed while loading. Select the range again.');
        const remove=explicit&&selection().ids.includes(target.uuid)?new Set(ids):null;
        selection().set(remove?selection().ids.filter(id=>!remove.has(id)):mergeEpochSelection(selection().ids,ids,props.source.readContext?.selection_manifests?Infinity:1000));
      }else{
        const previous=anchor.current;anchor.current=target;
        // Starting a ⌘/Ctrl selection keeps the epoch that was just clicked
        // (Finder-style): click 1, ⌘-click 3 → {1,3}. Workbench highlight keeps its own rules.
        const base=multiple&&!props.source.readContext&&!selection().ids.length&&previous?.uuid&&previous.explicit===explicit&&previous.uuid!==target.uuid?[previous.uuid]:selection().ids;
        if(explicit||multiple||shift)selection().set(toggleEpochSelection(base,target.uuid,props.source.readContext?.selection_manifests?Infinity:1000));
      }
    }catch(error){if(isCurrent()&&error.name!=='AbortError')setError(error.message);}
    finally{if(isCurrent())setSelecting(false);}
  }
  // Action callbacks forward to the latest render, so memoized branches keep
  // exact behavior without re-rendering. Data functions (inclusionForEpoch)
  // keep their identity so tag/curation overlays still re-render rows.
  liveTree.current={scope,select,selectCell,selectGroupCell,changeNavigation,rememberFrontier,onFocus,setTargets,openEpoch:groupTags.openEpoch,
    onToggleInclusion:props.onToggleInclusion,onTargetCell:props.onTargetCell,focusedCell:props.focusedCell};
  const stableActions={onSelect:actions.onSelect,onSelectCell:actions.onSelectCell,onSelectGroupCell:actions.onSelectGroupCell,onTagCell:actions.onTagCell,
    changeNavigation:actions.changeNavigation,rememberFrontier:actions.rememberFrontier,onFocus:onFocus?actions.onFocus:undefined,setTargets:setTargets?actions.setTargets:undefined,
    onTagEpoch:actions.onTagEpoch,onToggleInclusion:props.onToggleInclusion?actions.onToggleInclusion:undefined,onTargetCell:props.onTargetCell?actions.onTargetCell:undefined};
  return <div ref={treeElement} data-inspection-membership-ready={membershipReady} className="inspection-cell-tree" aria-label="All matching dates, cells and epochs" title={props.setHighlightedEpochs?"⌘/Ctrl-click to highlight epochs; Shift-click for a range":"⌘/Ctrl-click to select epochs; Shift-click for a range"}>{groupTags.dialog}{error&&<p role="alert">{error}</p>}{selecting&&<p role="status">Selecting epoch range…</p>}{!dates.length&&<p role="status">No epochs match the current filters.</p>}{dates.map(group=><MemoDateBranch key={group.date} group={group} {...props} {...stableActions} source={stableSource} liveTree={liveTree} rowRegistries={rowRegistries} pageReads={pageReads} navigation={navigation} targets={targets.length?targets:NO_IDS} disabled={disabled||selecting} navigationDisabled={navigationDisabled||selecting}/>)}{cellsMore&&<CellsWindow {...cellsMore}/>}</div>;

}

// A bounded cell list: the next window loads when its marker scrolls into view.
function CellsWindow({loaded,total,loading=false,error=null,onMore}){
  const marker=useRef(null),more=Number.isInteger(total)&&loaded<total;
  useEffect(()=>{
    if(!more||loading||error||typeof IntersectionObserver==='undefined'||!marker.current)return;
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))onMore();},{root:marker.current.closest('.tree-scroll'),rootMargin:'200px 0px'});
    observer.observe(marker.current);return()=>observer.disconnect();
  },[more,loading,error,loaded]);
  return <div ref={marker} className="inspection-cells-window" role="status">
    <span>{Number.isInteger(total)?`${loaded.toLocaleString()} of ${total.toLocaleString()} cells`:`${loaded.toLocaleString()} cells`}</span>
    {error?<><span role="alert">{error}</span><button onClick={onMore}>Retry</button></>:more&&<button disabled={loading} onClick={onMore}>{loading?'Loading cells…':'Load more cells'}</button>}
  </div>;
}
