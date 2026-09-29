import {NavigationLoadingProvider,NavigationLoadingNotice} from './NavigationLoading.jsx';
import StableContent from './StableContent.jsx';
import {advanceEpochIntent,epochIntentAt,epochAtIntent} from '../epochNavigationIntent.js';
import {useEffect,useRef,useState} from 'react';
import {GitBranch} from 'lucide-react';
import {useEpochResource,useEpochPrefetch,humanize} from '../api.js';
import {useEpochBrowserPage} from '../useEpochBrowserPage.js';
import {epochShortcutDirection,inspectorPaneSizes} from '../inspectorInteraction.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {Trace} from './Inspector.jsx';
import InspectionCellTree from './InspectionCellTree.jsx';
import {EpochBrowserToolbar,EpochSelectionBar,EpochNavigation,EpochListHeading} from './EpochBrowserChrome.jsx';
import PagedTree from './PagedTree.jsx';
import MetadataPanel from './MetadataPanel.jsx';
import EpochConnections from './EpochConnections.jsx';
import PaneDivider from './PaneDivider.jsx';
import {Empty} from './Common.jsx';
import './MatchingEpochs.css';
import AnnotationTags from './AnnotationTags.jsx';
import TagExchangeControls from './TagExchangeControls.jsx';

function MatchingEpochsContent({predicate,splits,preview,onRefresh,session,onSession,onTagFilter,onAnnotationsChanged,onDesign,designDisabled=false,onExport,exportDisabled=false,actions=[]}){
  const navigationIntent=useRef(null);
  const saved=useRef(session?.revision===preview.tree_revision?session:null).current;
  const [focused,setFocused]=useState(saved?.focused||null),[request,setRequest]=useState(saved?.focused?{anchorUuid:saved.focused}:{offset:0});
  const [cells,setCells]=useState(null),[targets,setTargets]=useState([]);
  const [treeOpen,setTreeOpen]=useState(saved?.treeOpen??true),[treeMode,setTreeMode]=useState(saved?.treeMode??false);
  const [metadataOpen,setMetadataOpen]=useState(()=>{try{const value=localStorage.getItem('workspace.inspector.metadata');return value===null?window.innerWidth>=1350:value==='true';}catch{return true;}});
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
  function selectEpoch(uuid){navigationIntent.current=null;setFocused(uuid);if(!page.data?.epochs.some(row=>row.epoch_uuid===uuid))setRequest({anchorUuid:uuid});}
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
  const tagEntry=detail&&<AnnotationTags epoch={detail} revision={detailRevision} disabled={!currentPage||epoch.loading} selectedEpochs={targets} focusRequest={tagFocus} epochFocusRequest={epochTagFocus} onNavigateEpoch={direction=>{move(direction);setEpochTagFocus(value=>value+1);}} onChange={annotationsChanged} onFilter={onTagFilter} tools={<TagExchangeControls epoch={detail} onChanged={annotationsChanged} disabled={!currentPage||epoch.loading}/>}/>;
  const detailLoading=!!focused&&!page.error&&!epoch.error&&!detail;
  return <section className="inspector epoch-inspector-mode matching-epochs" tabIndex={0} aria-label="Matching epoch inspection" onKeyDown={event=>{if(!focused)return;const direction=epochShortcutDirection(event);if(direction){event.preventDefault();event.stopPropagation();event.currentTarget.focus({preventScroll:true});move(direction);}}}>
    <EpochBrowserToolbar onExport={onExport} exportDisabled={exportDisabled} onBrowse={()=>{setTreeMode(false);setTreeOpen(true);}} onDesign={onDesign} designDisabled={designDisabled} onTags={openTags} metadataOpen={metadataOpen} onToggleMetadata={()=>toggleMetadata(!metadataOpen)} actions={[{label:treeOpen?'Hide epoch list':'Show epoch list',icon:GitBranch,run:()=>setTreeOpen(value=>!value)},...actions]}/>
    <EpochSelectionBar targets={targets} onTags={openTags} onClear={()=>setTargets([])} disabled={!!page.error}/>
    {annotationNotice&&<div className="matching-annotation-notice" role="status">{annotationNotice}<button onClick={onRefresh}>Refresh results</button><button aria-label="Dismiss annotation notice" onClick={()=>setAnnotationNotice('')}>×</button></div>}
    {page.error&&<div className="mx-operation-error" role="alert">{page.error}<button onClick={onRefresh}>Refresh predicate results</button></div>}
    <div ref={layout} className={`inspection-layout resizable-layout ${treeOpen?'':'without-tree'} ${metadataOpen?'metadata-open':''} ${pane.overlay?'metadata-overlay':''}`} style={{gridTemplateColumns:pane.columns,'--metadata-width':`${pane.metadata}px`}}>
      <NavigationLoadingNotice/>
      {treeOpen&&<aside className="inspection-tree"><EpochListHeading treeMode={treeMode} onTreeMode={setTreeMode}/>{treeMode?<PagedTree presentation="tree" predicate={predicate} splits={splits} revision={detailRevision} expectedRevision={preview.tree_revision} onRefreshPreview={onRefresh} selected={focused} onSelectEpoch={selectEpoch}/>:<div className="tree-scroll" aria-label="Date, cell and epoch overview"><StableContent data={cells} loading={!cells&&page.loading} error={page.error} retry={onRefresh}><InspectionCellTree cells={cells||[]} source={source} revision={annotationRevision} focused={focused} onFocus={selectEpoch} targets={targets} setTargets={setTargets} disabled={!!page.error}/></StableContent></div>}{!metadataOpen&&<StableContent className="stable-tag-dock" data={detail} loading={detailLoading} error={epoch.error} retry={epoch.reload}>{tagEntry}</StableContent>}</aside>}
      {treeOpen&&<PaneDivider label="Resize epoch tree pane" value={pane.tree} min={180} max={pane.treeMax} onChange={tree=>setSizes(old=>({...old,tree}))}/>}
      <div className="inspection-detail"><StableContent {...epoch} data={detail} blocked={!!page.error} loading={detailLoading} retry={epoch.reload}>{detail?<><div className="epoch-heading"><div><h2>{datedCellLabel(detail)}</h2><p>{humanize(detail.protocol_name?.split('.').at(-1))} · Epoch {detail.epoch_number} within block</p></div></div><EpochNavigation position={index<0?-1:offset+index} total={page.data?.total||0} loading={page.loading} onMove={move}/><Trace epoch={detail} revision={detailRevision}/>{!metadataOpen&&!treeOpen&&tagEntry}</>:<Empty title="Choose an epoch">Select an epoch from the tree to inspect its response and metadata.</Empty>}</StableContent></div>
      {metadataOpen&&<><PaneDivider label="Resize metadata pane" value={pane.metadata} min={240} max={pane.metadataMax} reverse className={pane.overlay?'metadata-overlay-divider':''} style={pane.overlay?{right:pane.metadata}:undefined} onChange={metadata=>setSizes(old=>({...old,metadata}))}/><StableContent className="stable-metadata" data={detail} blocked={!!page.error} loading={detailLoading} error={epoch.error} retry={epoch.reload}><MetadataPanel tags={tagEntry} epoch={detail} catalog={{data:preview.catalog}} onClose={()=>toggleMetadata(false)} connections={detail&&<EpochConnections epoch={detail} protocolName={humanize(detail.protocol_name)} contextLabel="Acquisition protocol"/>}/></StableContent></>}
    </div>
  </section>;
}
export default function MatchingEpochs(props){return <NavigationLoadingProvider><MatchingEpochsContent {...props}/></NavigationLoadingProvider>;}
