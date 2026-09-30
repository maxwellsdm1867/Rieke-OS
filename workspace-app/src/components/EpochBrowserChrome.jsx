import {createPortal} from 'react-dom';
import {ChevronsDownUp,Activity,GitBranch,MessageCircle,PanelRightClose,PanelRightOpen,ArrowLeft,ArrowRight,X,Download} from 'lucide-react';
import {number} from '../api.js';
import InspectorActions from './InspectorActions.jsx';

export function EpochBrowserToolbar({designMode=false,designDisabled=false,onBrowse,onDesign,onTags,metadataOpen,onToggleMetadata,onExport,exportDisabled=false,actions=[],children,treeControlsInPane=false,filterControl=null,portalTarget=null}){
  const toolbar=<div className="inspector-toolbar compact-inspector-toolbar">{!treeControlsInPane&&<nav className="inspection-view-switch" aria-label="Tree editing">{designMode?<button onClick={onBrowse}><ArrowLeft size={15}/> Back to epochs</button>:<button disabled={designDisabled} onClick={onDesign}><GitBranch size={15}/> Edit tree</button>}</nav>}<span className="spacer"/>{!designMode&&<>{filterControl}<button onClick={onTags}><MessageCircle size={15}/> Tags</button><button aria-pressed={metadataOpen} aria-controls="epoch-metadata-sidebar" title="Show or hide epoch metadata" onClick={onToggleMetadata}>{metadataOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>} Details</button></>}{children}{onExport&&<button className="primary" disabled={exportDisabled} onClick={onExport}><Download size={15}/> Export</button>}<InspectorActions actions={actions}/></div>;
  return portalTarget?createPortal(toolbar,portalTarget):toolbar;
}
export function EpochSelectionBar({targets,onTags,onClear,disabled=false}){
  return targets.length>0&&<div className="inspection-scope bulk-active compact-selection" role="status" aria-live="polite"><strong>{number(targets.length)} epochs selected</strong><button disabled={disabled||targets.length>1000} onClick={onTags}><MessageCircle size={13}/> Tag selected epochs</button><button disabled={disabled} onClick={onClear}><X size={13}/> Clear</button></div>;
}
export function EpochNavigation({position,total,loading=false,disabled=false,onMove}){
  return <div className="epoch-navigation" tabIndex={0} aria-label="Epoch navigation. Tab next; Shift+Tab previous; W/S also navigate."><button disabled={disabled||loading||position===0} onClick={()=>onMove(-1)}><ArrowLeft size={14}/> Previous epoch</button><span>{loading?'Loading epoch…':position<0?'Focused epoch is outside the loaded page':`Epoch ${number(position+1)} of ${number(total)} matching epochs`}</span><button disabled={disabled||loading||(position>=0&&position+1>=total)} onClick={()=>onMove(1)}>Next epoch <ArrowRight size={14}/></button></div>;
}
export function EpochListHeading({treeMode=false,onTreeMode,onDesign,designDisabled=false,onCollapse}){
  return <div className="tree-heading" aria-label="Epoch list controls">{onCollapse&&<button className="tree-collapse-action" aria-label="Collapse all" title="Collapse all" disabled={designDisabled} onClick={onCollapse}><ChevronsDownUp size={13}/><span>Collapse all</span></button>}<div className="segmented">{onTreeMode&&<><button className={!treeMode?'active':''} aria-pressed={!treeMode} onClick={()=>onTreeMode(false)}>Epochs</button><button className={treeMode?'active':''} aria-pressed={treeMode} onClick={()=>onTreeMode(true)}>Split tree</button></>}</div>{onDesign&&<button className="tree-edit-action" aria-label="Edit tree" title="Edit tree" disabled={designDisabled} onClick={onDesign}><GitBranch size={13}/><span>Edit tree</span></button>}</div>;
}
