import {useTraceViewPreference} from '../../traces/traceViewPreference.jsx';
import ScientificContext from '../../components/ScientificContext.jsx';
import {frozenTreePresentationScope} from '../frozenReadContext.js';
import {useState} from 'react';
import {Activity,ArrowLeft,Tags,X,LoaderCircle,AlertTriangle} from 'lucide-react';
import {useNavigationLoading,useDelayedLoading} from '../../components/NavigationLoading.jsx';
import './EpochViewer.css';
import {EpochBrowserToolbar,EpochNavigation} from './EpochBrowserChrome.jsx';
import EpochBrowserLayout from './EpochBrowserLayout.jsx';
import EpochTreePane from './EpochTreePane.jsx';
import TreeBuilder from '../../typed-query/ui/TreeBuilder.jsx';
import RetainedTreePresentation from '../../tree-browser/ui/RetainedTreePresentation.jsx';
import StableContent from '../../components/StableContent.jsx';
import EpochDetailHeading from './EpochDetailHeading.jsx';
import EpochAnalysisInclusion from './EpochAnalysisInclusion.jsx';
import Trace from '../../traces/ui/TraceViewer.jsx';
import MetadataPanel from './MetadataPanel.jsx';
import SelectionOverview from '../../protocol-overview/ui/SelectionOverview.jsx';
import ProtocolViewFilter from '../../typed-query/ui/ProtocolViewFilter.jsx';
import {clearTagFilters,tagFilterLabel} from '../../typed-query/protocolViewFilter.js';
import {Empty} from '../../components/Common.jsx';
import {datedCellLabel} from '../../recording-import/recordingIdentity.js';
import AnnotationTags from '../../annotations/ui/AnnotationTags.jsx';
import useTreeCellSelection from '../../annotations/useTreeCellSelection.js';

// Source adapters provide data and mutations; every viewer assembles its UI here.
// Retain only the prepared empty presentation shell. The
// existing trace owner still admits and measures the first focused request.
function PreparedTraceDetail({resource,epoch,trace,heading,navigation,curation}){
  const waiting=!!resource.loading||!!resource.error||!!resource.blocked;
  const empty=!epoch||waiting;
  const coordinated=useNavigationLoading(resource.loading&&!resource.error);
  const showLoading=useDelayedLoading(resource.loading&&!coordinated);
  return <div className="stable-content prepared-trace-detail" aria-busy={!!resource.loading}>
    <div className={`stable-content-body${empty?' stable-content-placeholder prepared-trace-empty':''}`} inert={empty} aria-hidden={empty?true:undefined}>
      {!empty&&heading}
      {!empty&&navigation}
      <Trace key="prepared-recorded-trace" {...trace} resetInteractionOnEmpty epoch={empty?null:epoch}/>
      {!empty&&curation}
    </div>
    {(resource.error||showLoading)&&<div className={`stable-content-notice ${resource.error?'failed':''}`} role={resource.error?'alert':'status'}>
      {resource.error?<AlertTriangle size={15}/>:<LoaderCircle size={15}/>}
      <span>{resource.error||'Loading selected epoch'}</span>
      {resource.error&&resource.retry&&<button onClick={resource.retry}>Retry</button>}
    </div>}
  </div>;
}

export default function EpochViewer({className='epoch-inspector-mode',ariaLabel='Epoch inspection',onKeyDown,toolbar,toolbarChildren,viewFilters,onViewFilters,filterRevision,filterDisabled=false,hideFilterControl=false,before,layout,designMode=false,builder,columnTree,treePane,resource={},epoch,targets=[],navigation,traceRevision,tracePreference:providedTracePreference,onTracePreference,readContext=null,traceReadContext=undefined,traceEpoch=null,traceRequested=true,inclusion,detailDisabled=false,onQC,tags,detailExtras,metadata}){
  const [tracePreference,setTracePreference]=useTraceViewPreference(providedTracePreference,onTracePreference);
  const [previewOpen,setPreviewOpen]=useState(true);
  const [tagsOpen,setTagsOpen]=useState(false);
  const cellSelection=useTreeCellSelection(designMode&&!readContext?columnTree:null);
  const independentTrace=traceReadContext!==undefined;
  const shownEpoch=independentTrace?traceEpoch:epoch;
  const displayResource=independentTrace?{data:shownEpoch,loading:!shownEpoch&&traceRequested,scope:JSON.stringify([traceReadContext,shownEpoch?.epoch_uuid,shownEpoch?.source_sha256])}:resource;
  // Historical display can advance while mutation receipts are refreshing.
  // Never retain another epoch's tags/review beneath the new recorded trace.
  const curationScope=JSON.stringify([resource.scope,readContext,traceReadContext,shownEpoch?.epoch_uuid,shownEpoch?.source_sha256]);
  const hasPreview=!!(epoch||columnTree?.selected);
  const showPreview=designMode&&previewOpen&&hasPreview;
  const selectedPreviewProof=!columnTree?.readContext?.selection_token||typeof columnTree.readContext.selection_view_key==='string'&&!!columnTree.readContext.selection_view_key.trim();
  const frozenPreview=selectedPreviewProof&&!!columnTree?.selected&&!!frozenTreePresentationScope(columnTree)
    &&(!epoch||epoch.epoch_uuid===columnTree.selected)&&(!shownEpoch||shownEpoch.epoch_uuid===columnTree.selected);
  const previewBlocked=!!columnTree?.actionsDisabled;
  const tracePane=showPreview&&(!previewBlocked||frozenPreview)?<section className="tree-trace-pane" aria-label="Raw recording preview" inert={frozenPreview&&previewBlocked} aria-hidden={frozenPreview&&previewBlocked?true:undefined}><header><strong><Activity size={14}/> Raw recording</strong><button className="icon-button" aria-label="Close raw recording preview" onClick={()=>setPreviewOpen(false)}><X size={15}/></button></header><div className="tree-trace-body"><StableContent {...resource} data={epoch}>{epoch&&<><div className="tree-preview-identity"><strong>{datedCellLabel(epoch)}</strong><span>Epoch {epoch.epoch_number??'—'} · {epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'Time not recorded'}</span></div><Trace viewPreference={tracePreference} onViewPreference={setTracePreference} epoch={traceReadContext===null?null:shownEpoch} revision={traceRevision} readContext={traceReadContext===undefined?readContext:traceReadContext}/></>}</StableContent></div></section>:null;
  const treeTags=<div className="tree-selection-tags" hidden={!tagsOpen}>{cellSelection.cells.length?<><div className="tree-cell-selection" aria-label="Selected cells"><strong>{cellSelection.cells.length} cells selected</strong><button disabled={cellSelection.blocked} onClick={cellSelection.clear}>Clear cell selection</button><div>{cellSelection.cells.map(cell=><span key={cell.cell_uuid}>{cell.label}</span>)}</div></div><AnnotationTags composer={cellSelection.composer} selectedCells={cellSelection.ids} targetScope="selected-cells" revision={cellSelection.revision} disabled={cellSelection.blocked} reconcileReceipt onChange={columnTree?.onAnnotationsChanged}/></>:<StableContent {...resource} data={epoch}>{tags}</StableContent>}</div>;
  const curation=<><div className="curation-bar">{inclusion&&<EpochAnalysisInclusion epoch={epoch} {...inclusion}/>} {!designMode&&!layout.metadataOpen&&(!layout.treeOpen||treePane?.treeMode)&&tags}</div>
{detailExtras}</>;
  const preparedShell=!designMode&&traceReadContext?.kind==='prepared_display'&&!(!readContext&&targets.length);
  const detail=preparedShell?<PreparedTraceDetail resource={displayResource} epoch={shownEpoch}
    trace={{viewPreference:tracePreference,onViewPreference:setTracePreference,revision:traceRevision,readContext:traceReadContext}}
    heading={shownEpoch&&<EpochDetailHeading epoch={shownEpoch} disabled={detailDisabled||!epoch||resource.loading} onQC={onQC}/>}
    navigation={navigation&&<EpochNavigation {...navigation}/>}
    curation={<StableContent {...resource} scope={curationScope} data={epoch}>{curation}</StableContent>}/>:<StableContent {...displayResource} data={shownEpoch}>{!readContext&&!designMode&&targets.length?<SelectionOverview count={targets.length}/>:shownEpoch?<>
    {designMode?<div className="tree-preview-identity"><strong>{datedCellLabel(shownEpoch)}</strong><span>Epoch {shownEpoch.epoch_number??'—'} · {shownEpoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'Time not recorded'}</span></div>:<EpochDetailHeading epoch={shownEpoch} disabled={detailDisabled||!epoch||resource.loading} onQC={onQC}/>}
    {navigation&&!designMode&&<EpochNavigation {...navigation}/>}
    <Trace viewPreference={tracePreference} onViewPreference={setTracePreference} epoch={traceReadContext===null?null:shownEpoch} revision={traceRevision} readContext={traceReadContext===undefined?readContext:traceReadContext}/>
    {independentTrace?<StableContent {...resource} scope={curationScope} data={epoch}>{curation}</StableContent>:curation}
  </>:<Empty title="Choose an epoch">Select an epoch from the tree to inspect its response and metadata.</Empty>}</StableContent>;
  const valuesEpoch=metadata?.loadingPolicy?metadata.loadingPolicy.values.data:epoch;
  const metadataPanel=metadata&&<MetadataPanel {...metadata} epoch={metadata.loadingPolicy?.row||epoch} tags={tags} context={valuesEpoch&&<ScientificContext epoch={valuesEpoch}/>}/>;
  return <div className={`inspector ${className}`} tabIndex={0} aria-label={ariaLabel} onKeyDown={onKeyDown}>
    {toolbar&&<EpochBrowserToolbar {...toolbar} filterControl={hideFilterControl?null:onViewFilters?<ProtocolViewFilter filters={viewFilters} onChange={onViewFilters} revision={filterRevision} disabled={filterDisabled}/>:toolbar.filterControl} treeControlsInPane>{toolbarChildren}{!designMode&&onViewFilters&&tagFilterLabel(viewFilters)&&<span className="inspection-filter-summary">{tagFilterLabel(viewFilters)}<button disabled={filterDisabled} onClick={()=>onViewFilters(Object.fromEntries(Object.entries(clearTagFilters(viewFilters)).filter(([key])=>key!=='metadata_predicate')))}>Clear filter</button></span>}</EpochBrowserToolbar>}
    {before}
    <EpochBrowserLayout {...layout} editing={designMode} retainDetail
      tree={designMode?<><nav className="tree-design-controls" aria-label="Tree editing"><button onClick={toolbar?.onBrowse}><ArrowLeft size={15}/> Back to epochs</button>{!previewOpen&&hasPreview&&<button aria-label="Show raw recording preview" onClick={()=>setPreviewOpen(true)}><Activity size={15}/></button>}<button aria-label="Show tree selection tags" aria-expanded={tagsOpen} onClick={()=>setTagsOpen(value=>!value)}><Tags size={15}/></button></nav>{treeTags}<TreeBuilder {...builder}/>{treePane?.selectionTools}</>:<EpochTreePane {...treePane} childrenInTree={false}>{!layout.metadataOpen&&<StableContent {...resource} className="stable-tag-dock" data={epoch}>{tags}</StableContent>}</EpochTreePane>}
      detail={<><div hidden={!designMode} style={!designMode?{display:'none'}:undefined} className="tree-design-content"><RetainedTreePresentation active={designMode} tree={{...columnTree,trailingPane:tracePane,trailingPaneKey:showPreview?columnTree?.selected:null, selectedCells:cellSelection.ids,onToggleCell:readContext?undefined:(...args)=>{cellSelection.toggle(...args);setTagsOpen(true);},onStatus:value=>{cellSelection.status(value);columnTree?.onStatus?.(value);},onMetadata:value=>{cellSelection.metadata(value);columnTree?.onMetadata?.(value);},onSelectEpoch:(...args)=>{setPreviewOpen(true);columnTree?.onSelectEpoch?.(...args);}}}/></div>{!designMode&&detail}</>}
      metadata={metadata&&(metadata.loadingPolicy?<div className="stable-content stable-metadata"><div className="stable-content-body">{metadataPanel}</div></div>:<StableContent {...resource} className="stable-metadata" data={epoch}>{metadataPanel}</StableContent>)}/>
  </div>;
}
