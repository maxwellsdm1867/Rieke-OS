import EpochViewer from './EpochViewer.jsx';
import SelectionMaskDialog from './SelectionMaskDialog.jsx';
import {NavigationLoadingProvider} from './NavigationLoading.jsx';
import {advanceEpochIntent, epochIntentAt, epochAtIntent} from '../epochNavigationIntent.js';
import {SourceEligibilityNotice} from './Common.jsx';
import {useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {GitBranch, Check, X, Eye, Upload, Download, FileJson} from 'lucide-react';
import {api, useResource, useEpochResource, useEpochPrefetch, number, humanize, resolveCurationTargets} from '../api.js';
import {Badge} from './Common.jsx';
import EpochConnections from './EpochConnections.jsx';
import './InspectorPolish.css';
import './MatlabMaskImport.css';
import EpochTags from './EpochTags.jsx';
import AnnotationTags from './AnnotationTags.jsx';
import TagExchangeControls from './TagExchangeControls.jsx';
import './Inspector.css';

import {inspectionSearches} from '../inspectionScope.js';
import {saveCurationSelection} from '../curationSelection.js';
import {useAnnotationReceipts} from '../useAnnotationReceipts.js';
import {fastAnnotationReceipt} from '../annotationReceipts.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {restoredEpochFocus} from '../workspaceNavigation.js';
import Trace from './TraceViewer.jsx';
import {inspectorPaneSizes, epochShortcutDirection, resourceForPath} from '../inspectorInteraction.js';
export {Trace};

function InspectorContent({protocol,initialEpochUuid=null,cellScope,filters,revision,structureRevision=revision,annotationChange=null,onChange,onBack,onImport,onStores,onExport,splitRecipe=['date','cell','block'],onSplitChange,initialNavigation=null,onSessionChange,onQC,onTagFilter,onFilterChange,toolbarTarget=null}) {
  const id=protocol.definition.protocol_uuid,annotationOrigin=useId();
  const requestedCellFocus=filters?.cell_uuid&&filters.cell_uuid!==cellScope?null:(cellScope || null);
  const [focusCell,setFocusCell]=useState(initialNavigation&&Object.hasOwn(initialNavigation,'focusCell')?initialNavigation.focusCell:requestedCellFocus);
  const [offset,setOffset]=useState(initialNavigation?.offset || 0), [focused,setFocused]=useState(()=>restoredEpochFocus(initialNavigation,initialEpochUuid)), [targets,setTargets]=useState([]);
  const [cellTagRequest,setCellTagRequest]=useState(null);
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
  useEffect(()=>{setMatlabMaskFile(null);setMatlabDataset('');setMatchingExports([]);},[id]);
  const [designMode,setDesignMode]=useState(initialNavigation?.designMode || false),[designPath,setDesignPath]=useState(initialNavigation?.designPath || []);
  const [designNavigation,setDesignNavigation]=useState(initialNavigation?.designNavigation||null);
  const changeSplits=useCallback(fields=>{setSplits(fields.join(','));setDesignPath([]);setDesignNavigation(null);},[]);
  const [collapseRequest,setCollapseRequest]=useState(0);
  const [treeOpen,setTreeOpen]=useState(initialNavigation?.treeOpen ?? true),[treeMode,setTreeMode]=useState(initialNavigation?.treeMode ?? false);
  const {protocol:protocolSearch,navigation:search}=inspectionSearches(filters,focusCell);
  const annotationState=useAnnotationReceipts({revision,structureRevision,change:annotationChange,origin:annotationOrigin,scope:JSON.stringify([id,protocolSearch,focusCell,pendingNavigation?.anchorUuid??null]),filters});
  const pageRevision=annotationState.authorityRevision;
  const rowsPath=`/protocols/${id}/epochs?${search}&${pendingNavigation?.anchorUuid?`anchor_uuid=${encodeURIComponent(pendingNavigation.anchorUuid)}`:`offset=${offset}`}&limit=60${focusCell?'':'&include_cells=true'}`;
  const loadedRows=useResource(rowsPath,pageRevision);
  const rows=resourceForPath(loadedRows,rowsPath);
  // The compact page receipt owns current curation authority and exact filtered
  // cell counts. A focused navigation page needs a separate all-cell receipt.
  const cellRows=useResource(focusCell?`/protocols/${id}/epochs?${protocolSearch}&offset=0&limit=1&include_cells=true`:null,pageRevision);
  const cellPage=focusCell?cellRows:rows;
  const queryRevision=rows.data?.query_revision,bindingVersion=rows.data?.expected_binding_version;
  const pageReady=!annotationState.dirty&&!rows.loading&&!rows.error&&typeof queryRevision==='string'&&!!queryRevision&&Number.isSafeInteger(bindingVersion)&&bindingVersion>=0;
  const cellsReady=pageReady&&!cellPage.loading&&!cellPage.error&&cellPage.data?.query_revision===queryRevision&&cellPage.data?.expected_binding_version===bindingVersion;
  const cellScopeKey=JSON.stringify([id,protocolSearch]),confirmedCells=useRef(null);
  const freshCells=cellsReady&&Array.isArray(cellPage.data?.cells)?cellPage.data.cells:null;
  useLayoutEffect(()=>{if(freshCells)confirmedCells.current={scope:cellScopeKey,cells:freshCells};},[cellScopeKey,freshCells]);
  // Keep expanded branches mounted during same-scope refresh, while their
  // controls remain disabled until both authority receipts agree again.
  const viewCells=freshCells||(confirmedCells.current?.scope===cellScopeKey?confirmedCells.current.cells:[]);
  const cellRevisionError=pageReady&&!cellPage.loading&&cellPage.data&&!cellsReady;

  const [treePage,setTreePage]=useState(null);
  const [treeStatus,setTreeStatus]=useState({loading:true,error:null});
  const tree={data:treePage,...treeStatus};
  const receiveTree=useCallback(data=>setTreePage(data),[]);
  useEffect(()=>setTreePage(null),[id,protocolSearch,splits,pageRevision]);
  const layoutRef=useRef(null),[layoutWidth,setLayoutWidth]=useState(1100);
  const [paneWidths,setPaneWidths]=useState(()=>{try{return JSON.parse(localStorage.getItem('workspace.inspector.paneWidths')||'{}');}catch{return {};}});
  const paneSizes=inspectorPaneSizes(layoutWidth,paneWidths||{},treeOpen,!designMode&&metadataOpen);
  const changePane=(key,value)=>setPaneWidths(old=>({...old,[key]:value}));
  const savePane=(key,value)=>{setPaneWidths(old=>{const next={...old,[key]:value};try{localStorage.setItem('workspace.inspector.paneWidths',JSON.stringify(next));}catch{}return next;});};
  useEffect(()=>{const element=layoutRef.current;if(!element)return;const observer=new ResizeObserver(entries=>setLayoutWidth(entries[0].contentRect.width));observer.observe(element);return()=>observer.disconnect();},[]);
  const epoch=useEpochResource(focused?`/epochs/${focused}?protocol_uuid=${id}`:null,annotationState.epochRevision,80);
  const focusedEpoch=useMemo(()=>epoch.data?.epoch_uuid===focused?annotationState.apply(epoch.data):null,[epoch.data,focused,annotationState.apply]);
  const neighborIndex=rows.data?.epochs?.findIndex(row=>row.epoch_uuid===focused)??-1;
  useEpochPrefetch(!annotationState.dirty&&!epoch.loading&&!rows.loading&&neighborIndex>=0?[rows.data.epochs[neighborIndex+1],rows.data.epochs[neighborIndex-1]].filter(Boolean).map(row=>`/epochs/${row.epoch_uuid}?protocol_uuid=${id}`):[],annotationState.epochRevision);
  const metadataCatalog=useResource(metadataOpen&&!designMode?'/metadata/fields':null,structureRevision);
  const scopeIdentity=JSON.stringify([id,requestedCellFocus,protocolSearch,initialEpochUuid]);
  const curationIdentity=JSON.stringify([id,protocolSearch,focusCell,protocol.query_revision,protocol.expected_binding_version??0,queryRevision,bindingVersion,revision,focused,targets]);
  const curationGeneration=useRef(0),curationRequest=useRef(null),mounted=useRef(false),committedCurationIdentity=useRef(null);
  const changedCallback=useRef(onChange);changedCallback.current=onChange;
  useLayoutEffect(()=>{
    mounted.current=true;committedCurationIdentity.current=curationIdentity;curationGeneration.current++;
    return()=>{mounted.current=false;curationGeneration.current++;curationRequest.current?.abort();};
  },[curationIdentity]);
  const previousScope=useRef({key:scopeIdentity,id,initialEpochUuid});
  useEffect(()=>{if(previousScope.current.key===scopeIdentity)return;const requested=previousScope.current.id!==id||previousScope.current.initialEpochUuid!==initialEpochUuid;previousScope.current={key:scopeIdentity,id,initialEpochUuid};setCellTagRequest(null);navigationIntent.current=null;anchorSteps.current=0;setFocusCell(requestedCellFocus);setOffset(0);setFocused(requested?initialEpochUuid:null);setTargets([]);setPendingNavigation(null);setDesignNavigation(null);},[scopeIdentity,id,requestedCellFocus,protocolSearch,initialEpochUuid]);
  useEffect(()=>{onSessionChange?.({focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation});},[focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation,onSessionChange]);

  function clearCellFocus(){navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);setTargets([]);setPendingNavigation(null);}
  function selectOverviewTargets(update){
    // This overview spans every matching cell, including when entered from a cell shortcut.
    if(focusCell){navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);setPendingNavigation(null);}
    setTargets(update);
  }
  function focusTreeEpoch(uuid,epochInfo){setCellTagRequest(null);toggleMetadata(true);
    if(busy)return;
    if(focusCell&&epochInfo?.cell_uuid!==focusCell)clearCellFocus();
    annotationState.flushAuthority();navigationIntent.current=null;anchorSteps.current=0;setFocused(uuid);setPendingNavigation({anchorUuid:uuid,direction:0});
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
  async function curate(changes, scope='selection', epochUuid=null) {
    if(busy||curationRequest.current||!mounted.current)return;
    const uuids=epochUuid?[epochUuid]:resolveCurationTargets(focused,targets,scope);
    if(!uuids.length)return;
    if(!pageReady){setError('Refresh this dataset before saving.');return;}
    const controller=new AbortController(),generation=curationGeneration.current;
    curationRequest.current=controller;
    const isCurrent=()=>mounted.current&&generation===curationGeneration.current&&committedCurationIdentity.current===curationIdentity;
    setBusy(true);setError('');setOperationMessage('Saving curation changes…');
    try {
      await saveCurationSelection({request:api,protocolId:id,queryRevision,
        bindingVersion,epochUuids:uuids,changes,
        selectionScope:{filters:filters||{},cell_uuid:epochUuid?null:focusCell},
        signal:controller.signal,isCurrent});
      if(isCurrent())setTag('');
      if(mounted.current)changedCallback.current?.({kind:'curation',protocolId:id});
    }catch(e){if(mounted.current)setError(e.message);}finally{
      if(curationRequest.current===controller)curationRequest.current=null;
      if(mounted.current)setBusy(false);
    }
  }
  async function saveMask() {
    if(busy)return;
    setBusy(true);setError('');setMaskMessage('');setOperationMessage('Saving protocol selection mask…');
    try {
      const mask=await api(`/protocols/${id}/masks/export`);
      const blob=new Blob([JSON.stringify(mask,null,2)+'\n'],{type:'application/json'});
      const url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download=`recording-mask-${id.slice(0,8)}.json`;
      document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      setMaskMessage('Selection mask saved for this protocol query. The JSON contains epoch identities and inclusion decisions.');
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
      const result=await api(`/protocols/${id}/masks/import`,{method:'POST',body:{mask,query_revision:queryRevision}});
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
      const body=new FormData();body.append('file',matlabMaskFile);body.append('query_revision',queryRevision);
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
  const tagNavigationIdentity=JSON.stringify([id,protocolSearch,focusCell,focused,targets,structureRevision]);
  const committedTagNavigation=useRef(null);
  useLayoutEffect(()=>{
    committedTagNavigation.current={identity:tagNavigationIdentity,busy,pendingNavigation,navigate(direction,afterSave){
      if((afterSave||annotationState.dirty)&&focused){
        annotationState.flushAuthority();
        // A tag can change membership in the active filter. Locate the current
        // epoch against fresh server authority before deciding which comes next.
        navigationIntent.current=null;anchorSteps.current=0;
        setPendingNavigation({anchorUuid:focused,direction});
      }else moveEpoch(direction);
      setEpochTagFocus(value=>value+1);
    }};
  });
  useLayoutEffect(()=>()=>{committedTagNavigation.current=null;},[]);
  function navigateAndTag(direction,{afterSave=false}={}){
    const current=committedTagNavigation.current;
    if(!current||current.identity!==tagNavigationIdentity||current.busy||current.pendingNavigation)return;
    current.navigate(direction,afterSave);
  }
  function openTagsForSelection(){
    if(!focused&&targets.length)focusTreeEpoch(targets[0]);
    toggleMetadata(true);setTagFocus(value=>value+1);
  }
  const epochListRef=useRef(null);
  const actionScope=targets.length?`${targets.length} selected`:'focused epoch';
  const annotationChanged=(result,confirmed)=>{
    const safe=fastAnnotationReceipt(confirmed)&&committedTagNavigation.current?.identity===tagNavigationIdentity;
    if(onChange)onChange({kind:'annotations',protocolId:id,...(safe?{origin:annotationOrigin,confirmed}:{})});
    else{epoch.reload();loadedRows.reload();}
  };
  const tagEntry=focusedEpoch&&<AnnotationTags reconcileReceipt={!!onChange} refreshWithEpoch={!!onChange} epoch={focusedEpoch} revision={revision} disabled={busy||epoch.loading||!!pendingNavigation} onChange={annotationChanged} onFilter={onTagFilter} focusRequest={tagFocus} targetScope={cellTagRequest?'cell':targets.length?'selected':'epoch'} epochFocusRequest={epochTagFocus} onNavigateEpoch={navigateAndTag} selectedEpochs={targets} tools={!cellTagRequest&&!targets.length&&<TagExchangeControls epoch={focusedEpoch} disabled={busy} onChanged={annotationChanged}/>}><EpochTags value={tag} onValue={setTag} onAdd={value=>curate({tags_add:[value]})} onRemove={value=>curate({tags_remove:[value]},'focused')} selectedTags={focusedEpoch.curation?.tags||[]} busy={busy||!pageReady} scope={`dataset · ${actionScope}`} revision={revision}/></AnnotationTags>;
  return <EpochViewer viewFilters={filters} onViewFilters={onFilterChange} filterRevision={revision} filterDisabled={busy} className={designMode?'tree-design':'epoch-inspector-mode'} ariaLabel={designMode?'Tree overview workspace':'Epoch inspection workspace. Tab next epoch, Shift+Tab previous epoch; W/S also navigate.'} onKeyDown={epochKeys}
    toolbar={{portalTarget:toolbarTarget,treeControlsInPane:true,designMode:designMode,onBrowse:()=>{setDesignMode(false);setTreeMode(false);setTreeOpen(true);},onDesign:()=>{setDesignMode(true);setTreeOpen(true);setTreeMode(true);},onTags:openTagsForSelection,metadataOpen:metadataOpen,onToggleMetadata:()=>toggleMetadata(!metadataOpen),actions:[
        {label:treeOpen?(designMode?'Hide tree editor':'Hide epoch list'):(designMode?'Show tree editor':'Show epoch list'),icon:GitBranch,run:()=>setTreeOpen(value=>!value)},
        !designMode&&{label:'Import mask file…',icon:FileJson,run:()=>setMasksOpen(true),disabled:busy},
        !designMode&&onImport&&{label:'Add data store',icon:Upload,run:onImport,disabled:busy},
      ]}} toolbarChildren={<>
      {focusCell&&<button className="inspection-focus-chip" disabled={busy} onClick={clearCellFocus} title="Clear cell focus and navigate all matching cells">{datedCellLabel(protocol.cells?.find(cell=>cell.cell_uuid===focusCell)||focusedEpoch||{},true)} <X size={12}/></button>}
    </>} before={<>
    <SourceEligibilityNotice eligibility={protocol.source_eligibility} onStores={onStores}/>
    {!designMode&&<>

    {masksOpen&&<SelectionMaskDialog busy={busy} onClose={()=>setMasksOpen(false)}>
      <h3>Import MATLAB UGM</h3>
      <p>The completed MATLAB export is matched automatically by exact epoch UUIDs. Only that export’s inclusion decisions are updated.</p>
      <input ref={matlabMaskInput} type="file" accept=".ugm" hidden onChange={event=>{setMatlabMaskFile(event.target.files?.[0] || null);setMatlabDataset('');setMatchingExports([]);event.target.value='';}}/>
      <button className="tag-file-picker" disabled={busy} onClick={()=>matlabMaskInput.current?.click()}><Upload size={20}/><span><strong>{matlabMaskFile?.name || 'Choose UGM file'}</strong><small>EpicTree selection mask · up to 32 MiB</small></span></button>
      {matchingExports.length>0&&<label>More than one export matches<select aria-label="MATLAB mask export match" disabled={busy} value={matlabDataset} onChange={event=>setMatlabDataset(event.target.value)}><option value="">Choose the export that produced this mask</option>{matchingExports.map(item=><option key={item.dataset_uuid} value={item.dataset_uuid}>{item.name || item.dataset_uuid}{Number.isFinite(item.epoch_count)?` · ${number(item.epoch_count)} epochs`:''} · {item.dataset_uuid.slice(0,8)}</option>)}</select></label>}
      <p><button className="primary" disabled={busy||!matlabMaskFile||!pageReady||(matchingExports.length>0&&!matlabDataset)} onClick={importMatlabMask}>{busy?'Applying…':'Apply MATLAB mask'}</button></p>
      <section className="selection-mask-json"><h3>Protocol JSON mask</h3><p>Save or restore inclusion decisions for the full protocol query, including cells outside the current view.</p>
        <button disabled={busy} onClick={saveMask}><Download size={14}/> Save JSON mask</button>{' '}
        <input ref={maskInput} type="file" accept=".json,application/json" hidden onChange={importMask}/>
        <button disabled={busy} onClick={()=>maskInput.current?.click()}><Upload size={14}/> Import JSON mask</button>
      </section>
      {error&&<p className="tag-exchange-error" role="alert">{error}</p>}
      {maskMessage&&<p className="tag-import-success" role="status"><Check size={15}/>{maskMessage}</p>}
    </SelectionMaskDialog>}
    </>}{!designMode&&maskMessage&&<div className="mask-result" role="status"><Check size={15}/><span>{maskMessage}</span><button className="icon-button" onClick={()=>setMaskMessage('')} aria-label="Dismiss mask result"><X size={14}/></button></div>}
    {(cellPage.error||cellRevisionError)&&<div className="inspector-operation-error" role="alert">{cellPage.error||'Dataset changed while loading the cell list. Refresh before selecting epochs.'}<button onClick={()=>{loadedRows.reload();cellRows.reload();}}>Refresh epoch list</button></div>}
    {error&&<div className="inspector-operation-error" role="alert">{error}<button className="icon-button" onClick={()=>setError('')} aria-label="Dismiss operation error"><X size={14}/></button></div>}
</>}
    layout={{layoutRef,sizes:paneSizes,treeOpen,metadataOpen,onResize:changePane,onResizeCommit:savePane}} designMode={designMode}
    builder={{protocolId:id,queryString:protocolSearch,revision:revision,value:splits.split(',').filter(Boolean),onChange:changeSplits,preview:tree.data,loading:tree.loading,error:tree.error}} columnTree={{collapseRequest:collapseRequest,externalCollapseControl:true,actionsDisabled:busy||!cellsReady,inclusionForEpoch:annotationState.apply,onToggleInclusion:(item,included)=>curate({included},'focused',item.epoch_uuid),cells:viewCells,selectedEpochs:targets,setSelectedEpochs:selectOverviewTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);setTargets([]);toggleMetadata(true);setDesignMode(false);setCellTagRequest((protocol.cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},presentation:"columns",protocolId:id,filters:filters,splits:splits,revision:pageRevision,design:true,selected:focused,initialNavigation:designNavigation,onNavigationChange:setDesignNavigation,onMetadata:receiveTree,onStatus:setTreeStatus,onSelectEpoch:focusTreeEpoch}} treePane={{treeMode:treeMode,onTreeMode:value=>{setTreeMode(value);if(value)changePane('tree',Math.max(420,paneSizes.tree));},onDesign:()=>{setDesignMode(true);setTreeOpen(true);setTreeMode(true);},designDisabled:busy,collapseRequest:collapseRequest,onCollapse:()=>setCollapseRequest(value=>value+1),treeProps:{actionsDisabled:busy||!cellsReady,inclusionForEpoch:annotationState.apply,onToggleInclusion:(item,included)=>curate({included},'focused',item.epoch_uuid),cells:viewCells,selectedEpochs:targets,setSelectedEpochs:selectOverviewTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);setTargets([]);toggleMetadata(true);setDesignMode(false);setCellTagRequest((protocol.cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},protocolId:id,filters,splits,revision:pageRevision,selected:focused,initialNavigation:designNavigation,onNavigationChange:setDesignNavigation,onSelectEpoch:focusTreeEpoch,onMetadata:receiveTree,onStatus:setTreeStatus},listRef:epochListRef,listKey:`${id}:${protocolSearch}`,listProps:{cells:viewCells||[],source:{kind:'protocol',protocolId:id,query:protocolSearch,queryRevision},revision:pageRevision,inclusionForEpoch:annotationState.apply,focused:cellTagRequest?null:focused,onFocus:focusTreeEpoch,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cell,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);setTargets([]);toggleMetadata(true);setCellTagRequest(cell);},targets,setTargets:selectOverviewTargets,disabled:busy||!cellsReady,onToggleInclusion:(epoch,included)=>curate({included},'focused',epoch.epoch_uuid)}}}
    resource={{scope:id,...epoch,loading:!epoch.error&&(!!pendingNavigation||(!!focused&&(epoch.loading||!focusedEpoch))),retry:epoch.reload}}
    epoch={focusedEpoch} targets={targets} navigation={{position:focusedPageIndex<0?-1:offset+focusedPageIndex,total:rows.data?.total||0,loading:!!pendingNavigation||rows.loading,disabled:busy,onMove:moveEpoch}}
    traceRevision={annotationState.epochRevision} inclusion={{disabled:busy||!pageReady,scope:'pinned dataset',onToggle:(epoch,included)=>curate({included},'focused',epoch.epoch_uuid)}} detailDisabled={busy} onQC={onQC} tags={tagEntry}
    detailExtras={focusedEpoch&&<>        {busy&&<p className="curation-progress" role="status">{operationMessage}</p>}
        <div className="tags"><span>Dataset-only tags:</span>
          {(focusedEpoch.curation?.tags||[]).map(t=><button key={t} disabled={busy} aria-label={`Remove tag ${t} from focused epoch only`} title="Remove from focused epoch only" onClick={()=>curate({tags_remove:[t]},'focused')}>{t}<X size={13}/></button>)}
          {!focusedEpoch.curation?.tags?.length&&<span>No tags</span>}
          {focusedEpoch.curation?.included===false&&<Badge kind="warning">Excluded from analysis · recording retained</Badge>}
        </div>
        <details className="optional-review"><summary>Optional review marker · {focusedEpoch.curation?.review_state==='approved'?'Reviewed':'Not marked'}</summary>
          <p>Use this marker if it helps your workflow. Included epochs can be exported without it; “reviewed only” is an optional export filter.</p>
          <button disabled={busy} onClick={()=>curate({review_state:!targets.length&&focusedEpoch.curation?.review_state==='approved'?'unreviewed':'approved'})}><Eye size={14}/>
            {targets.length?`Mark ${actionScope} reviewed`:focusedEpoch.curation?.review_state==='approved'?'Clear focused epoch review marker':'Mark focused epoch reviewed'}
          </button>
        </details></>} metadata={{selectionCell:cellTagRequest,selectedEpochs:targets,onClearSelection:()=>setTargets([]),catalog:metadataCatalog,onClose:()=>toggleMetadata(false),connections:focusedEpoch&&<EpochConnections epoch={focusedEpoch} protocolName={humanize(protocol.definition?.name)}/>}}/>;
}

export default function Inspector(props){return <NavigationLoadingProvider><InspectorContent {...props}/></NavigationLoadingProvider>;}
