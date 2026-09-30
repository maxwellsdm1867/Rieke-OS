import EpochViewer from './EpochViewer.jsx';
import {NavigationLoadingProvider} from './NavigationLoading.jsx';
import {advanceEpochIntent,epochIntentAt,epochAtIntent} from '../epochNavigationIntent.js';
import {useEffect,useRef,useState} from 'react';
import {GitBranch,ListFilter} from 'lucide-react';
import {useEpochResource,useEpochPrefetch,humanize} from '../api.js';
import {useEpochBrowserPage} from '../useEpochBrowserPage.js';
import {epochShortcutDirection,inspectorPaneSizes} from '../inspectorInteraction.js';
import EpochConnections from './EpochConnections.jsx';
import './MatchingEpochs.css';
import AnnotationTags from './AnnotationTags.jsx';
import TagExchangeControls from './TagExchangeControls.jsx';

function MatchingEpochsContent({toolbarTarget=null,viewFilters,onViewFilters,filterRevision,filterDisabled=false,predicate,splits,preview,onRefresh,session,onSession,onTagFilter,onAnnotationsChanged,onDesign,designDisabled=false,onExport,exportDisabled=false,actions=[],inclusionForEpoch,onToggleInclusion,onQC}){
  const navigationIntent=useRef(null);
  const saved=useRef(session?.revision===preview.tree_revision?session:null).current;
  const [focused,setFocused]=useState(saved?.focused||null),[request,setRequest]=useState(saved?.focused?{anchorUuid:saved.focused}:{offset:0});
  const [cells,setCells]=useState(null),[targets,setTargets]=useState([]);
  const [collapseRequest,setCollapseRequest]=useState(0);
  const [treeOpen,setTreeOpen]=useState(saved?.treeOpen??true),[treeMode,setTreeMode]=useState(saved?.treeMode??false);
  const [metadataOpen,setMetadataOpen]=useState(()=>{try{const value=localStorage.getItem('workspace.inspector.metadata');return value===null?window.innerWidth>=1350:value==='true';}catch{return true;}});
  const [cellTagRequest,setCellTagRequest]=useState(null);
  const [tagFocus,setTagFocus]=useState(0),[epochTagFocus,setEpochTagFocus]=useState(0),[annotationRevision,setAnnotationRevision]=useState(0),[annotationNotice,setAnnotationNotice]=useState('');
  const [width,setWidth]=useState(1200),[sizes,setSizes]=useState({});
  const layout=useRef(null),callbacks=useRef({onSession});callbacks.current={onSession};
  const pane=inspectorPaneSizes(width,sizes,treeOpen,metadataOpen);
  const source={kind:'predicate',predicate,splits,treeRevision:preview.tree_revision};
  const page=useEpochBrowserPage(source,{...request,includeCells:true});
  const currentPage=!!page.data&&!page.loading&&!page.error;
  const offset=page.data?.offset??request.offset??0;
  useEffect(()=>{const observer=new ResizeObserver(entries=>setWidth(entries[0].contentRect.width));if(layout.current)observer.observe(layout.current);return()=>observer.disconnect();},[]);
  useEffect(()=>{
    if(!currentPage)return;
    if(page.data.cells)setCells(page.data.cells);
    const target=navigationIntent.current&&epochIntentAt(navigationIntent.current.index,page.data.total);
    if(target){navigationIntent.current=target;const uuid=epochAtIntent(page.data,target);if(uuid)setFocused(uuid);else setRequest({offset:target.offset});}
  },[page.data,currentPage]);
  useEffect(()=>{callbacks.current.onSession?.({revision:preview.tree_revision,offset,focused,treeOpen,treeMode});},[preview.tree_revision,offset,focused,treeOpen,treeMode]);
  const inPage=currentPage&&page.data.epochs.some(row=>row.epoch_uuid===focused);
  const detailRevision=`${preview.tree_revision}:${annotationRevision}`;
  const epoch=useEpochResource(inPage?`/epochs/${focused}`:null,detailRevision,80),detail=inPage&&epoch.data?.epoch_uuid===focused?epoch.data:null;
  const index=page.data?.epochs.findIndex(row=>row.epoch_uuid===focused)??-1;
  useEpochPrefetch(inPage&&!epoch.loading&&index>=0?[page.data.epochs[index+1],page.data.epochs[index-1]].filter(Boolean).map(row=>`/epochs/${row.epoch_uuid}`):[],detailRevision);
  function selectEpoch(uuid){setCellTagRequest(null);toggleMetadata(true);navigationIntent.current=null;setFocused(uuid);if(!page.data?.epochs.some(row=>row.epoch_uuid===uuid))setRequest({anchorUuid:uuid});}
  function move(direction){
    const next=advanceEpochIntent({page:currentPage?page.data:null,focused,intent:navigationIntent.current,direction});
    if(!next)return;
    navigationIntent.current=next;
    const uuid=currentPage&&epochAtIntent(page.data,next);
    if(uuid)setFocused(uuid);else setRequest({offset:next.offset});
  }
  function toggleMetadata(value){setMetadataOpen(value);try{localStorage.setItem('workspace.inspector.metadata',String(value));}catch{}}
  function openTags(){if(!focused&&targets.length)selectEpoch(targets[0]);toggleMetadata(true);setTagFocus(value=>value+1);}
  function annotationsChanged(){epoch.reload();setAnnotationRevision(value=>value+1);setAnnotationNotice(onAnnotationsChanged?'':'Tags saved. Refresh predicate results to re-evaluate tag conditions.');onAnnotationsChanged?.();}
  const tagEntry=detail&&<AnnotationTags epoch={detail} revision={detailRevision} disabled={!currentPage||epoch.loading} selectedEpochs={targets} focusRequest={tagFocus} targetScope={cellTagRequest?'cell':targets.length?'selected':'epoch'} epochFocusRequest={epochTagFocus} onNavigateEpoch={direction=>{move(direction);setEpochTagFocus(value=>value+1);}} onChange={annotationsChanged} onFilter={onTagFilter} tools={!cellTagRequest&&!targets.length&&<TagExchangeControls epoch={detail} onChanged={annotationsChanged} disabled={!currentPage||epoch.loading}/>}/>;
  const detailLoading=!!focused&&!page.error&&!epoch.error&&!detail;
  return <EpochViewer viewFilters={viewFilters} onViewFilters={onViewFilters} filterRevision={filterRevision} filterDisabled={filterDisabled} className="epoch-inspector-mode matching-epochs" ariaLabel="Matching epoch inspection" onKeyDown={event=>{if(!focused)return;const direction=epochShortcutDirection(event);if(direction){event.preventDefault();event.stopPropagation();event.currentTarget.focus({preventScroll:true});move(direction);}}}
    toolbar={{portalTarget:toolbarTarget,treeControlsInPane:true,onExport:onExport,exportDisabled:exportDisabled,onBrowse:()=>{setTreeMode(false);setTreeOpen(true);},onDesign:onDesign,designDisabled:designDisabled,onTags:openTags,metadataOpen:metadataOpen,onToggleMetadata:()=>toggleMetadata(!metadataOpen),actions:[{label:treeOpen?'Hide epoch list':'Show epoch list',icon:GitBranch,run:()=>setTreeOpen(value=>!value)},...actions]}} before={<>

    {annotationNotice&&<div className="matching-annotation-notice" role="status">{annotationNotice}<button onClick={onRefresh}>Refresh results</button><button aria-label="Dismiss annotation notice" onClick={()=>setAnnotationNotice('')}>×</button></div>}
    {page.error&&<div className="mx-operation-error" role="alert">{page.error}<button onClick={onRefresh}>Refresh predicate results</button></div>}
</>}
    layout={{layoutRef:layout,sizes:pane,treeOpen,metadataOpen,onResize:(name,value)=>setSizes(old=>({...old,[name]:value}))}}
    treePane={{treeMode:treeMode,onTreeMode:value=>{setTreeMode(value);if(value)setSizes(old=>({...old,tree:Math.max(420,pane.tree)}));},onDesign:onDesign,designDisabled:designDisabled,collapseRequest:collapseRequest,onCollapse:()=>setCollapseRequest(value=>value+1),treeProps:{actionsDisabled:filterDisabled,inclusionForEpoch,onToggleInclusion,cells,selectedEpochs:targets,setSelectedEpochs:setTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{selectEpoch(epoch.epoch_uuid);setTargets([]);toggleMetadata(true);setCellTagRequest((cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},predicate,splits,revision:preview.tree_revision,expectedRevision:preview.tree_revision,onRefreshPreview:onRefresh,selected:focused,onSelectEpoch:selectEpoch},listStatus:{data:cells,loading:!cells&&page.loading,error:page.error,retry:onRefresh},listProps:{inclusionForEpoch,onToggleInclusion,cells:cells||[],source,revision:preview.tree_revision,focused:cellTagRequest?null:focused,onFocus:selectEpoch,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cell,epoch)=>{selectEpoch(epoch.epoch_uuid);setTargets([]);toggleMetadata(true);setCellTagRequest(cell);},targets,setTargets,disabled:!!page.error||filterDisabled}}} resource={{...epoch,blocked:!!page.error,loading:detailLoading,retry:epoch.reload}}
    epoch={detail&&inclusionForEpoch?inclusionForEpoch(detail):detail} targets={targets}
    navigation={{position:index<0?-1:offset+index,total:page.data?.total||0,loading:page.loading,onMove:move}}
    traceRevision={detailRevision} detailDisabled={!currentPage||epoch.loading} onQC={onQC}
    inclusion={onToggleInclusion?{disabled:filterDisabled||!currentPage||epoch.loading,onToggle:onToggleInclusion}:null} tags={tagEntry}
    metadata={{selectionCell:cellTagRequest,selectedEpochs:targets,onClearSelection:()=>setTargets([]),catalog:{data:preview.catalog},onClose:()=>toggleMetadata(false),connections:detail&&<EpochConnections epoch={detail} protocolName={humanize(detail.protocol_name)} contextLabel="Acquisition protocol"/>}}/>;
}
export default function MatchingEpochs(props){return <NavigationLoadingProvider><MatchingEpochsContent {...props}/></NavigationLoadingProvider>;}
