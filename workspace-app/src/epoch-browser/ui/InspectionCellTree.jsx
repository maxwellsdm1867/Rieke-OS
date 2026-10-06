import {useWorkspaceRequest,useWorkspaceRequestScope} from '../../workspaceRequest.js';
import {IncomingEpochSelect} from '../../incoming-workbench/ui/IncomingTreeSelection.jsx';
import {TreeGroupTagButton,useTreeGroupTags} from '../../annotations/ui/TreeGroupTags.jsx';
import {loadIncomingSelection} from '../../incoming-workbench/incomingSelection.js';
import {frozenPresentationScope} from '../frozenReadContext.js';
import StableContent from '../../components/StableContent.jsx';
import {epochIncluded} from '../../incoming-workbench/incomingReviewDecision.js';
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
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

function CellEpochPage({highlightedEpochs,cell,offset,restoreOffset,onFrontier,expected,onFault,revealEpoch,seen=[],source,revision,pageReads,focused,onFocus,targets,onSelect,disabled,navigationDisabled=disabled,onToggleInclusion,inclusionForEpoch,setTargets,onTagEpoch}){
  const pageSize=useWorkspaceRequestScope()?.pageSize??60;
  const page=useEpochBrowserPage(source,{cellUuid:cell.cell_uuid,offset},JSON.stringify([revision,source.queryRevision,source.treeRevision]),pageReads);
  const [expanded,setExpanded]=useState(false);
  const tail=useRef(null);
  let receipt=null,problem=null;
  if(page.data){
    try{
      const data=page.data,rows=data.epochs;
      receipt=JSON.stringify([epochPageRevision(source,data),data.total,data.expected_binding_version??null]);
      if(!Number.isInteger(data.total)||data.total<0||data.offset!==offset||!Array.isArray(rows)||rows.length>pageSize||
          rows.length!==Math.min(pageSize,Math.max(0,data.total-offset))||
          rows.some(row=>!row||row.cell_uuid!==cell.cell_uuid||typeof row.epoch_uuid!=='string'||!row.epoch_uuid||seen.includes(row.epoch_uuid))||new Set(rows.map(row=>row.epoch_uuid)).size!==rows.length||
          (expected!==null&&expected!==receipt))throw Error('Epoch list changed while scrolling. Reload the list.');
    }catch(error){problem=error.message;}
  }
  useLayoutEffect(()=>{if(problem)onFault(problem);else if(page.data&&!page.loading&&!page.error)onFrontier(offset);},[problem,receipt,page.loading,page.error,offset]);
  const ready=!!page.data&&!page.loading&&!page.error&&!problem;
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
    {(ready?page.data.epochs:[]).map((record,index)=>{const epoch=inclusionForEpoch?inclusionForEpoch(record):record,tags=source.readContext?incomingRowAnnotation(epoch):undefined;return <div key={epoch.epoch_uuid} className={`epoch-row cell-tree-epoch ${tags?'has-shared-tags':''} ${highlightedEpochs?.includes(epoch.epoch_uuid)?'is-highlighted':''} ${focused===epoch.epoch_uuid?'active':''} ${targets.includes(epoch.epoch_uuid)?'bulk-selected':''} ${epochIncluded(epoch,!!source.readContext)===false?'analysis-excluded':''}`}>
      <button aria-description={tags} title={tags} disabled={navigationDisabled||page.loading} aria-current={focused===epoch.epoch_uuid?'true':undefined} aria-pressed={highlightedEpochs?highlightedEpochs.includes(epoch.epoch_uuid):targets.includes(epoch.epoch_uuid)||(!source.readContext&&!targets.length&&focused===epoch.epoch_uuid)} onMouseDown={event=>{if(event.shiftKey)event.preventDefault();}} onClick={event=>onSelect(event,{cellUuid:cell.cell_uuid,index:offset+index,uuid:epoch.epoch_uuid},epoch,page.data)} aria-label={`Inspect ${datedCellLabel(cell,true)} epoch ${offset+index+1}`}>
        <strong>{offset+index+1}</strong>
        <time>{epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'—'}</time>
        <span className="epoch-short-protocol" title={humanize(epoch.protocol_name?.split('.').at(-1))}>{humanize(epoch.protocol_name?.split('.').at(-1))||'—'}</span>
      </button>
      {source.readContext&&<><IncomingEpochSelect epoch={epoch} selected={targets} onSelect={setTargets} disabled={disabled||page.loading}/><TreeGroupTagButton showLabel label="Tag This Epoch" count={1} disabled={disabled||page.loading} onClick={event=>onTagEpoch(epoch,event)}/></>}
      {onToggleInclusion&&<EpochInclusionToggle incoming={!!source.readContext} epoch={epoch} label={`${datedCellLabel(cell,true)} epoch ${offset+index+1}`} disabled={disabled||page.loading} onToggle={onToggleInclusion}/>}
    </div>;})}
    {more&&(expanded||offset<restoreOffset||reveal)?<CellEpochPage highlightedEpochs={highlightedEpochs} cell={cell} offset={offset+pageSize} restoreOffset={restoreOffset} onFrontier={onFrontier} expected={expected??receipt} onFault={onFault} revealEpoch={reveal?revealEpoch:null} seen={[...seen,...page.data.epochs.map(row=>row.epoch_uuid)]} source={source} revision={revision} pageReads={pageReads} focused={focused} onFocus={onFocus} targets={targets} onSelect={onSelect} disabled={disabled} navigationDisabled={navigationDisabled} onToggleInclusion={onToggleInclusion} inclusionForEpoch={inclusionForEpoch} setTargets={setTargets} onTagEpoch={onTagEpoch}/>:more&&<button ref={tail} className="epoch-load-more" disabled={navigationDisabled} onFocus={()=>{if(!navigationDisabled)setExpanded(true);}} onClick={()=>setExpanded(true)}>Load more epochs</button>}

  </>;
  if(source.readContext?.cohort_key)return <div data-inspection-page-ready={ready}><StableContent loading={page.loading} error={page.error} data={page.data} scope={JSON.stringify([frozenPresentationScope(source.readContext,source.protocolId,source.query),cell.cell_uuid,offset])} retry={page.reload} label="Refreshing incoming epoch list">{content}</StableContent></div>;
  return <div data-inspection-page-ready={ready}><Status {...page} retry={page.reload}>{content}</Status></div>;
}
function CellEpochs({offset,onFrontier,...props}){
  const [fault,setFault]=useState(null),[attempt,setAttempt]=useState(0),[frontier,setFrontier]=useState(-1);
  const restoredOffset=useRef(offset);
  const loaded=value=>{setFrontier(old=>Math.max(old,value));onFrontier(value);};
  if(fault)return <div data-inspection-page-ready={false} role="alert">{fault} <button onClick={()=>{setFault(null);setAttempt(value=>value+1);setFrontier(-1);}}>Reload epochs</button></div>;
  return <div data-inspection-page-ready={frontier>=restoredOffset.current}><CellEpochPage key={attempt} {...props} offset={0} restoreOffset={restoredOffset.current} expected={null} onFault={setFault} onFrontier={loaded}/></div>;
}
function CellBranch({cell,dateOpen,onSelectCell,onSelectGroupCell,onTagCell,selectedCell,navigation,changeNavigation,rememberFrontier,...props}){
  const pageSize=useWorkspaceRequestScope()?.pageSize??60;
  const open=navigation.cells.includes(cell.cell_uuid);
  const setOpen=value=>{if(value!==open)changeNavigation(old=>({...old,cells:toggleInspectionBranch(old.cells,cell.cell_uuid,value)}));};
  const offset=inspectionPageOffset(navigation.offsets[cell.cell_uuid],cell.epochs,pageSize);
  const onFrontier=value=>rememberFrontier(cell.cell_uuid,value);
  const tags=props.source.readContext?incomingRowAnnotation(cell,'cell'):undefined;
  return <details className={tags?'cell-tree-cell has-shared-tags':'cell-tree-cell'} open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary className={selectedCell===cell.cell_uuid?'selected-cell':''} aria-label={datedCellLabel(cell,true)} aria-description={tags} title={[cell.identity_qualifier&&cell.cell_uuid,tags].filter(Boolean).join('\n')||undefined} onClick={()=>onSelectCell(cell)}><strong>{cell.label||cell.cell_label||'Unlabeled cell'}</strong>{cell.identity_qualifier&&<span> · {cell.identity_qualifier}</span>}{props.source.readContext&&!props.browseOnly&&<TreeGroupTagButton label="Tag This Cell" count={cell.epochs} disabled={props.disabled} onSelect={event=>onSelectGroupCell(cell,event)} onClick={event=>onTagCell(cell,event)}/>}</summary>
    {dateOpen&&open&&<CellEpochs key={props.source.readContext?.cohort_key?frozenPresentationScope(props.source.readContext,props.source.protocolId,props.source.query):JSON.stringify([props.source,props.revision,cell.cell_uuid,cell.epochs])} cell={cell} offset={offset} onFrontier={onFrontier} {...props}/>}
  </details>;
}
function DateBranch({group,navigation,changeNavigation,...props}){
  const open=navigation.dates.includes(group.date);
  const setOpen=value=>{if(value!==open)changeNavigation(old=>({...old,dates:toggleInspectionBranch(old.dates,group.date,value)}));};
  return <details className="cell-tree-date" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><strong>{group.date}</strong></summary>
    {group.cells.map(cell=><CellBranch navigation={navigation} changeNavigation={changeNavigation} key={cell.cell_uuid} cell={cell} dateOpen={open} {...props}/>)}
  </details>;
}
export default function InspectionCellTree({cells,targets,setTargets,disabled,navigationDisabled=disabled,onFocus,onSelectCell,navigationScope,initialNavigation,onNavigationChange,membershipReady=true,navigationRequest=0,collapseRequest,...props}){
  const api=useWorkspaceRequest(defaultApi),requestScope=useWorkspaceRequestScope(),pageSize=requestScope?.pageSize??60;
  const source={...props.source,pageSize};
  const pageReadScope=JSON.stringify([source,props.revision]);
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
      callbacks.current.setTargets(mergeEpochSelection(callbacks.current.targets,ids));
    }catch(error){if(isCurrent())setError(error.message);}
    finally{if(isCurrent())setSelecting(false);}
  }
  const gestures=()=>({ids:callbacks.current.setHighlightedEpochs?callbacks.current.highlightedEpochs||[]:callbacks.current.targets,set:callbacks.current.setHighlightedEpochs||callbacks.current.setTargets});
  async function select(event,target,epoch,page){
    if(navigationDisabled||committedScope.current!==scope)return;
    const shift=event.shiftKey,multiple=event.metaKey||event.ctrlKey;
    if(disabled&&(shift||multiple))return;
    request.current?.abort();request.current=null;setSelecting(false);setError('');
    const token=generation.current;let controller;
    const isCurrent=()=>token===generation.current&&(!controller||(request.current===controller&&!controller.signal.aborted));
    try{
      target={...target,revision:epochPageRevision(props.source,page)};
      if(!epoch?.epoch_uuid||epoch.epoch_uuid!==target.uuid||epoch.cell_uuid!==target.cellUuid)throw new Error('Epoch selection ownership changed. Refresh and select again.');
      callbacks.current.onFocus?.(target.uuid,epoch);
      if(!multiple&&!shift){if(callbacks.current.setHighlightedEpochs)callbacks.current.setHighlightedEpochs([target.uuid]);else if(!props.source.readContext)callbacks.current.setTargets([]);}
      if(shift&&anchor.current){
        controller=new AbortController();request.current=controller;setSelecting(true);
        const before=JSON.stringify(gestures().ids);
        const ids=await epochSelectionRange({pageSize,cells:ordered,anchor:anchor.current,target,
          pageRevision:part=>epochPageRevision(props.source,part),loadPage:async(cellUuid,offset)=>{
          if(!isCurrent())throw new DOMException('Selection changed','AbortError');
          if(cellUuid===target.cellUuid&&offset===page.offset)return page;
          const {path,options}=epochPageRequest(source,{cellUuid,offset});return api(path,{...options,signal:controller.signal});
        }});
        if(!isCurrent())return;
        if(JSON.stringify(gestures().ids)!==before)throw new Error('Selection changed while loading. Select the range again.');
        gestures().set(mergeEpochSelection(gestures().ids,ids));
      }else{
        anchor.current=target;
        if(multiple||shift)gestures().set(toggleEpochSelection(gestures().ids,target.uuid));
      }
    }catch(error){if(isCurrent()&&error.name!=='AbortError')setError(error.message);}
    finally{if(isCurrent())setSelecting(false);}
  }
  return <div ref={treeElement} data-inspection-membership-ready={membershipReady} className="inspection-cell-tree" aria-label="All matching dates, cells and epochs" title={props.setHighlightedEpochs?"⌘/Ctrl-click to highlight epochs; Shift-click for a range":"⌘/Ctrl-click to select epochs; Shift-click for a range"}>{groupTags.dialog}{error&&<p role="alert">{error}</p>}{selecting&&<p role="status">Selecting epoch range…</p>}{!dates.length&&<p role="status">No epochs match the current filters.</p>}{dates.map(group=><DateBranch key={group.date} group={group} {...props} pageReads={pageReads} rememberFrontier={rememberFrontier} navigation={navigation} changeNavigation={changeNavigation} targets={targets} setTargets={setTargets} onTagEpoch={groupTags.openEpoch} onSelectGroupCell={selectGroupCell} onTagCell={(cell,event)=>selectCell(cell,event,true)} onFocus={onFocus} onSelectCell={selectCell} onSelect={select} disabled={disabled||selecting} navigationDisabled={navigationDisabled||selecting}/>)}</div>;
}
