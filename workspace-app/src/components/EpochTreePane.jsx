import {EpochListHeading} from './EpochBrowserChrome.jsx';
import InspectionCellTree from './InspectionCellTree.jsx';
import PagedTree from './PagedTree.jsx';
import StableContent from './StableContent.jsx';

// The saved protocol and predicate browsers share the same navigation surface.
// Their data sources and inclusion policies remain explicit at the call site.
export default function EpochTreePane({treeMode,onTreeMode,onDesign,designDisabled=false,collapseRequest,onCollapse,treeProps,listProps,listRef,listKey,listStatus,children,childrenInTree=false}){
  const list=<InspectionCellTree {...listProps} key={listKey} collapseRequest={collapseRequest}/>;
  return <>
    <EpochListHeading treeMode={treeMode} onTreeMode={onTreeMode} onDesign={onDesign} designDisabled={designDisabled} onCollapse={onCollapse}/>
    {treeMode?<PagedTree {...treeProps} presentation="tree" collapseRequest={collapseRequest} externalCollapseControl/>:
      <div ref={listRef} className="tree-scroll" aria-label="Date, cell and epoch overview">{listStatus?<StableContent {...listStatus}>{list}</StableContent>:list}</div>}
    {(!treeMode||childrenInTree)&&children}
  </>;
}
