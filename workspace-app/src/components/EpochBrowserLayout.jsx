import {NavigationLoadingNotice} from './NavigationLoading.jsx';
import PaneDivider from './PaneDivider.jsx';

// Source adapters supply content and state; geometry and pane chrome live here.
export default function EpochBrowserLayout({layoutRef,sizes,treeOpen,metadataOpen,editing=false,tree,detail,metadata,onResize,onResizeCommit,treeMin=180,className=''}){
  const showMetadata=metadataOpen&&!editing;
  return <div ref={layoutRef} className={`inspection-layout resizable-layout ${className} ${treeOpen?'':'without-tree'} ${showMetadata?'metadata-open':''} ${showMetadata&&sizes.overlay?'metadata-overlay':''}`} style={{gridTemplateColumns:sizes.columns,'--metadata-width':`${sizes.metadata}px`}}>
    <NavigationLoadingNotice/>
    {treeOpen&&<><aside className="inspection-tree">{tree}</aside><PaneDivider label={editing?'Resize tree editor pane':'Resize epoch tree pane'} value={sizes.tree} min={treeMin} max={Math.max(treeMin,sizes.treeMax)} onChange={value=>onResize('tree',value)} onCommit={onResizeCommit?value=>onResizeCommit('tree',value):undefined}/></>}
    {editing?detail:<div className="inspection-detail">{detail}</div>}
    {showMetadata&&<><PaneDivider label="Resize metadata pane" value={sizes.metadata} min={240} max={sizes.metadataMax} reverse className={sizes.overlay?'metadata-overlay-divider':''} style={sizes.overlay?{right:sizes.metadata}:undefined} onChange={value=>onResize('metadata',value)} onCommit={onResizeCommit?value=>onResizeCommit('metadata',value):undefined}/>{metadata}</>}
  </div>;
}
