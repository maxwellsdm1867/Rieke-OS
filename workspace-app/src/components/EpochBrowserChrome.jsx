import {Activity,GitBranch,MessageCircle,PanelRightClose,PanelRightOpen,ArrowLeft,ArrowRight,X,Download} from 'lucide-react';
import {number} from '../api.js';
import InspectorActions from './InspectorActions.jsx';

export function EpochBrowserToolbar({designMode=false,designDisabled=false,onBrowse,onDesign,onTags,metadataOpen,onToggleMetadata,onExport,exportDisabled=false,actions=[],children}){
  return <div className="inspector-toolbar compact-inspector-toolbar"><nav className="inspection-view-switch" aria-label="Tree and epoch views"><button className={!designMode?'active':''} aria-pressed={!designMode} onClick={onBrowse}><Activity size={15}/> Browse epochs</button><button className={designMode?'active':''} aria-pressed={designMode} disabled={designDisabled} onClick={onDesign}><GitBranch size={15}/> Design tree</button></nav><span className="spacer"/>{!designMode&&<><button onClick={onTags}><MessageCircle size={15}/> Tags</button><button aria-pressed={metadataOpen} aria-controls="epoch-metadata-sidebar" title="Show or hide epoch metadata" onClick={onToggleMetadata}>{metadataOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>} Details</button></>}{children}{onExport&&<button className="primary" disabled={exportDisabled} onClick={onExport}><Download size={15}/> Export</button>}<InspectorActions actions={actions}/></div>;
}
export function EpochSelectionBar({targets,onTags,onClear,disabled=false}){
  return targets.length>0&&<div className="inspection-scope bulk-active compact-selection" role="status" aria-live="polite"><strong>{number(targets.length)} epochs selected</strong><button disabled={disabled||targets.length>1000} onClick={onTags}><MessageCircle size={13}/> Tag selected epochs</button><button disabled={disabled} onClick={onClear}><X size={13}/> Clear</button></div>;
}
export function EpochNavigation({position,total,loading=false,disabled=false,onMove}){
  return <div className="epoch-navigation" tabIndex={0} aria-label="Epoch navigation. Tab next; Shift+Tab previous; W/S also navigate."><button disabled={disabled||loading||position===0} onClick={()=>onMove(-1)}><ArrowLeft size={14}/> Previous epoch</button><span>{loading?'Loading epoch…':position<0?'Focused epoch is outside the loaded page':`Epoch ${number(position+1)} of ${number(total)} matching epochs`}</span><button disabled={disabled||loading||(position>=0&&position+1>=total)} onClick={()=>onMove(1)}>Next epoch <ArrowRight size={14}/></button></div>;
}
export function EpochListHeading({treeMode=false,onTreeMode}){
  return <div className="tree-heading"><h3>{treeMode?'Shared protocol tree':'Date · cell · epochs'}</h3>{onTreeMode&&<div className="segmented"><button className={!treeMode?'active':''} onClick={()=>onTreeMode(false)}>Epochs</button><button className={treeMode?'active':''} onClick={()=>onTreeMode(true)}>Split tree</button></div>}</div>;
}
