import ScientificContext from './ScientificContext.jsx';
import {ArrowLeft} from 'lucide-react';
import './EpochViewer.css';
import {EpochBrowserToolbar,EpochNavigation} from './EpochBrowserChrome.jsx';
import EpochBrowserLayout from './EpochBrowserLayout.jsx';
import EpochTreePane from './EpochTreePane.jsx';
import TreeBuilder from './TreeBuilder.jsx';
import PagedTree from './PagedTree.jsx';
import StableContent from './StableContent.jsx';
import EpochDetailHeading from './EpochDetailHeading.jsx';
import EpochAnalysisInclusion from './EpochAnalysisInclusion.jsx';
import Trace from './TraceViewer.jsx';
import MetadataPanel from './MetadataPanel.jsx';
import SelectionOverview from './SelectionOverview.jsx';
import ProtocolViewFilter from './ProtocolViewFilter.jsx';
import {clearTagFilters,tagFilterLabel} from '../protocolViewFilter.js';
import {Empty} from './Common.jsx';

// Source adapters provide data and mutations; every viewer assembles its UI here.
export default function EpochViewer({className='epoch-inspector-mode',ariaLabel='Epoch inspection',onKeyDown,toolbar,toolbarChildren,viewFilters,onViewFilters,filterRevision,filterDisabled=false,before,layout,designMode=false,builder,columnTree,treePane,resource={},epoch,targets=[],navigation,traceRevision,inclusion,detailDisabled=false,onQC,tags,detailExtras,metadata}){
  const detail=<StableContent {...resource} data={epoch}>{targets.length?<SelectionOverview count={targets.length}/>:epoch?<>
    <EpochDetailHeading epoch={epoch} disabled={detailDisabled} onQC={onQC}/>
    {navigation&&<EpochNavigation {...navigation}/>}
    <Trace epoch={epoch} revision={traceRevision}/>
    <div className="curation-bar">{inclusion&&<EpochAnalysisInclusion epoch={epoch} {...inclusion}/>} {!layout.metadataOpen&&(!layout.treeOpen||treePane?.treeMode)&&tags}</div>
    {detailExtras}
  </>:<Empty title="Choose an epoch">Select an epoch from the tree to inspect its response and metadata.</Empty>}</StableContent>;
  return <div className={`inspector ${className}`} tabIndex={0} aria-label={ariaLabel} onKeyDown={onKeyDown}>
    {toolbar&&<EpochBrowserToolbar {...toolbar} filterControl={onViewFilters?<ProtocolViewFilter filters={viewFilters} onChange={onViewFilters} revision={filterRevision} disabled={filterDisabled}/>:toolbar.filterControl} treeControlsInPane>{toolbarChildren}{!designMode&&onViewFilters&&tagFilterLabel(viewFilters)&&<span className="inspection-filter-summary">{tagFilterLabel(viewFilters)}<button disabled={filterDisabled} onClick={()=>onViewFilters(clearTagFilters(viewFilters))}>Clear filter</button></span>}</EpochBrowserToolbar>}
    {before}
    <EpochBrowserLayout {...layout} editing={designMode}
      tree={designMode?<><nav className="tree-design-controls" aria-label="Tree editing"><button onClick={toolbar?.onBrowse}><ArrowLeft size={15}/> Back to epochs</button></nav><TreeBuilder {...builder}/></>:<EpochTreePane {...treePane} childrenInTree={false}>{!layout.metadataOpen&&<StableContent {...resource} className="stable-tag-dock" data={epoch}>{tags}</StableContent>}</EpochTreePane>}
      detail={designMode?<PagedTree {...columnTree} presentation="columns" design/>:detail}
      metadata={metadata&&<StableContent {...resource} className="stable-metadata" data={epoch}><MetadataPanel {...metadata} epoch={epoch} tags={tags} context={epoch&&<ScientificContext epoch={epoch}/>}/></StableContent>}/>
  </div>;
}
