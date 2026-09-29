import {NavigationLoadingProvider,NavigationLoadingNotice} from './NavigationLoading.jsx';
import StableContent from './StableContent.jsx';
import {advanceEpochIntent,epochIntentAt,epochAtIntent} from '../epochNavigationIntent.js';
import {SourceEligibilityNotice} from './Common.jsx';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, GitBranch, Check, X, MessageCircle, ArrowLeft, ArrowRight, Activity, Eye, Info, PanelRightClose, PanelRightOpen, Upload, Download, FileJson } from 'lucide-react';
import { api, useResource, useEpochResource, useEpochPrefetch, number, humanize, resolveCurationTargets } from '../api.js';
import { Status, Metadata, Badge, Empty } from './Common.jsx';
import EpochConnections from './EpochConnections.jsx';
import TreeBuilder from './TreeBuilder.jsx';
import TreePreview from './TreePreview.jsx';
import './InspectorPolish.css';
import './MatlabMaskImport.css';
import MetadataPanel from './MetadataPanel.jsx';
import InspectionCellTree from './InspectionCellTree.jsx';
import {EpochBrowserToolbar,EpochSelectionBar,EpochNavigation,EpochListHeading} from './EpochBrowserChrome.jsx';
import EpochTags from './EpochTags.jsx';
import AnnotationTags from './AnnotationTags.jsx';
import TagExchangeControls from './TagExchangeControls.jsx';
import './Inspector.css';

import {inspectionSearches,indexInspectionTree,focusAfterTreeSelection,curationMatchesCellFocus} from '../inspectionScope.js';
import {branchLabel,branchTooltip,componentLabel,componentValue,epochLeafLabel,readableField} from '../treeBranchPresentation.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {restoredEpochFocus} from '../workspaceNavigation.js';
import {boundedTreePage,inspectionTreeFocus} from '../boundedTree.js';
import Trace from './TraceViewer.jsx';
import PaneDivider from './PaneDivider.jsx';
import PagedTree from './PagedTree.jsx';
import {inspectorPaneSizes,epochShortcutDirection,resourceForPath} from '../inspectorInteraction.js';
export {Trace};

function TreePageControls({page,onPage,kind}){
  if(page.total<=60&&!page.pinnedOutside)return null;
  return <div className="tree-page-controls"><div><button disabled={!page.hasPrevious} onClick={()=>onPage(page.offset-60)} aria-label={`Previous ${kind}`}><ArrowLeft size={12}/></button><span>{page.total?page.offset+1:0}–{page.end} of {number(page.total)} {kind}</span><button disabled={!page.hasNext} onClick={()=>onPage(page.offset+60)} aria-label={`Next ${kind}`}><ArrowRight size={12}/></button></div>{page.pinnedOutside&&<small>Focused item also shown below this page.</small>}</div>;
}
export function Branch({node,onFocus,selected,depth=0,cellBranches=null,parentField=null,treeFocus}) {
  const selectedBranch=treeFocus?.branches.has(node) || false;
  const [open,setOpen] = useState(selectedBranch);
  const [offset,setOffset] = useState(0);
  const inFocusedCell=cellBranches?.has(node) || false;
  useEffect(()=>{if(selectedBranch)setOpen(true);},[selectedBranch]);
  const children = node.children || [];
  // Legacy UUID-only leaves are converted only for the visible page.
  const leafValues=node.epochs || node.epoch_uuids || [];
  const pin=children.length?treeFocus?.childOf.get(node):selectedBranch?(node.epochs?treeFocus?.epoch:selected):null;
  const page=boundedTreePage(children.length?children:leafValues,offset,60,pin);
  return <div className={`tree-branch ${inFocusedCell?'cell-focus-branch':''}`}>
    <button className="branch-label" onClick={()=>setOpen(!open)} aria-expanded={open} title={branchTooltip(node,parentField)}>
      {open?<ChevronDown size={13}/>:<ChevronRight size={13}/>}
      <span className={node.components?.length?'branch-combination':''}>{node.components?.length?node.components.map(part=><span className="branch-component" key={part.field}><small title={part.field}>{componentLabel(part)}</small><span>{componentValue(part)}</span></span>):branchLabel(node,parentField)}</span>
      <small>{node.count ?? node.epoch_count ?? leafValues.length}</small>
    </button>
    {open && <div className="branch-children">
      {children.length>0&&node.field_label&&<div className="branch-field-label" title={node.field}>{readableField(node.field_label,node.field)}</div>}
      <TreePageControls page={page} onPage={setOffset} kind={children.length?'groups':'epochs'}/>
      {children.length?page.items.map(n=><Branch key={n.key ?? JSON.stringify([n.missing===true,n.value])} node={n} onFocus={onFocus} selected={selected} depth={depth+1} cellBranches={cellBranches} parentField={node.field} treeFocus={treeFocus}/>):page.items.map(item=>{
        const e=typeof item==='string'?{epoch_uuid:item}:item;
        return <button className={`epoch-leaf ${selected===e.epoch_uuid?'selected':''}`} key={e.epoch_uuid} onClick={()=>onFocus(e.epoch_uuid)} title={`${e.start_time || ''} · ${e.epoch_uuid}`}>
          <Activity size={12}/><span>{e.cell_label&&<small>{datedCellLabel(e)} · </small>}{epochLeafLabel(e)}</span>
        </button>;
      })}
    </div>}
  </div>;
}
function InspectionTree({tree,onFocus,selected,cellBranches,treeFocus}){
  const [offset,setOffset]=useState(0);
  const nodes=tree.children?.length?tree.children:tree.tree?.children?.length?tree.tree.children:tree.groups?.length?tree.groups:(tree.epochs||tree.epoch_uuids?[tree]:[]);
  const pin=nodes.length===1&&nodes[0]===tree?tree:treeFocus?.childOf.get(tree);
  const page=boundedTreePage(nodes,offset,60,pin);
  return <><TreePageControls page={page} onPage={setOffset} kind="top-level groups"/>{page.items.map(node=><Branch key={node.key ?? JSON.stringify([node.missing===true,node.value])} node={node} onFocus={onFocus} selected={selected} cellBranches={cellBranches} parentField={tree.field} treeFocus={treeFocus}/>)}</>;
}

function recordedValue(value) {
  if (value === undefined || value === null) return 'Not recorded';
  if (value === '[]' || (Array.isArray(value) && value.length === 0)) return '[] (empty recorded field)';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}
function ScientificContext({epoch}) {
  const additions = epoch.metadata?.group?.properties?.externalSolutionAdditions;
  const historyProtocol=/VariableHistoryNoiseCurInject/.test(epoch.protocol_name || '');
  const controlFlag=Object.hasOwn(epoch.parameters || {},'isControl')?epoch.parameters.isControl:epoch.parameters?.controlMode;
  const historyControl=historyProtocol&&[1,true].includes(controlFlag);
  const historyPairs=historyProtocol?['history1','history2','target'].filter(key=>Array.isArray(epoch.parameters?.[key])&&epoch.parameters[key].length===2):[];
  const conditions = [
    ['currentMean','Current mean',''],
    ['currentSD','Current SD',''],
    ['frequencyCutoff','Frequency cutoff',''],
    ['stimTime','Stimulus duration',''],
  ].filter(([key])=>epoch.parameters?.[key] !== undefined && epoch.parameters[key] !== null);
  return <section className="scientific-context" aria-label="Recording and condition context">
    <div className="context-inline"><strong>{humanize(epoch.cell_type) || 'Type not recorded'}</strong><span>{epoch.source_filename || 'Source not recorded'}</span></div>
    <div className="context-inline"><span>Group label: <strong>{recordedValue(epoch.group_label)}</strong></span><span>External additions: <strong>{recordedValue(additions)}</strong></span></div>
    {historyControl&&<p className="history-control-note">Control epoch · target only; history settings were recorded but not delivered.</p>}
    {historyPairs.length>0&&<div className="history-pair-facts">{historyPairs.map(key=><div key={key}><span>{key==='target'?'Target':key==='history1'?'History 1':'History 2'}{historyControl&&key!=='target'?' · configured only':''}</span><strong>{recordedValue(epoch.parameters[key][0])} / {recordedValue(epoch.parameters[key][1])}</strong><small>Recorded mean / SD</small></div>)}</div>}
    {conditions.length>0&&<div className="condition-facts">{conditions.map(([key,label,units])=><div key={key}>
      <span>{label}</span><strong>{recordedValue(epoch.parameters[key])}{units && ` ${units}`}</strong>
    </div>)}</div>}
    <details className="context-timing"><summary>Block {epoch.block_start_time?.split(' ')[1] || 'time not recorded'} · acquisition details</summary><div className="context-facts">
      <div><span>Epoch block started</span><strong>{recordedValue(epoch.block_start_time)}</strong></div>
      <div><span>Epoch block ended</span><strong>{recordedValue(epoch.block_end_time)}</strong></div>
      <div className="context-protocol"><span>Acquisition protocol · source value</span><strong>{recordedValue(epoch.protocol_name)}</strong></div>
    </div><p className="source-note">Group labels and solution fields are separate source records. Empty fields do not establish control or wash.</p></details>
  </section>;
}

function InspectorContent({protocol,initialEpochUuid=null,cellScope,filters,revision,onChange,onBack,onImport,onStores,onExport,splitRecipe=['date','cell','block'],onSplitChange,initialNavigation=null,onSessionChange,onQC,onTagFilter}) {
  const id=protocol.definition.protocol_uuid;
  const requestedCellFocus=filters?.cell_uuid&&filters.cell_uuid!==cellScope?null:(cellScope || null);
  const [focusCell,setFocusCell]=useState(initialNavigation&&Object.hasOwn(initialNavigation,'focusCell')?initialNavigation.focusCell:requestedCellFocus);
  const [offset,setOffset]=useState(initialNavigation?.offset || 0), [focused,setFocused]=useState(()=>restoredEpochFocus(initialNavigation,initialEpochUuid)), [targets,setTargets]=useState([]);
  const [tagFocus,setTagFocus]=useState(0),[epochTagFocus,setEpochTagFocus]=useState(0);
  const [tag,setTag]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [operationMessage,setOperationMessage]=useState(''),[maskMessage,setMaskMessage]=useState('');
  const maskInput=useRef(null),matlabMaskInput=useRef(null);
  const [matlabMaskFile,setMatlabMaskFile]=useState(null),[matlabDataset,setMatlabDataset]=useState(''),[matchingExports,setMatchingExports]=useState([]);
  const [pendingNavigation,setPendingNavigation]=useState(null);
  const navigationIntent=useRef(null),anchorSteps=useRef(0);
  function selectEpoch(uuid){navigationIntent.current=null;anchorSteps.current=0;setPendingNavigation(null);setFocused(uuid);}
  const externalSplitKey=splitRecipe.join(',');
  const previousExternalSplit=useRef(externalSplitKey);
  const [splits,setSplits]=useState(externalSplitKey);
  const [masksOpen,setMasksOpen]=useState(false);
  const [metadataOpen,setMetadataOpen]=useState(()=>{try{const saved=localStorage.getItem('workspace.inspector.metadata');return saved===null?window.innerWidth>=1350:saved==='true';}catch{return true;}});
  function toggleMetadata(next){setMetadataOpen(next);try{localStorage.setItem('workspace.inspector.metadata',String(next));}catch{}}
  const matlabExports=useResource(masksOpen?`/exports?protocol_uuid=${id}`:null,revision,80);
  useEffect(()=>{setMatlabMaskFile(null);setMatlabDataset('');setMatchingExports([]);},[id]);
  const matchingMatlabExports=[...new Map([...(matlabExports.data?.exports || []).filter(item=>item.format==='epictree-mat'&&item.protocol_uuid===id&&item.status==='completed'),...matchingExports].map(item=>[item.dataset_uuid,item])).values()];
  const [designMode,setDesignMode]=useState(initialNavigation?.designMode || false),[designPath,setDesignPath]=useState(initialNavigation?.designPath || []);
  const [designNavigation,setDesignNavigation]=useState(initialNavigation?.designNavigation||null);
  const changeSplits=useCallback(fields=>{setSplits(fields.join(','));setDesignPath([]);setDesignNavigation(null);},[]);
  const [treeOpen,setTreeOpen]=useState(initialNavigation?.treeOpen ?? true),[treeMode,setTreeMode]=useState(initialNavigation?.treeMode ?? false);
  const {protocol:protocolSearch,navigation:search}=inspectionSearches(filters,focusCell);
  const rowsPath=`/protocols/${id}/epochs?${search}&${pendingNavigation?.anchorUuid?`anchor_uuid=${encodeURIComponent(pendingNavigation.anchorUuid)}`:`offset=${offset}`}&limit=60`;
  const loadedRows=useResource(rowsPath,revision);
  const rows=resourceForPath(loadedRows,rowsPath);
  const [treePage,setTreePage]=useState(null);
  const [treeStatus,setTreeStatus]=useState({loading:true,error:null});
  const tree={data:treePage,...treeStatus};
  const receiveTree=useCallback(data=>setTreePage(data),[]);
  useEffect(()=>setTreePage(null),[id,protocolSearch,splits,revision]);
  const layoutRef=useRef(null),[layoutWidth,setLayoutWidth]=useState(1100);
  const [paneWidths,setPaneWidths]=useState(()=>{try{return JSON.parse(localStorage.getItem('workspace.inspector.paneWidths')||'{}');}catch{return {};}});
  const paneSizes=inspectorPaneSizes(layoutWidth,paneWidths||{},treeOpen,!designMode&&metadataOpen);
  const changePane=(key,value)=>setPaneWidths(old=>({...old,[key]:value}));
  const savePane=(key,value)=>{setPaneWidths(old=>{const next={...old,[key]:value};try{localStorage.setItem('workspace.inspector.paneWidths',JSON.stringify(next));}catch{}return next;});};
  useEffect(()=>{const element=layoutRef.current;if(!element)return;const observer=new ResizeObserver(entries=>setLayoutWidth(entries[0].contentRect.width));observer.observe(element);return()=>observer.disconnect();},[]);
  const epoch=useEpochResource(focused?`/epochs/${focused}?protocol_uuid=${id}`:null,revision,80);
  const focusedEpoch=epoch.data?.epoch_uuid===focused?epoch.data:null;
  const neighborIndex=rows.data?.epochs?.findIndex(row=>row.epoch_uuid===focused)??-1;
  useEpochPrefetch(!epoch.loading&&!rows.loading&&neighborIndex>=0?[rows.data.epochs[neighborIndex+1],rows.data.epochs[neighborIndex-1]].filter(Boolean).map(row=>`/epochs/${row.epoch_uuid}?protocol_uuid=${id}`):[],revision);
  const metadataCatalog=useResource(metadataOpen&&!designMode?`/protocols/${id}/tree-fields?${protocolSearch}`:null,revision);
  const scopeIdentity=JSON.stringify([id,requestedCellFocus,protocolSearch,initialEpochUuid]);
  const previousScope=useRef(scopeIdentity);
  useEffect(()=>{if(previousScope.current===scopeIdentity)return;previousScope.current=scopeIdentity;navigationIntent.current=null;anchorSteps.current=0;setFocusCell(requestedCellFocus);setOffset(0);setFocused(initialEpochUuid);setTargets([]);setPendingNavigation(null);setDesignNavigation(null);},[scopeIdentity,id,requestedCellFocus,protocolSearch,initialEpochUuid]);
  useEffect(()=>{onSessionChange?.({focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation});},[focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation,onSessionChange]);

  function clearCellFocus(){navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);setTargets([]);setPendingNavigation(null);}
  function selectOverviewTargets(update){
    // This overview spans every matching cell, including when entered from a cell shortcut.
    if(focusCell){navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);setPendingNavigation(null);}
    setTargets(update);
  }
  function focusTreeEpoch(uuid,epochInfo){
    if(busy)return;
    if(focusCell&&epochInfo?.cell_uuid!==focusCell)clearCellFocus();
    navigationIntent.current=null;anchorSteps.current=0;setFocused(uuid);setPendingNavigation({anchorUuid:uuid,direction:0});
  }
  useEffect(()=>{navigationIntent.current=null;anchorSteps.current=0;},[id,search,revision]);
  useEffect(()=>{
    if(!pendingNavigation)return;
    if(rows.error){navigationIntent.current=null;anchorSteps.current=0;setError(rows.error);setPendingNavigation(null);return;}
    if(rows.loading||!rows.data)return;
    const page=rows.data;
    let target=navigationIntent.current;
    if(pendingNavigation.anchorUuid){
      const index=page.epochs.findIndex(row=>row.epoch_uuid===pendingNavigation.anchorUuid);
      if(index<0){setError('The selected epoch is no longer in this query. Refresh the dataset.');setPendingNavigation(null);return;}
      target=epochIntentAt(page.offset+index+(pendingNavigation.direction||0)+anchorSteps.current,page.total);
      anchorSteps.current=0;
    }else if(!target){
      target=epochIntentAt(pendingNavigation.targetIndex??(page.offset+(pendingNavigation.edge==='last'?page.epochs.length-1:0)),page.total);
    }
    target=target&&epochIntentAt(target.index,page.total);
    navigationIntent.current=target;
    if(!target){setFocused(null);setPendingNavigation(null);return;}
    const uuid=epochAtIntent(page,target);
    if(uuid){setFocused(uuid);setOffset(page.offset);setPendingNavigation(null);}
    else{setOffset(target.offset);setPendingNavigation({offset:target.offset,targetIndex:target.index});}
  },[pendingNavigation,rows.data,rows.loading,rows.error]);
  // Persist grouping only after the server has successfully built that tree.
  useEffect(()=>{if(previousExternalSplit.current===externalSplitKey&&tree.data&&!tree.loading&&!tree.error&&tree.data.split_order?.join(',')===splits)onSplitChange?.(tree.data.split_order);},[tree.data,tree.loading,tree.error,splits,onSplitChange,externalSplitKey]);
  useEffect(()=>{if(previousExternalSplit.current!==externalSplitKey){previousExternalSplit.current=externalSplitKey;if(splits!==externalSplitKey){setSplits(externalSplitKey);setDesignPath([]);setDesignNavigation(null);}}},[externalSplitKey,splits]);
  async function curate(changes, scope='selection') {
    if(busy)return;
    const uuids=resolveCurationTargets(focused,targets,scope);
    if(!uuids.length)return;
    setBusy(true);setError('');setOperationMessage('Saving curation changes…');
    try {
      const states=await Promise.all(uuids.map(uuid=>api(`/epochs/${uuid}?protocol_uuid=${id}`)));
      if(!curationMatchesCellFocus(states,focusCell))throw new Error('Cell focus changed. Clear the selection and select epochs in the current cell before saving.');
      const expected_revisions=Object.fromEntries(states.map(e=>[e.epoch_uuid,e.curation?.revision||0]));
      await api(`/protocols/${id}/curation`,{method:'POST',body:{epoch_uuids:uuids,changes,expected_revisions,query_revision:protocol.query_revision}});
      setTag('');onChange();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function importMask(event) {
    const file=event.target.files?.[0];event.target.value='';
    if(!file||busy)return;
    setBusy(true);setError('');setMaskMessage('');setOperationMessage('Validating and importing protocol selection mask…');
    try {
      if(file.size>5*1024*1024)throw new Error('Selection mask is larger than the 5 MB limit. Choose a Recording Selection Mask JSON file.');
      let mask;
      try{mask=JSON.parse(await file.text());}catch{throw new Error('The selected file is not valid JSON. Choose a Recording Selection Mask v1 file.');}
      if(mask?.format!=='recording-selection-mask'||mask.version!==1)throw new Error('This button accepts Recording Selection Mask v1 JSON. Use Import MATLAB UGM below for .ugm masks.');
      if(mask.protocol_uuid!==id)throw new Error('This mask belongs to a different protocol. Open that protocol before importing it.');
      const result=await api(`/protocols/${id}/masks/import`,{method:'POST',body:{mask,query_revision:protocol.query_revision}});
      setMaskMessage(result.message || `Imported ${file.name}. Inclusion decisions were restored for the mask’s epochs; review approvals were not changed.`);
      onChange();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function importMatlabMask(){
    if(!matlabMaskFile||busy)return;
    setBusy(true);setError('');setMaskMessage('');setOperationMessage('Validating MATLAB mask against a completed export…');
    try{
      if(matlabMaskFile.size>32*1024*1024)throw new Error('MATLAB masks are limited to 32 MiB.');
      if(!matlabMaskFile.size)throw new Error('The selected mask file is empty.');
      if(!matlabMaskFile.name.toLowerCase().endsWith('.ugm'))throw new Error('Choose an EpicTree .ugm selection mask. This importer does not accept recording .mat files.');
      const body=new FormData();body.append('file',matlabMaskFile);body.append('query_revision',protocol.query_revision);
      if(matlabDataset)body.append('dataset_uuid',matlabDataset);
      const response=await fetch(`/api/protocols/${id}/masks/import-matlab`,{method:'POST',headers:{'X-Workspace-Request':'1'},body});
      const result=await response.json().catch(()=>({}));
      if(!response.ok){if(Array.isArray(result.matching_exports))setMatchingExports(result.matching_exports);throw new Error(result.error || result.message || `Mask import failed (${response.status})`);}
      if(!Number.isInteger(result.imported_count)||result.imported_count<1||!Number.isInteger(result.included_count)||result.included_count<0||result.included_count>result.imported_count||typeof result.dataset_uuid!=='string'||typeof result.query_revision!=='string'){onChange();throw new Error('The server did not return a complete import receipt. Check Activity & logs before retrying.');}
      setMaskMessage(result.message || `Imported ${number(result.imported_count)} MATLAB mask decisions from the matched export. Other epochs, tags and review states were unchanged.`);
      setMatlabMaskFile(null);setMatchingExports([]);onChange();
    }catch(error){setError(error.message);}finally{setBusy(false);}
  }
  const focusedPageIndex=rows.data?.epochs?.findIndex(e=>e.epoch_uuid===focused) ?? -1;
  function moveEpoch(direction) {
    if(busy)return;
    if(pendingNavigation?.anchorUuid){anchorSteps.current+=direction;return;}
    const next=advanceEpochIntent({page:rows.data,focused,intent:navigationIntent.current,direction});
    if(!next){
      if(!rows.loading&&focused){anchorSteps.current=0;setPendingNavigation({anchorUuid:focused,direction});}
      return;
    }
    navigationIntent.current=next;
    const uuid=!rows.loading&&epochAtIntent(rows.data,next);
    if(uuid){setFocused(uuid);setPendingNavigation(null);}
    else{setPendingNavigation({offset:next.offset,targetIndex:next.index});setOffset(next.offset);}
  }
  function epochKeys(event){if(designMode||!focused)return;const direction=epochShortcutDirection(event);if(!direction)return;event.preventDefault();event.stopPropagation();if(event.currentTarget.hasAttribute('tabindex'))event.currentTarget.focus({preventScroll:true});moveEpoch(direction);}
  function navigateAndTag(direction){
    if(busy||pendingNavigation)return;
    moveEpoch(direction);setEpochTagFocus(value=>value+1);
  }
  function openTagsForSelection(){
    if(!focused&&targets.length)focusTreeEpoch(targets[0]);
    toggleMetadata(true);setTagFocus(value=>value+1);
  }
  const epochListRef=useRef(null);
  const actionScope=targets.length?`${targets.length} selected`:'focused epoch';
  const annotationChanged=()=>{epoch.reload();loadedRows.reload();onChange?.();};
  const tagEntry=focusedEpoch&&<AnnotationTags epoch={focusedEpoch} revision={revision} disabled={busy||epoch.loading||!!pendingNavigation} onChange={annotationChanged} onFilter={onTagFilter} focusRequest={tagFocus} epochFocusRequest={epochTagFocus} onNavigateEpoch={navigateAndTag} selectedEpochs={targets} tools={<TagExchangeControls epoch={focusedEpoch} disabled={busy} onChanged={annotationChanged}/>}><EpochTags value={tag} onValue={setTag} onAdd={value=>curate({tags_add:[value]})} onRemove={value=>curate({tags_remove:[value]},'focused')} selectedTags={focusedEpoch.curation?.tags||[]} busy={busy} scope={`dataset · ${actionScope}`} revision={revision}/></AnnotationTags>;
  return <div className={`inspector ${designMode?'tree-design':'epoch-inspector-mode'}`} tabIndex={0} onKeyDown={epochKeys} aria-label={designMode?'Tree overview workspace':'Epoch inspection workspace. Tab next epoch, Shift+Tab previous epoch; W/S also navigate.'}>
    <EpochBrowserToolbar onExport={onExport} exportDisabled={busy} designMode={designMode} onBrowse={()=>{setDesignMode(false);setTreeMode(false);setTreeOpen(true);}} onDesign={()=>{setDesignMode(true);setTreeOpen(true);setTreeMode(true);}} onTags={openTagsForSelection} metadataOpen={metadataOpen} onToggleMetadata={()=>toggleMetadata(!metadataOpen)} actions={[
        {label:treeOpen?(designMode?'Hide tree editor':'Hide epoch list'):(designMode?'Show tree editor':'Show epoch list'),icon:GitBranch,run:()=>setTreeOpen(value=>!value)},
        !designMode&&onImport&&{label:'Add data store',icon:Upload,run:onImport,disabled:busy},
        !designMode&&{label:masksOpen?'Hide selection masks':'Selection masks',icon:FileJson,run:()=>setMasksOpen(value=>!value)},
      ]}>
      {focusCell&&<button className="inspection-focus-chip" disabled={busy} onClick={clearCellFocus} title="Clear cell focus and navigate all matching cells">{datedCellLabel(protocol.cells?.find(cell=>cell.cell_uuid===focusCell)||focusedEpoch||{},true)} <X size={12}/></button>}
    </EpochBrowserToolbar>
    <SourceEligibilityNotice eligibility={protocol.source_eligibility} onStores={onStores}/>
    {!designMode&&<>
    <EpochSelectionBar targets={targets} onTags={openTagsForSelection} onClear={()=>setTargets([])} disabled={busy}/>
    {masksOpen&&<div className="inspection-mask-tools">
      <span><FileJson size={15}/> Protocol selection mask <small>All epochs in the full protocol query · includes other cells and filtered-out epochs · JSON v1 · whole protocol scope</small></span>
      <a className="button" href={busy?undefined:`/api/protocols/${id}/masks/export`} download={`recording-mask-${id.slice(0,8)}.json`} aria-disabled={busy} onClick={()=>{setError('');setMaskMessage('');}} title="Download all inclusion decisions for this protocol query as JSON"><Download size={14}/> Save JSON mask</a>
      <input ref={maskInput} type="file" accept=".json,application/json" hidden onChange={importMask}/>
      <button disabled={busy} onClick={()=>maskInput.current?.click()} title="Restore inclusion for the entire protocol query, regardless of the visible cell, filters or checkboxes"><Upload size={14}/> Import JSON mask</button>
      <details className="matlab-mask-import"><summary><Upload size={14}/> Import MATLAB UGM</summary><p>Use a UUID-based EpicTree UGM v1.1 mask from a completed MATLAB export. Only that export’s epochs are updated; tags, review and other epochs are preserved.</p>
        <div className="matlab-mask-fields"><label>Match completed MATLAB export<select aria-label="MATLAB mask export match" disabled={busy} value={matlabDataset} onChange={event=>setMatlabDataset(event.target.value)}><option value="">Automatically match exact epoch UUIDs</option>{matchingMatlabExports.map(item=><option key={item.dataset_uuid} value={item.dataset_uuid}>{item.name || item.dataset_uuid}{Number.isFinite(item.epoch_count)?` · ${number(item.epoch_count)} epochs`:''} · {item.dataset_uuid.slice(0,8)}</option>)}</select></label><input ref={matlabMaskInput} type="file" accept=".ugm" hidden onChange={event=>{setMatlabMaskFile(event.target.files?.[0] || null);setMatchingExports([]);event.target.value='';}}/><button disabled={busy} onClick={()=>matlabMaskInput.current?.click()}><Upload size={14}/> Choose UGM file</button><span className="matlab-mask-filename">{matlabMaskFile?.name || 'No file selected'}</span><button className="primary" disabled={busy||!matlabMaskFile||!protocol.query_revision} onClick={importMatlabMask}>Apply MATLAB mask</button></div>
        {matlabExports.error&&<p className="matlab-mask-history-error">Export history could not load. Automatic exact-UUID matching is still checked by the server. <button onClick={matlabExports.reload}>Retry history</button></p>}{matchingExports.length>0&&<p className="matlab-mask-history-error">Choose the completed export that produced this mask, then apply again.</p>}
      </details>
    </div>}
    </>}{!designMode&&maskMessage&&<div className="mask-result" role="status"><Check size={15}/><span>{maskMessage}</span><button className="icon-button" onClick={()=>setMaskMessage('')} aria-label="Dismiss mask result"><X size={14}/></button></div>}
    {error&&<div className="inspector-operation-error" role="alert">{error}<button className="icon-button" onClick={()=>setError('')} aria-label="Dismiss operation error"><X size={14}/></button></div>}
    <div ref={layoutRef} style={{gridTemplateColumns:paneSizes.columns,'--metadata-width':`${paneSizes.metadata}px`}} className={`inspection-layout resizable-layout ${treeOpen?'':'without-tree'} ${!designMode&&metadataOpen?'metadata-open':''} ${paneSizes.overlay?'metadata-overlay':''}`}>
      <NavigationLoadingNotice/>
      {treeOpen&&<aside className="inspection-tree">
        {!designMode&&<EpochListHeading treeMode={treeMode} onTreeMode={value=>{setTreeMode(value);if(value)changePane('tree',Math.max(420,paneSizes.tree));}}/>}
        {designMode?<TreeBuilder protocolId={id} queryString={protocolSearch} revision={revision}
            value={splits.split(',').filter(Boolean)} onChange={changeSplits}
            preview={tree.data} loading={tree.loading} error={tree.error}/>:treeMode?<>
          <div className="inspection-tree-edit"><span>{splits?`${splits.split(',').length} splits`:'Flat epoch list'}</span><button onClick={()=>setDesignMode(true)}><GitBranch size={13}/> Edit tree</button></div>
          <PagedTree presentation="tree" protocolId={id} filters={filters} splits={splits} revision={revision} selected={focused} initialNavigation={designNavigation} onNavigationChange={setDesignNavigation} onSelectEpoch={focusTreeEpoch} onMetadata={receiveTree} onStatus={setTreeStatus}/>
        </>:<>
          <div ref={epochListRef} className="tree-scroll" aria-label="Date, cell and epoch overview"><InspectionCellTree key={`${id}:${protocolSearch}`} cells={protocol.cells||[]} source={{kind:'protocol',protocolId:id,query:protocolSearch}} revision={revision} focused={focused} onFocus={focusTreeEpoch} targets={targets} setTargets={selectOverviewTargets} disabled={busy}/></div>
          {!metadataOpen&&<StableContent className="stable-tag-dock" scope={id} data={focusedEpoch} loading={!epoch.error&&(!!pendingNavigation||(!!focused&&(epoch.loading||!focusedEpoch)))} error={epoch.error} retry={epoch.reload}>{tagEntry}</StableContent>}
        </>}
      </aside>}
      {treeOpen&&<PaneDivider label={designMode?'Resize tree editor pane':'Resize epoch tree pane'} value={paneSizes.tree} min={180} max={paneSizes.treeMax} onChange={value=>changePane('tree',value)} onCommit={value=>savePane('tree',value)}/>}
      {designMode?<PagedTree presentation="columns" protocolId={id} filters={filters} splits={splits} revision={revision} design selected={focused} initialNavigation={designNavigation} onNavigationChange={setDesignNavigation} onMetadata={receiveTree} onStatus={setTreeStatus} onSelectEpoch={(uuid,info)=>{focusTreeEpoch(uuid,info);setTreeMode(false);setDesignMode(false);}}/>:<div className="inspection-detail"><StableContent scope={id} {...epoch} data={focusedEpoch} loading={!epoch.error&&(!!pendingNavigation||(!!focused&&(epoch.loading||!focusedEpoch)))} retry={epoch.reload}>{focusedEpoch?<>
        <div className="epoch-heading"><div>
          <h2>{datedCellLabel(focusedEpoch)}</h2>
          <p>{humanize(focusedEpoch.protocol_name?.split('.').at(-1)) || 'Protocol not recorded'} · Epoch {focusedEpoch.epoch_number ?? '—'} within block · {focusedEpoch.start_time?.split(/[T ]/)[1]?.slice(0,8) || 'Time not recorded'}</p>
        </div><div className="epoch-heading-badges">{onQC&&<button disabled={busy} onClick={()=>onQC(focusedEpoch.cell_uuid)} title="Open quality-control recordings linked to this cell">Cell QC</button>}<Badge kind={focusedEpoch.curation?.included===false?'neutral':'info'}>{focusedEpoch.curation?.included===false?'Excluded':'Included'}</Badge><Badge>{focusedEpoch.exports?.length?`${focusedEpoch.exports.length} saved exports`:'No saved export'}</Badge></div></div>
        <EpochNavigation position={focusedPageIndex<0?-1:offset+focusedPageIndex} total={rows.data?.total||0} loading={!!pendingNavigation||rows.loading} disabled={busy} onMove={moveEpoch}/>

        <Trace epoch={focusedEpoch} revision={revision}/>
        <p className="curation-help">Include / Exclude saves immediately for this protocol. With checkboxes selected, the action applies to those epochs; otherwise it applies to the focused epoch. Export uses included epochs in the protocol’s query and filters.</p>
        <div className="curation-bar">
          <button disabled={busy} onClick={()=>curate({included:true})}><Check size={14}/> Include {actionScope}</button>
          <button disabled={busy} onClick={()=>curate({included:false})}><X size={14}/> Exclude {actionScope}</button>
          {!metadataOpen&&(!treeOpen||treeMode)&&tagEntry}
        </div>
        {busy&&<p className="curation-progress" role="status">{operationMessage}</p>}
        <div className="tags"><span>Dataset-only tags:</span>
          {(focusedEpoch.curation?.tags||[]).map(t=><button key={t} disabled={busy} aria-label={`Remove tag ${t} from focused epoch only`} title="Remove from focused epoch only" onClick={()=>curate({tags_remove:[t]},'focused')}>{t}<X size={13}/></button>)}
          {!focusedEpoch.curation?.tags?.length&&<span>No tags</span>}
          {focusedEpoch.curation?.included===false&&<Badge kind="warning">Focused epoch excluded from export</Badge>}
        </div>
        <details className="optional-review"><summary>Optional review marker · {focusedEpoch.curation?.review_state==='approved'?'Reviewed':'Not marked'}</summary>
          <p>Use this marker if it helps your workflow. Included epochs can be exported without it; “reviewed only” is an optional export filter.</p>
          <button disabled={busy} onClick={()=>curate({review_state:!targets.length&&focusedEpoch.curation?.review_state==='approved'?'unreviewed':'approved'})}><Eye size={14}/>
            {targets.length?`Mark ${actionScope} reviewed`:focusedEpoch.curation?.review_state==='approved'?'Clear focused epoch review marker':'Mark focused epoch reviewed'}
          </button>
        </details>
      </>:<Empty title="Choose an epoch">Select an epoch from the tree to inspect its response and metadata.</Empty>}</StableContent></div>}
      {!designMode&&metadataOpen&&<><PaneDivider label="Resize metadata pane" value={paneSizes.metadata} min={240} max={paneSizes.metadataMax} reverse className={paneSizes.overlay?'metadata-overlay-divider':''} style={paneSizes.overlay?{right:paneSizes.metadata}:undefined} onChange={value=>changePane('metadata',value)} onCommit={value=>savePane('metadata',value)}/><StableContent className="stable-metadata" scope={id} data={focusedEpoch} loading={!epoch.error&&(!!pendingNavigation||(!!focused&&(epoch.loading||!focusedEpoch)))} error={epoch.error} retry={epoch.reload}><MetadataPanel tags={tagEntry} epoch={focusedEpoch} catalog={metadataCatalog} onClose={()=>toggleMetadata(false)} context={focusedEpoch&&<ScientificContext epoch={focusedEpoch}/>} connections={focusedEpoch&&<EpochConnections epoch={focusedEpoch} protocolName={humanize(protocol.definition?.name)}/>}/></StableContent></>}
    </div>
  </div>;
}

export default function Inspector(props){return <NavigationLoadingProvider><InspectorContent {...props}/></NavigationLoadingProvider>;}
