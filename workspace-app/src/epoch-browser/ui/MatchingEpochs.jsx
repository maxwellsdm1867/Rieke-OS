import {predicateIdentity} from '../../typed-query/predicateIdentity.js';
import {normalizeTraceViewPreference} from '../../traces/traceViewPreference.jsx';
import EpochViewer from './EpochViewer.jsx';
import {NavigationLoadingProvider} from '../../components/NavigationLoading.jsx';
import {advanceEpochIntent,epochIntentAt,epochAtIntent} from '../epochNavigationIntent.js';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {tagStore} from '../../annotations/tagStore.js';
import {useDeferredTagVersion} from '../../annotations/useTagStore.js';
import {GitBranch,ListFilter} from 'lucide-react';
import {useEpochPrefetch,humanize} from '../../api.js';
import {useEpochInspection} from '../useEpochInspection.js';
import {epochPrefetchPaths,wholeTracePrefetchPath} from '../../resourceCache.js';
import {useEpochBrowserPage} from '../useEpochBrowserPage.js';
import {epochPageRequest,epochPageRevision} from '../epochBrowserSource.js';
import {pendingCountsRequest} from '../queryCounts.js';
import {useQueryCounts} from '../useQueryCounts.js';
import {api} from '../../api.js';
import {epochShortcutDirection,inspectorPaneSizes} from '../inspectorInteraction.js';
import EpochConnections from './EpochConnections.jsx';
import './MatchingEpochs.css';

// The cell list arrives in bounded windows; later windows load on scroll.
const CELL_WINDOW=200;
import AnnotationTags from '../../annotations/ui/AnnotationTags.jsx';
import TagExchangeControls from '../../annotations/ui/TagExchangeControls.jsx';

function MatchingEpochsContent({projectId=null,designMode=false,builder=null,columnTree=null,toolbarTarget=null,viewFilters,onViewFilters,filterRevision,filterDisabled=false,predicate,splits,preview,onRefresh,session,onSession,tracePreference:providedTracePreference,onTracePreference,onTagFilter,onAnnotationsChanged,onDesign,designDisabled=false,onExport,exportDisabled=false,actions=[],inclusionForEpoch,onToggleInclusion,onQC}){
  const [localTracePreference,setLocalTracePreference]=useState(()=>normalizeTraceViewPreference(session?.tracePreference));
  const tracePreference=providedTracePreference??localTracePreference;
  const setTracePreference=onTracePreference??setLocalTracePreference;
  const navigationIntent=useRef(null);
  const saved=useRef(session?.revision===preview.tree_revision?session:null).current;
  const [focused,setFocused]=useState(saved?.focused||null),[request,setRequest]=useState(saved?.focused?{anchorUuid:saved.focused}:{offset:0});
  const [cells,setCells]=useState(null),[targets,setTargets]=useState(saved?.targets||[]);
  const [listNavigation,setListNavigation]=useState(saved?.listNavigation||null);
  const listScope=predicateIdentity([projectId,predicate,splits,preview.tree_revision]);
  const [annotationDrafts,setAnnotationDrafts]=useState(session?.annotationDrafts||{});
  const rememberAnnotationDraft=useCallback((key,value)=>setAnnotationDrafts(previous=>{if(previous[key]===value)return previous;const next={...previous};if(value)next[key]=value;else delete next[key];return next;}),[]);
  const [collapseRequest,setCollapseRequest]=useState(0);
  const [treeOpen,setTreeOpen]=useState(saved?.treeOpen??true),[treeMode,setTreeMode]=useState(saved?.treeMode??false);
  const [metadataOpen,setMetadataOpen]=useState(()=>{try{const value=localStorage.getItem('workspace.inspector.metadata');return value===null?window.innerWidth>=1350:value==='true';}catch{return true;}});
  const [cellTagRequest,setCellTagRequest]=useState(null);
  const [tagFocus,setTagFocus]=useState(0),[epochTagFocus,setEpochTagFocus]=useState(0),[annotationRevision,setAnnotationRevision]=useState(0),[annotationNotice,setAnnotationNotice]=useState('');
  const tagVersion=useDeferredTagVersion();
  const [width,setWidth]=useState(1200),[sizes,setSizes]=useState({});
  const layout=useRef(null),callbacks=useRef({onSession});callbacks.current={onSession};
  const pane=inspectorPaneSizes(width,sizes,treeOpen,!designMode&&metadataOpen);
  const source={kind:'predicate',predicate,splits,treeRevision:preview.tree_revision};
  // Multi-field queries answer before exact counts exist. The explorer polls the
  // run's counts job; a page naming a different job is polled here. Once counts
  // are ready the first page is read again with exact totals and cells.
  const [countsRead,setCountsRead]=useState(null);
  const ownCountsJob=useQueryCounts(countsRead&&countsRead!==preview.counts?.request_id?countsRead:null);
  const countsKey=preview.counts?.status==='ready'?`counted:${preview.counts.request_id}`:ownCountsJob.status==='ready'?`counted:${countsRead}`:'';
  const page=useEpochBrowserPage(source,{...request,includeCells:true,cellsLimit:CELL_WINDOW},countsKey);
  const [cellWindow,setCellWindow]=useState({total:null,next:null,loading:false,error:null});
  const cellScope=useRef(null);cellScope.current=JSON.stringify([listScope,countsKey]);
  const currentPage=!!page.data&&!page.loading&&!page.error;
  const offset=page.data?.offset??request.offset??0;
  useEffect(()=>{const observer=new ResizeObserver(entries=>setWidth(entries[0].contentRect.width));if(layout.current)observer.observe(layout.current);return()=>observer.disconnect();},[]);
  useEffect(()=>{
    if(!currentPage)return;
    setCountsRead(pendingCountsRequest(page.data));
    if(page.data.cells){setCells(page.data.cells);setCellWindow({total:page.data.cells_total??page.data.cells.length,next:page.data.cells_next??null,loading:false,error:null});}
    const target=navigationIntent.current&&epochIntentAt(navigationIntent.current.index,page.data.total);
    if(target){navigationIntent.current=target;const uuid=epochAtIntent(page.data,target);if(uuid)setFocused(uuid);else setRequest({offset:target.offset});}
  },[page.data,currentPage]);
  useEffect(()=>{callbacks.current.onSession?.({tracePreference,revision:preview.tree_revision,offset,focused,treeOpen,treeMode,targets,listNavigation,annotationDrafts});},[tracePreference,preview.tree_revision,offset,focused,treeOpen,treeMode,targets,listNavigation,annotationDrafts]);
  const inPage=currentPage&&page.data.epochs.some(row=>row.epoch_uuid===focused);
  const detailRevision=`${preview.tree_revision}:${annotationRevision}`;
  // Recorded samples follow the result revision only: tag changes re-read the
  // epoch detail (tags live there), never trace samples. Source hash, stream,
  // rate, units and count are still checked on every warm or retained trace.
  const traceRevision=preview.tree_revision;
  const inspection=useEpochInspection({focused,path:inPage?`/epochs/${focused}`:null,row:inPage?page.data.epochs.find(row=>row.epoch_uuid===focused):null,scope:JSON.stringify([source,filterRevision]),revision:detailRevision,reloadRow:page.reload});
  const epoch=inspection.resource,detail=useMemo(()=>inPage&&epoch.data?.epoch_uuid===focused?tagStore.apply(epoch.data):null,[inPage,epoch.data,focused,tagVersion]);
  const index=page.data?.epochs.findIndex(row=>row.epoch_uuid===focused)??-1;
  useEpochPrefetch(inPage&&!epoch.loading&&index>=0?epochPrefetchPaths(page.data.epochs,index,wholeTracePrefetchPath,{progressive:true}):[],traceRevision,180,{traces:true,traceOnly:true,progressive:true,concurrency:2});
  function selectEpoch(uuid){setCellTagRequest(null);toggleMetadata(true);navigationIntent.current=null;setFocused(uuid);if(!page.data?.epochs.some(row=>row.epoch_uuid===uuid))setRequest({anchorUuid:uuid});}
  function move(direction){
    const next=advanceEpochIntent({page:currentPage?page.data:null,focused,intent:navigationIntent.current,direction});
    if(!next)return;
    navigationIntent.current=next;
    const uuid=currentPage&&epochAtIntent(page.data,next);
    if(uuid)setFocused(uuid);else setRequest({offset:next.offset});
  }
  async function loadMoreCells(){
    const after=cellWindow.next,scope=cellScope.current;
    if(!after||cellWindow.loading)return;
    setCellWindow(old=>({...old,loading:true,error:null}));
    try{
      const {path,options}=epochPageRequest(source,{offset:0,includeCells:true,cellsLimit:CELL_WINDOW,cellsAfter:after});
      const data=await api(path,options);
      if(cellScope.current!==scope)return;
      epochPageRevision(source,data);
      if(!Array.isArray(data.cells))throw Error('The next cells could not be loaded. Refresh results.');
      setCells(old=>{const seen=new Set((old||[]).map(cell=>cell.cell_uuid));return [...(old||[]),...data.cells.filter(cell=>!seen.has(cell.cell_uuid))];});
      setCellWindow({total:data.cells_total??null,next:data.cells_next??null,loading:false,error:null});
    }catch(error){if(cellScope.current===scope)setCellWindow(old=>({...old,loading:false,error:error.message}));}
  }
  const cellsPending=currentPage&&page.data.cells_pending===true;
  const pendingList=cellsPending&&<div className="pending-epoch-rows" aria-label="Matching epochs (counting cells)">
    <p role="status">Counting matching epochs and cells…</p>
    {page.data.epochs.map(row=><button key={row.epoch_uuid} aria-current={focused===row.epoch_uuid?'true':undefined} onClick={()=>selectEpoch(row.epoch_uuid)}><strong>{row.cell_label||'Cell'}</strong><time>{row.start_time?.split(/[T ]/)[1]?.slice(0,8)||'—'}</time></button>)}
    {page.data.has_more&&<p>More epochs follow; the full list appears when counting finishes.</p>}
  </div>;
  function toggleMetadata(value){setMetadataOpen(value);try{localStorage.setItem('workspace.inspector.metadata',String(value));}catch{}}
  function openTags(){if(!focused&&targets.length)selectEpoch(targets[0]);toggleMetadata(true);setTagFocus(value=>value+1);}
  function annotationsChanged(result,confirmed){if(!confirmed){epoch.reload();setAnnotationRevision(value=>value+1);}setAnnotationNotice(onAnnotationsChanged?'':'Tags saved. Refresh predicate results to re-evaluate tag conditions.');onAnnotationsChanged?.(result,confirmed);}
  const tagEntry=detail&&<AnnotationTags reconcileReceipt refreshWithEpoch composer={{values:annotationDrafts,onChange:rememberAnnotationDraft}} epoch={detail} revision={detailRevision} disabled={!currentPage||epoch.loading} selectedEpochs={targets} focusRequest={tagFocus} targetScope={cellTagRequest?'cell':targets.length?'selected':'epoch'} epochFocusRequest={epochTagFocus} onNavigateEpoch={direction=>{move(direction);setEpochTagFocus(value=>value+1);}} onChange={annotationsChanged} onFilter={onTagFilter} tools={!cellTagRequest&&!targets.length&&<TagExchangeControls epoch={detail} onChanged={annotationsChanged} disabled={!currentPage||epoch.loading}/>}/>;
  const detailLoading=!!focused&&!page.error&&!epoch.error&&!detail;
  return <EpochViewer tracePreference={tracePreference} onTracePreference={setTracePreference} designMode={designMode} builder={builder} columnTree={designMode?{...columnTree,onAnnotationsChanged:annotationsChanged,actionsDisabled:filterDisabled,inclusionForEpoch,onToggleInclusion,cells,selectedEpochs:targets,setSelectedEpochs:setTargets,selected:focused,onSelectEpoch:selectEpoch}:null} viewFilters={viewFilters} onViewFilters={onViewFilters} filterRevision={filterRevision} filterDisabled={filterDisabled} className={designMode?'tree-design matching-epochs':'epoch-inspector-mode matching-epochs'} ariaLabel="Matching epoch inspection" onKeyDown={event=>{if(designMode||!focused)return;const direction=epochShortcutDirection(event);if(direction){event.preventDefault();event.stopPropagation();event.currentTarget.focus({preventScroll:true});move(direction);}}}
    toolbar={{designMode,portalTarget:toolbarTarget,treeControlsInPane:true,onExport:onExport,exportDisabled:exportDisabled,onBrowse:()=>{setTreeMode(false);setTreeOpen(true);columnTree?.onBrowse?.();},onDesign:onDesign,designDisabled:designDisabled,onTags:openTags,metadataOpen:metadataOpen,onToggleMetadata:()=>toggleMetadata(!metadataOpen),actions:[{label:treeOpen?'Hide epoch list':'Show epoch list',icon:GitBranch,run:()=>setTreeOpen(value=>!value)},...actions]}} before={<>

    {annotationNotice&&<div className="matching-annotation-notice" role="status">{annotationNotice}<button onClick={onRefresh}>Refresh results</button><button aria-label="Dismiss annotation notice" onClick={()=>setAnnotationNotice('')}>×</button></div>}
    {page.error&&<div className="mx-operation-error" role="alert">{page.error}<button onClick={onRefresh}>Refresh predicate results</button></div>}
</>}
    layout={{layoutRef:layout,sizes:pane,treeOpen,metadataOpen,onResize:(name,value)=>setSizes(old=>({...old,[name]:value}))}}
    treePane={{treeMode:treeMode,onTreeMode:value=>{setTreeMode(value);if(value)setSizes(old=>({...old,tree:Math.max(420,pane.tree)}));},onDesign:onDesign,designDisabled:designDisabled,collapseRequest:collapseRequest,onCollapse:()=>setCollapseRequest(value=>value+1),treeProps:{onAnnotationsChanged:annotationsChanged,actionsDisabled:filterDisabled,inclusionForEpoch,onToggleInclusion,cells,selectedEpochs:targets,setSelectedEpochs:setTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{selectEpoch(epoch.epoch_uuid);setTargets([]);toggleMetadata(true);setCellTagRequest((cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},predicate,splits,revision:preview.tree_revision,expectedRevision:preview.tree_revision,onRefreshPreview:onRefresh,selected:focused,onSelectEpoch:selectEpoch},listStatus:{data:cells,loading:!cells&&page.loading,error:page.error,retry:onRefresh},pendingList:pendingList||null,listProps:{cellsMore:cells&&!cellsPending&&cellWindow.total!=null?{loaded:cells.length,total:cellWindow.total,loading:cellWindow.loading,error:cellWindow.error,onMore:loadMoreCells}:null,navigationScope:listScope,initialNavigation:listNavigation,onNavigationChange:setListNavigation,revealEpoch:!page.loading&&!page.error?page.data?.epochs?.find(row=>row.epoch_uuid===focused):null,inclusionForEpoch,onToggleInclusion,cells:cells||[],source,revision:preview.tree_revision,focused:cellTagRequest?null:focused,onFocus:selectEpoch,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cell,epoch)=>{selectEpoch(epoch.epoch_uuid);setTargets([]);toggleMetadata(true);setCellTagRequest(cell);},focusedCell:detail?.cell_uuid??null,onTargetCell:cell=>{setTargets([]);toggleMetadata(true);setCellTagRequest(cell);},targets,setTargets,disabled:!!page.error||filterDisabled}}} resource={{...epoch,blocked:!!page.error,loading:detailLoading,retry:epoch.reload}}
    epoch={detail&&inclusionForEpoch?inclusionForEpoch(detail):detail} targets={targets}
    navigation={{position:index<0?-1:offset+index,total:page.data?(page.data.total??preview.matched_count??null):0,loading:page.loading,onMove:move}}
    traceRevision={traceRevision} detailDisabled={!currentPage||epoch.loading} onQC={onQC}
    inclusion={onToggleInclusion?{disabled:filterDisabled||!currentPage||epoch.loading,onToggle:onToggleInclusion}:null} tags={tagEntry}
    metadata={{loadingPolicy:inspection.metadata,selectionCell:cellTagRequest,selectedEpochs:targets,onClearSelection:()=>setTargets([]),catalog:{data:preview.catalog},onClose:()=>toggleMetadata(false),connections:inspection.metadata.values.data&&<EpochConnections epoch={inspection.metadata.values.data} protocolName={humanize(detail.protocol_name)} contextLabel="Acquisition protocol"/>}}/>;
}
export default function MatchingEpochs(props){return <NavigationLoadingProvider><MatchingEpochsContent {...props}/></NavigationLoadingProvider>;}
