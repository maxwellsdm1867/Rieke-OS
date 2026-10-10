import ScientificContext from '../../components/ScientificContext.jsx';
import {useState} from 'react';
import {Activity,ArrowLeft,Tags,X} from 'lucide-react';
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
export default function EpochViewer({className='epoch-inspector-mode',ariaLabel='Epoch inspection',onKeyDown,toolbar,toolbarChildren,viewFilters,onViewFilters,filterRevision,filterDisabled=false,hideFilterControl=false,before,layout,designMode=false,builder,columnTree,treePane,resource={},epoch,targets=[],navigation,traceRevision,readContext=null,inclusion,detailDisabled=false,onQC,tags,detailExtras,metadata}){
  const [tracePreference,setTracePreference]=useState(undefined);
  const [previewOpen,setPreviewOpen]=useState(true);
  const [tagsOpen,setTagsOpen]=useState(false);
  const cellSelection=useTreeCellSelection(designMode&&!readContext?columnTree:null);
  const hasPreview=!!(epoch||columnTree?.selected);
  const showPreview=designMode&&previewOpen&&hasPreview;
  const tracePane=showPreview&&!columnTree?.actionsDisabled?<section className="tree-trace-pane" aria-label="Raw recording preview"><header><strong><Activity size={14}/> Raw recording</strong><button className="icon-button" aria-label="Close raw recording preview" onClick={()=>setPreviewOpen(false)}><X size={15}/></button></header><div className="tree-trace-body"><StableContent {...resource} data={epoch}>{epoch&&<><div className="tree-preview-identity"><strong>{datedCellLabel(epoch)}</strong><span>Epoch {epoch.epoch_number??'—'} · {epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'Time not recorded'}</span></div><Trace viewPreference={tracePreference} onViewPreference={setTracePreference} epoch={epoch} revision={traceRevision} readContext={readContext}/></>}</StableContent></div></section>:null;
  const treeTags=<div className="tree-selection-tags" hidden={!tagsOpen}>{cellSelection.cells.length?<><div className="tree-cell-selection" aria-label="Selected cells"><strong>{cellSelection.cells.length} cells selected</strong><button disabled={cellSelection.blocked} onClick={cellSelection.clear}>Clear cell selection</button><div>{cellSelection.cells.map(cell=><span key={cell.cell_uuid}>{cell.label}</span>)}</div></div><AnnotationTags composer={cellSelection.composer} selectedCells={cellSelection.ids} targetScope="selected-cells" revision={cellSelection.revision} disabled={cellSelection.blocked} reconcileReceipt onChange={columnTree?.onAnnotationsChanged}/></>:<StableContent {...resource} data={epoch}>{tags}</StableContent>}</div>;
  const detail=<StableContent {...resource} data={epoch}>{!readContext&&!designMode&&targets.length?<SelectionOverview count={targets.length}/>:epoch?<>
    {designMode?<div className="tree-preview-identity"><strong>{datedCellLabel(epoch)}</strong><span>Epoch {epoch.epoch_number??'—'} · {epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'Time not recorded'}</span></div>:<EpochDetailHeading epoch={epoch} disabled={detailDisabled} onQC={onQC}/>}
    {navigation&&!designMode&&<EpochNavigation {...navigation}/>}
    <Trace viewPreference={tracePreference} onViewPreference={setTracePreference} epoch={epoch} revision={traceRevision} readContext={readContext}/>
    <div className="curation-bar">{inclusion&&<EpochAnalysisInclusion epoch={epoch} {...inclusion}/>} {!designMode&&!layout.metadataOpen&&(!layout.treeOpen||treePane?.treeMode)&&tags}</div>
    {detailExtras}
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
