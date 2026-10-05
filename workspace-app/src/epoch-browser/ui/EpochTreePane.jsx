import {EpochListHeading} from './EpochBrowserChrome.jsx';
import InspectionCellTree from './InspectionCellTree.jsx';
import PagedTree from '../../tree-browser/ui/PagedTree.jsx';
import StableContent from '../../components/StableContent.jsx';

// The saved protocol and predicate browsers share the same navigation surface.
// Their data sources and inclusion policies remain explicit at the call site.
export default function EpochTreePane({treeMode,onTreeMode,onDesign,designDisabled=false,collapseRequest,onCollapse,treeProps,listProps,listRef,listKey,listStatus,selectionTools,children,childrenInTree=false}){
  const list=<InspectionCellTree {...listProps} key={listKey} collapseRequest={collapseRequest}/>;
  return <>
    <EpochListHeading treeMode={treeMode} onTreeMode={onTreeMode} onDesign={onDesign} designDisabled={designDisabled} onCollapse={onCollapse}/>
    {treeMode?<PagedTree {...treeProps} presentation="tree" collapseRequest={collapseRequest} externalCollapseControl/>:
      <div ref={listRef} className="tree-scroll" aria-label="Date, cell and epoch overview">{listStatus?<StableContent {...listStatus}>{list}</StableContent>:list}</div>}
    {selectionTools}
    {(!treeMode||childrenInTree)&&children}
  </>;
}
