import {useState} from 'react';
import {RetainedPortal} from '../../retainedWorkspaceViews.js';
import {ChevronsDownUp,Activity,GitBranch,MessageCircle,PanelRightClose,PanelRightOpen,ArrowLeft,ArrowRight,X,Download,CheckSquare,Square,ChevronDown,ChevronUp} from 'lucide-react';
import {number} from '../../api.js';
import InspectorActions from './InspectorActions.jsx';
import NeuronIcon from '../../components/NeuronIcon.jsx';

export function EpochBrowserToolbar({designMode=false,browseLabel='Back to epochs',designDisabled=false,onBrowse,onDesign,onTags,metadataOpen,onToggleMetadata,onExport,exportDisabled=false,actions=[],children,treeControlsInPane=false,filterControl=null,portalTarget=null}){
  const toolbar=<div className="inspector-toolbar compact-inspector-toolbar">{!treeControlsInPane&&<nav className="inspection-view-switch" aria-label="Tree view">{designMode?<button onClick={onBrowse}><ArrowLeft size={15}/> {browseLabel}</button>:<button disabled={designDisabled} onClick={onDesign}><GitBranch size={15}/> View tree</button>}</nav>}<span className="spacer"/>{filterControl}{!designMode&&<><button onClick={onTags}><MessageCircle size={15}/> Tags</button><button aria-pressed={metadataOpen} aria-controls="epoch-metadata-sidebar" title="Show or hide epoch metadata" onClick={onToggleMetadata}>{metadataOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>} Details</button></>}{children}{onExport&&<button className="primary" disabled={exportDisabled} onClick={onExport}><Download size={15}/> Export</button>}<InspectorActions actions={actions}/></div>;
  return portalTarget?<RetainedPortal target={portalTarget}>{toolbar}</RetainedPortal>:toolbar;
}
export function EpochSelectionBar(props){
  return props.targets.length>1?<ActiveEpochSelectionBar {...props}/>:null;
}
function ActiveEpochSelectionBar({targets,cellCount=null,onTags,onClear,hideClear=false,onSelectAll,onSelectCell,cellSelectDisabled=false,onInclude,onExclude,onRemove,scope='export',disabled=false}){
  const [expanded,setExpanded]=useState(true);
  const cells=Number.isSafeInteger(cellCount)&&cellCount>=0?cellCount:null;
  return <div className={`inspection-scope bulk-active compact-selection${expanded?'':' is-collapsed'}`} role="status" aria-live="polite" aria-label="Current selection">
    <div className="epoch-selection-metrics">
      <span aria-label={cells==null?'Selected cell count unavailable':`${number(cells)} selected cells`} title={cells==null?'Selected cell count unavailable':undefined}><NeuronIcon size={18}/><strong>{cells==null?'—':number(cells)}</strong><small>{cells===1?'cell':'cells'}</small></span>
      <span aria-label={`${number(targets.length)} epochs selected`}><Activity size={18} aria-hidden="true"/><strong>{number(targets.length)}</strong><small>{targets.length===1?'epoch':'epochs'}</small></span>
    </div>
    <button className="quiet epoch-selection-toggle" aria-expanded={expanded} aria-label={expanded?'Hide selection actions':'Show selection actions'} title={expanded?'Hide selection actions without clearing the selection':'Show selection actions'} onClick={()=>setExpanded(value=>!value)}>{expanded?<ChevronUp size={14}/>:<ChevronDown size={14}/>}<span>{expanded?'Hide actions':'Show actions'}</span></button>
    {expanded&&<div className="epoch-selection-actions">
      {onSelectAll&&<button disabled={disabled} onClick={onSelectAll} title="Select every matching epoch in this filtered protocol, up to 1,000."><CheckSquare size={13}/> Select all</button>}
      {!hideClear&&<button disabled={disabled} onClick={onClear}><Square size={13}/> Deselect all</button>}
      {onSelectCell&&<button disabled={disabled||cellSelectDisabled} onClick={onSelectCell} title="Select the matching epochs from the focused cell.">Select focused cell</button>}
      <button disabled={disabled||targets.length>1000} onClick={onTags}><MessageCircle size={13}/> Tag selected epochs</button>
      <button disabled={disabled||targets.length>1000} onClick={onExclude} hidden={!onExclude}>Exclude selected from {scope}</button>
      <button disabled={disabled||targets.length>1000} onClick={onInclude} hidden={!onInclude}>Include selected in {scope}</button>
      {onRemove&&<button disabled={disabled||targets.length>1000} onClick={onRemove} title="Review removal of the selected epochs from this pinned protocol. Recordings and other protocols are kept.">Remove from pinned protocol</button>}
    </div>}
  </div>;
}
export function EpochNavigation({position,total,loading=false,disabled=false,onMove}){
  // total is null while exact counts are pending; Next stops at the last row.
  const counting=total==null;
  return <div className="epoch-navigation" tabIndex={0} aria-label="Epoch navigation. Tab next; Shift+Tab previous; Up/Down or W/S also navigate."><button disabled={disabled||loading||position===0} onClick={()=>onMove(-1)}><ArrowLeft size={14}/> Previous epoch</button><span>{loading?'Loading epoch…':position<0?'Focused epoch is outside the loaded page':counting?`Epoch ${number(position+1)} · counting matching epochs…`:`Epoch ${number(position+1)} of ${number(total)} matching epochs`}</span><button disabled={disabled||loading||(!counting&&position>=0&&position+1>=total)} onClick={()=>onMove(1)}>Next epoch <ArrowRight size={14}/></button></div>;
}
export function EpochListHeading({treeMode=false,onTreeMode,onDesign,designDisabled=false,onCollapse}){
  return <div className="tree-heading" aria-label="Epoch list controls">{onCollapse&&<button className="tree-collapse-action" aria-label="Collapse all" title="Collapse all" disabled={designDisabled} onClick={onCollapse}><ChevronsDownUp size={13}/><span>Collapse all</span></button>}<div className="segmented">{onTreeMode&&<><button className={!treeMode?'active':''} aria-pressed={!treeMode} onClick={()=>onTreeMode(false)}>Epochs</button><button className={treeMode?'active':''} aria-pressed={treeMode} onClick={()=>onTreeMode(true)}>Split tree</button></>}</div>{onDesign&&<button className="tree-edit-action" aria-label="View tree" title="View tree" disabled={designDisabled} onClick={onDesign}><GitBranch size={13}/><span>View tree</span></button>}</div>;
}

export function EpochHighlightTools({count=0,allSelected=false,disabled=false,onSelect,onDeselect}){
  return <button className="epoch-highlight-action" disabled={disabled||!count} title="Shift-click a range · ⌘/Ctrl-click to add rows" onClick={allSelected?onDeselect:onSelect}>
    {allSelected?'Deselect Highlighted':'Select Highlighted'} ({number(count)})
  </button>;
}
