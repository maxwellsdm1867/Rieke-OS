import {useTreeBranchReads} from '../tree-ancestors/treeBranchReads.jsx';
import {createPortal} from 'react-dom';
import {useUnmountGuard} from '../useUnmountGuard.js';
import EpochViewer from './EpochViewer.jsx';
import SelectionMaskDialog from '../exports/ui/SelectionMaskDialog.jsx';
import {NavigationLoadingProvider} from './NavigationLoading.jsx';
import {advanceEpochIntent, epochIntentAt, epochAtIntent} from '../epochNavigationIntent.js';
import {SourceEligibilityNotice} from './Common.jsx';
import {useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {GitBranch, Check, X, Eye, Upload, Download, FileJson} from 'lucide-react';
import {api, useResource, useEpochResource, useEpochPrefetch, number, humanize, resolveCurationTargets} from '../api.js';
import {Badge} from './Common.jsx';
import EpochConnections from './EpochConnections.jsx';
import './InspectorPolish.css';
import EpochTags from '../annotations/ui/EpochTags.jsx';
import IncomingEpochReview from '../incoming-workbench/ui/IncomingEpochReview.jsx';
import {selectedViewFilters} from '../incoming-workbench/selectedIncomingWorkflow.js';
import IncomingSelectionTools from '../incoming-workbench/ui/IncomingSelectionTools.jsx';
import IncomingTagSummary from '../incoming-workbench/ui/IncomingTagSummary.jsx';
import {incomingTagSummary} from '../incoming-workbench/incomingTagSummary.js';
import AnnotationTags from '../annotations/ui/AnnotationTags.jsx';
import TagExchangeControls from '../annotations/ui/TagExchangeControls.jsx';
import './Inspector.css';

import {frozenReadPath,frozenReadQuery,frozenPresentationScope} from '../frozenReadContext.js';
export const FROZEN_CANDIDATE_INSPECTOR_SUPPORTED=Trace.supportsFrozenReadContext===true;

import {inspectionSearches} from '../inspectionScope.js';
import {saveCurationSelection} from '../curationSelection.js';
import {useAnnotationReceipts} from '../annotations/useAnnotationReceipts.js';
import {fastAnnotationReceipt} from '../annotations/annotationReceipts.js';
import {datedCellLabel} from '../recording-import/recordingIdentity.js';
import {restoredEpochFocus} from '../workspace-navigation/workspaceNavigation.js';
import Trace from '../traces/ui/TraceViewer.jsx';
import {inspectorPaneSizes, epochShortcutDirection, resourceForPath} from '../inspectorInteraction.js';
export {Trace};

function InspectorContent({protocol,projectId,initialEpochUuid=null,cellScope,filters:baseFilters,revision,structureRevision=revision,annotationChange=null,onChange,onBack,onImport,onStores,onExport,splitRecipe=['date','cell','block'],onSplitChange,initialNavigation=null,onSessionChange,onQC,onTagFilter,onFilterChange,toolbarTarget=null,readContext=null,onSelectionChange,onReviewDecision,draftSelection=null,draftSelectionTarget=null,readPaused=false,browseRequest=0}) {
  const id=protocol.definition.protocol_uuid,annotationOrigin=useId();
  const [selectedView,setSelectedView]=useState(null);
  const filters=selectedView?.filters||baseFilters;
  const selectionScope=JSON.stringify([readContext?.cohort_key||readContext?.root,id,baseFilters,cellScope]);
  const requestedCellFocus=filters?.cell_uuid&&filters.cell_uuid!==cellScope?null:(cellScope || null);
  const [focusCell,setFocusCell]=useState(initialNavigation&&Object.hasOwn(initialNavigation,'focusCell')?initialNavigation.focusCell:requestedCellFocus);
  const [offset,setOffset]=useState(initialNavigation?.offset || 0), [focused,setFocused]=useState(()=>restoredEpochFocus(initialNavigation,initialEpochUuid)), [localTargets,setTargets]=useState([]);
  const targets=readContext&&draftSelection?draftSelection.selected||[]:localTargets;
  const [cellTagRequest,setCellTagRequest]=useState(null);
  const [annotationDrafts,setAnnotationDrafts]=useState(initialNavigation?.annotationDrafts||{});
  const rememberAnnotationDraft=useCallback((key,value)=>setAnnotationDrafts(previous=>{if(previous[key]===value)return previous;const next={...previous};if(value)next[key]=value;else delete next[key];return next;}),[]);
  const [tagFocus,setTagFocus]=useState(0),[epochTagFocus,setEpochTagFocus]=useState(0);
  const [tag,setTag]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useUnmountGuard(!!tag.trim(),'Save or clear the unfinished epoch tag before unmounting.');
  const [operationMessage,setOperationMessage]=useState(''),[maskMessage,setMaskMessage]=useState('');
  const maskInput=useRef(null);
  const [pendingNavigation,setPendingNavigation]=useState(null);
  const [listNavigationRequest,setListNavigationRequest]=useState(0);
  const navigationIntent=useRef(null),anchorSteps=useRef(0),selectionNavigation=useRef(null);
  function selectEpoch(uuid){setListNavigationRequest(value=>value+1);navigationIntent.current=null;anchorSteps.current=0;setPendingNavigation(null);setFocused(uuid);}
  const externalSplitKey=splitRecipe.join(',');
  const previousExternalSplit=useRef(externalSplitKey);
  const [splits,setSplits]=useState(externalSplitKey);
  const [masksOpen,setMasksOpen]=useState(false);
  const [metadataOpen,setMetadataOpen]=useState(()=>{try{const saved=localStorage.getItem('workspace.inspector.metadata');return saved===null?window.innerWidth>=1350:saved==='true';}catch{return true;}});
  function toggleMetadata(next){setMetadataOpen(next);try{localStorage.setItem('workspace.inspector.metadata',String(next));}catch{}}
  const [designMode,setDesignMode]=useState(initialNavigation?.designMode || false),[designPath,setDesignPath]=useState(initialNavigation?.designPath || []);
  const [designNavigation,setDesignNavigation]=useState(initialNavigation?.designNavigation||null);
  const [listNavigation,setListNavigation]=useState(initialNavigation?.listNavigation||null);
  const changeSplits=useCallback(fields=>{setSplits(fields.join(','));setDesignPath([]);setDesignNavigation(null);},[]);
  const [collapseRequest,setCollapseRequest]=useState(0);
  const [treeOpen,setTreeOpen]=useState(initialNavigation?.treeOpen ?? true),[treeMode,setTreeMode]=useState(initialNavigation?.treeMode ?? false);
  // A tab reselection is a view intent, not a new recording authority. Keep
  // mounted rows, scroll, focus and trace; only leave the tree designer.
  const previousBrowseRequest=useRef(browseRequest);
  useEffect(()=>{
    if(previousBrowseRequest.current===browseRequest)return;
    previousBrowseRequest.current=browseRequest;
    setDesignMode(false);setTreeMode(false);setTreeOpen(true);
  },[browseRequest]);
  const queries=inspectionSearches(filters,focusCell);
  const protocolSearch=frozenReadQuery(readContext,queries.protocol),search=frozenReadQuery(readContext,queries.navigation);
  const readRoot=readContext?.root||`/protocols/${id}`;
  const presentationScope=frozenPresentationScope(readContext,id,protocolSearch);
  const preserveCandidateView=typeof readContext?.cohort_key==='string'&&!!readContext.cohort_key;
  function selectTargets(value){const next=typeof value==='function'?value(targets):value;if(next.length>1000){setError('Select at most 1000 epochs.');return;}setTargets(next);onSelectionChange?.([...next]);if(selectedView)setSelectedView(next.length?{filters:selectedViewFilters(baseFilters,next)}:null);}
  const annotationState=useAnnotationReceipts({revision,structureRevision,change:annotationChange,origin:annotationOrigin,scope:JSON.stringify([readRoot,id,protocolSearch,focusCell]),filters});
  const pageRevision=annotationState.authorityRevision;
  const rowsPath=`${readRoot}/epochs?${search}&${pendingNavigation?.anchorUuid?`anchor_uuid=${encodeURIComponent(pendingNavigation.anchorUuid)}`:`offset=${offset}`}&limit=60${focusCell?'':'&include_cells=true'}`;
  const loadedRows=useResource(rowsPath,pageRevision,0,{paused:readPaused});
  const rows=resourceForPath(loadedRows,rowsPath);
  // The compact page receipt owns current curation authority and exact filtered
  // cell counts. A focused navigation page needs a separate all-cell receipt.
  const cellRows=useResource(focusCell?`${readRoot}/epochs?${protocolSearch}&offset=0&limit=1&include_cells=true`:null,pageRevision,0,{paused:readPaused});
  const cellPage=focusCell?cellRows:rows;
  const queryRevision=rows.data?.query_revision,bindingVersion=rows.data?.expected_binding_version;
  const pageReady=!readPaused&&!annotationState.dirty&&!rows.loading&&!rows.error&&typeof queryRevision==='string'&&!!queryRevision&&Number.isSafeInteger(bindingVersion)&&bindingVersion>=0;
  const cellsReady=pageReady&&!cellPage.loading&&!cellPage.error&&cellPage.data?.query_revision===queryRevision&&cellPage.data?.expected_binding_version===bindingVersion;
  const cellScopeKey=JSON.stringify([readRoot,id,protocolSearch]),confirmedCells=useRef(null);
  const navigationReadKey=JSON.stringify([cellScopeKey,focusCell,pageRevision,revision,structureRevision,protocol.query_revision,protocol.expected_binding_version]);
  const committedNavigationReadKey=useRef(null);
  useLayoutEffect(()=>{committedNavigationReadKey.current=navigationReadKey;},[navigationReadKey]);
  const freshCells=cellsReady&&Array.isArray(cellPage.data?.cells)?cellPage.data.cells:null;
  useLayoutEffect(()=>{if(freshCells)confirmedCells.current={scope:cellScopeKey,presentationScope,key:navigationReadKey,cells:freshCells,queryRevision,bindingVersion};},[cellScopeKey,presentationScope,navigationReadKey,freshCells,queryRevision,bindingVersion]);
  // Keep expanded branches mounted during same-scope refresh, while their
  // controls remain disabled until both authority receipts agree again.
  const incomingTags=useMemo(()=>readContext&&pageReady?incomingTagSummary(rows.data):null,[readContext,pageReady,rows.data]);
  const retainedCells=freshCells||(confirmedCells.current?.presentationScope===presentationScope?confirmedCells.current.cells:[]);
  const viewCells=useMemo(()=>readContext&&incomingTags?retainedCells.map(cell=>incomingTags.cellTags[cell.cell_uuid]?{...cell,annotations:{...cell.annotations,cell_tags:incomingTags.cellTags[cell.cell_uuid]}}:cell):retainedCells,[readContext,incomingTags,retainedCells]);
  const cellRevisionError=pageReady&&!cellPage.loading&&cellPage.data&&!cellsReady;
  // A navigation request does not change the membership of already loaded cell
  // pages. Retain their read authority only inside this exact committed scope.
  // Save, range-selection and inclusion controls still require cellsReady.
  const navigatingSameScope=!!pendingNavigation&&rows.loading&&!rows.error&&!annotationState.dirty&&confirmedCells.current?.key===navigationReadKey;
  const navigationReady=cellsReady||navigatingSameScope;
  const listQueryRevision=navigatingSameScope?confirmedCells.current.queryRevision:(queryRevision??(preserveCandidateView&&protocol.query_revision===readContext.candidate_scope_revision?protocol.query_revision:undefined));

  const [treeReceipt,setTreeReceipt]=useState(null);
  const treePage=treeReceipt?.data;
  const [treeStatus,setTreeStatus]=useState({loading:true,error:null});
  const treeReadOwner=useTreeBranchReads();
  // A focus locator and its resulting offset page share the last confirmed
  // selection authority. They do not make tag/inclusion receipts writable.
  const selectionReceipt=cellsReady?{key:navigationReadKey,queryRevision,bindingVersion}:confirmedCells.current;
  const selectionNavigationPending=selectionNavigation.current===navigationReadKey&&rows.loading&&!rows.error;
  useLayoutEffect(()=>{if(rows.error||!rows.loading&&!pendingNavigation)selectionNavigation.current=null;},[rows.error,rows.loading,pendingNavigation]);
  // Scope exists during render; its cache activates in the provider layout effect.
  // Initiation/completion still check the captured owner live via current().
  const selectionOwnerReady=!treeReadOwner||treeReadOwner.available;
  const selectionAvailable=!readPaused&&!annotationState.dirty&&!busy&&!draftSelection?.disabled&&selectionOwnerReady&&
    selectionReceipt?.key===navigationReadKey&&(cellsReady||selectionNavigationPending)&&!cellPage.error;
  const selectionIdentity=JSON.stringify([navigationReadKey,selectionReceipt?.queryRevision,selectionReceipt?.bindingVersion,treeReadOwner?.identity??null]);
  const treeSelectionAuthority={identity:selectionIdentity,available:!!selectionAvailable,
    current:()=>committedNavigationReadKey.current===navigationReadKey&&(!treeReadOwner||treeReadOwner.available&&treeReadOwner.active())};
  const designAuthorityKey=JSON.stringify([treeReadOwner?.identity,id,protocolSearch,splits,pageRevision,readContext,protocol.query_revision,protocol.expected_binding_version]);
  const treeReceiptCurrent=treeReceipt?.scope===designAuthorityKey;
  const designFocusReady=!focused||treeReceiptCurrent&&(treeReceipt.focused===focused||treePage?.epochs?.some(row=>row.epoch_uuid===focused));
  const designBlocked=designMode&&(treeStatus.scope!==designAuthorityKey||treeStatus.loading||!!treeStatus.error||!designFocusReady||treeReadOwner&&!treeReadOwner.active());
  const designSelectionAuthority={...treeSelectionAuthority,identity:JSON.stringify([selectionIdentity,designAuthorityKey,treeReceiptCurrent?treePage?.revision:null]),
    available:!!(selectionAvailable&&treeReceiptCurrent&&treePage?.revision&&treeStatus.scope===designAuthorityKey&&!treeStatus.error)};
  const receiveTreeStatus=value=>setTreeStatus({...value,scope:designAuthorityKey});
  function openTreeDesign(){setTreeStatus({loading:true,error:null});setDesignMode(true);setTreeOpen(true);setTreeMode(true);}
  const tree={data:treePage,...treeStatus};
  const receiveTree=useCallback(data=>setTreeReceipt({scope:designAuthorityKey,focused,data}),[designAuthorityKey,focused]);
  useEffect(()=>setTreeReceipt(null),[id,protocolSearch,splits,pageRevision]);
  const layoutRef=useRef(null),[layoutWidth,setLayoutWidth]=useState(1100);
  const [paneWidths,setPaneWidths]=useState(()=>{try{return JSON.parse(localStorage.getItem('workspace.inspector.paneWidths')||'{}');}catch{return {};}});
  const paneSizes=inspectorPaneSizes(layoutWidth,paneWidths||{},treeOpen,!designMode&&metadataOpen);
  const changePane=(key,value)=>setPaneWidths(old=>({...old,[key]:value}));
  const savePane=(key,value)=>{setPaneWidths(old=>{const next={...old,[key]:value};try{localStorage.setItem('workspace.inspector.paneWidths',JSON.stringify(next));}catch{}return next;});};
  useEffect(()=>{const element=layoutRef.current;if(!element)return;const observer=new ResizeObserver(entries=>setLayoutWidth(entries[0].contentRect.width));observer.observe(element);return()=>observer.disconnect();},[]);
  const epoch=useResource(focused?(readContext?frozenReadPath(readContext,id,`/epochs/${focused}`):`/epochs/${focused}?protocol_uuid=${id}`):null,annotationState.epochRevision,80,{cache:!readContext,warmEpoch:!readContext,paused:readPaused});
  const focusedEpoch=useMemo(()=>(!readContext&&!filters?.metadata_predicate||pageReady&&rows.data?.epochs?.some(row=>row.epoch_uuid===focused))&&epoch.data?.epoch_uuid===focused?annotationState.apply(epoch.data):null,[readContext,filters?.metadata_predicate,pageReady,rows.data,epoch.data,focused,annotationState.apply]);
  const neighborIndex=rows.data?.epochs?.findIndex(row=>row.epoch_uuid===focused)??-1;
  useEpochPrefetch(!readContext&&!annotationState.dirty&&!epoch.loading&&!rows.loading&&neighborIndex>=0?[rows.data.epochs[neighborIndex+1],rows.data.epochs[neighborIndex-1]].filter(Boolean).map(row=>readContext?frozenReadPath(readContext,id,`/epochs/${row.epoch_uuid}`):`/epochs/${row.epoch_uuid}?protocol_uuid=${id}`):[],annotationState.epochRevision);
  const metadataCatalog=useResource(metadataOpen&&!designMode?'/metadata/fields':null,structureRevision);
  const scopeIdentity=JSON.stringify([readRoot,id,requestedCellFocus,presentationScope,initialEpochUuid]);
  const attemptedFocusLocator=useRef(null);
  const focusLocatorKey=JSON.stringify([readRoot,search,pageRevision,focused]);
  useEffect(()=>{
    if(!preserveCandidateView||!pageReady||pendingNavigation||!focused)return;
    if(rows.data.epochs.some(row=>row.epoch_uuid===focused)){attemptedFocusLocator.current=focusLocatorKey;return;}
    if(attemptedFocusLocator.current===focusLocatorKey)return;
    attemptedFocusLocator.current=focusLocatorKey;
    navigationIntent.current=null;anchorSteps.current=0;setPendingNavigation({anchorUuid:focused,direction:0});
  },[preserveCandidateView,pageReady,pendingNavigation,focused,rows.data,focusLocatorKey]);
  const readAuthority=JSON.stringify([readRoot,protocolSearch,pageRevision]);
  const previousReadAuthority=useRef({readAuthority,presentationScope});
  useEffect(()=>{
    const previous=previousReadAuthority.current;
    previousReadAuthority.current={readAuthority,presentationScope};
    if(!preserveCandidateView||previous.readAuthority===readAuthority||previous.presentationScope!==presentationScope)return;
    // Keep the UUID focus intent, but discard ordinals and temporary selection
    // authority from the previous receipt. Fresh pages revalidate the UUID.
    navigationIntent.current=null;anchorSteps.current=0;setPendingNavigation(null);
    if(!readContext)selectTargets([]);
  },[readAuthority,presentationScope,preserveCandidateView,onSelectionChange]);
  const curationIdentity=JSON.stringify([readRoot,id,protocolSearch,focusCell,protocol.query_revision,protocol.expected_binding_version??0,queryRevision,bindingVersion,revision,focused,targets]);
  const curationGeneration=useRef(0),curationRequest=useRef(null),mounted=useRef(false),committedCurationIdentity=useRef(null);
  const changedCallback=useRef(onChange);changedCallback.current=onChange;
  useLayoutEffect(()=>{
    mounted.current=true;committedCurationIdentity.current=curationIdentity;curationGeneration.current++;
    return()=>{mounted.current=false;curationGeneration.current++;curationRequest.current?.abort();};
  },[curationIdentity]);
  const previousScope=useRef({key:scopeIdentity,id,initialEpochUuid});
  useEffect(()=>{if(previousScope.current.key===scopeIdentity)return;const requested=previousScope.current.id!==id||previousScope.current.initialEpochUuid!==initialEpochUuid;previousScope.current={key:scopeIdentity,id,initialEpochUuid};setCellTagRequest(null);navigationIntent.current=null;anchorSteps.current=0;setFocusCell(requestedCellFocus);setOffset(0);setFocused(requested?initialEpochUuid:null);if(!readContext)selectTargets([]);setPendingNavigation(null);setDesignNavigation(null);},[scopeIdentity,id,requestedCellFocus,protocolSearch,initialEpochUuid]);
  const previousSelectionScope=useRef(selectionScope);
  useEffect(()=>{if(previousSelectionScope.current===selectionScope)return;previousSelectionScope.current=selectionScope;if(readContext){selectTargets([]);setSelectedView(null);}},[selectionScope]);
  function toggleSelectedView(){if(selectedView){setSelectedView(null);return;}try{setSelectedView({filters:selectedViewFilters(baseFilters,targets)});}catch(error){setError(error.message);}}
  useEffect(()=>{onSessionChange?.({focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation,listNavigation,annotationDrafts});},[focused,focusCell,offset,treeOpen,treeMode,designMode,designPath,designNavigation,listNavigation,annotationDrafts,onSessionChange]);

  function clearCellFocus(){setListNavigationRequest(value=>value+1);navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);if(!readContext)selectTargets([]);setPendingNavigation(null);}
  function selectOverviewTargets(update){
    setCellTagRequest(null);
    // This overview spans every matching cell, including when entered from a cell shortcut.
    if(focusCell){navigationIntent.current=null;anchorSteps.current=0;setFocusCell(null);setOffset(0);setPendingNavigation(null);}
    selectTargets(update);
  }
  function focusTreeEpoch(uuid,epochInfo){setCellTagRequest(null);toggleMetadata(true);
    if(busy||!navigationReady||committedNavigationReadKey.current!==navigationReadKey)return;
    setListNavigationRequest(value=>value+1);
    const loadedMember=pageReady&&rows.data?.epochs?.some(row=>row.epoch_uuid===uuid&&row.cell_uuid===epochInfo?.cell_uuid);
    if(focusCell&&epochInfo?.cell_uuid!==focusCell)clearCellFocus();
    navigationIntent.current=null;anchorSteps.current=0;setFocused(uuid);
    selectionNavigation.current=loadedMember?null:navigationReadKey;
    setPendingNavigation(loadedMember?null:{anchorUuid:uuid,direction:0});
  }
  useEffect(()=>{navigationIntent.current=null;anchorSteps.current=0;},[id,search,revision]);
  useEffect(()=>{
    if(!pendingNavigation)return;
    if(rows.error){if(preserveCandidateView&&pendingNavigation.anchorUuid===focused&&attemptedFocusLocator.current===focusLocatorKey)setFocused(null);navigationIntent.current=null;anchorSteps.current=0;setError(rows.error);setPendingNavigation(null);return;}
    if(rows.loading||!rows.data)return;
    const page=rows.data;
    let target=navigationIntent.current;
    if(pendingNavigation.anchorUuid){
      const index=page.epochs.findIndex(row=>row.epoch_uuid===pendingNavigation.anchorUuid);
      if(index<0){if(preserveCandidateView&&pendingNavigation.anchorUuid===focused&&attemptedFocusLocator.current===focusLocatorKey)setFocused(null);navigationIntent.current=null;anchorSteps.current=0;setError('The selected epoch is no longer in this query. Refresh the dataset.');setPendingNavigation(null);return;}
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
  },[pendingNavigation,rows.data,rows.loading,rows.error,preserveCandidateView,focused,focusLocatorKey]);
  // Persist grouping only after the server has successfully built that tree.
  useEffect(()=>{if(previousExternalSplit.current===externalSplitKey&&tree.data&&!tree.loading&&!tree.error&&tree.data.split_order?.join(',')===splits)onSplitChange?.(tree.data.split_order);},[tree.data,tree.loading,tree.error,splits,onSplitChange,externalSplitKey]);
  useEffect(()=>{if(previousExternalSplit.current!==externalSplitKey){previousExternalSplit.current=externalSplitKey;if(splits!==externalSplitKey){setSplits(externalSplitKey);setDesignPath([]);setDesignNavigation(null);}}},[externalSplitKey,splits]);
  async function curate(changes, scope='selection', epochUuid=null) {
    if(designBlocked||busy||curationRequest.current||!mounted.current)return;
    const uuids=epochUuid?[epochUuid]:resolveCurationTargets(focused,targets,scope);
    if(!uuids.length)return;
    if(!pageReady){setError('Refresh this dataset before saving.');return;}
    if(readContext&&committedCurationIdentity.current!==curationIdentity){setError('Selection or dataset changed. Refresh before saving.');return;}
    const controller=new AbortController(),generation=curationGeneration.current;
    curationRequest.current=controller;
    const isCurrent=()=>mounted.current&&generation===curationGeneration.current&&committedCurationIdentity.current===curationIdentity;
    setBusy(true);setError('');setOperationMessage('Saving curation changes…');
    try {
      if(readContext){
        if(!onReviewDecision)throw Error('Candidate review decisions are unavailable.');
        if(Object.keys(changes).some(key=>!['included','reviewed','review_state'].includes(key)))throw Error('Candidate protocol curation tags are unavailable; use shared tags.');
        await onReviewDecision({epoch_uuids:uuids,changes:{...('included' in changes?{included:changes.included}:{}),...(typeof changes.reviewed==='boolean'?{reviewed:changes.reviewed}:'review_state' in changes?{reviewed:changes.review_state==='approved'}:{})},query_revision:queryRevision,bindingVersion});
      }else await saveCurationSelection({request:api,protocolId:id,queryRevision,
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
    if(busy||readContext)return;
    setBusy(true);setError('');setMaskMessage('');setOperationMessage('Saving protocol selection mask…');
    try {
      const mask=await api(`/protocols/${id}/masks/export`);
      if(mask?.format!=='recording-selection-mask'||mask.version!==1||mask.protocol_uuid!==id||!Array.isArray(mask.epochs))throw new Error('The server did not return a valid protocol selection mask.');
      const link=document.createElement('a');link.href=`/api/protocols/${encodeURIComponent(id)}/masks/export`;link.download=`recording-mask-${id.slice(0,8)}.json`;
      document.body.appendChild(link);link.click();link.remove();
      setMaskMessage('Selection mask ready. Choose where to save the JSON containing epoch identities and inclusion decisions.');
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
      if(mask?.format!=='recording-selection-mask'||mask.version!==1)throw new Error('Choose a Recording Selection Mask v1 JSON file.');
      if(mask.protocol_uuid!==id)throw new Error('This mask belongs to a different protocol. Open that protocol before importing it.');
      const result=await api(`/protocols/${id}/masks/import`,{method:'POST',body:{mask,query_revision:queryRevision}});
      setMaskMessage(result.message || `Imported ${file.name}. Inclusion decisions were restored for the mask’s epochs; review approvals were not changed.`);
      onChange();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const focusedPageIndex=rows.data?.epochs?.findIndex(e=>e.epoch_uuid===focused) ?? -1;
  function moveEpoch(direction) {
    if(busy)return;
    setListNavigationRequest(value=>value+1);
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
        setListNavigationRequest(value=>value+1);
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
  const tagEntry=focusedEpoch&&<AnnotationTags composer={{values:annotationDrafts,onChange:rememberAnnotationDraft}} reconcileReceipt={!!onChange} refreshWithEpoch={!!onChange} epoch={focusedEpoch} revision={revision} disabled={designBlocked||busy||((readContext||filters?.metadata_predicate)&&!pageReady)||epoch.loading||!!pendingNavigation} onChange={annotationChanged} onFilter={onTagFilter} focusRequest={tagFocus} targetScope={cellTagRequest?'cell':!readContext&&targets.length?'selected':'epoch'} epochFocusRequest={epochTagFocus} onNavigateEpoch={navigateAndTag} selectedEpochs={readContext?[]:targets} tools={!cellTagRequest&&!targets.length&&<TagExchangeControls epoch={focusedEpoch} disabled={designBlocked||busy} onChanged={annotationChanged}/>}>{!readContext&&<EpochTags value={tag} onValue={setTag} onAdd={value=>curate({tags_add:[value]})} onRemove={value=>curate({tags_remove:[value]},'focused')} selectedTags={focusedEpoch.curation?.tags||[]} busy={designBlocked||busy||!pageReady} scope={`dataset · ${actionScope}`} revision={revision}/> }</AnnotationTags>;
  return <EpochViewer hideFilterControl viewFilters={filters} onViewFilters={onFilterChange} filterRevision={revision} filterDisabled={busy} className={designMode?'tree-design':'epoch-inspector-mode'} ariaLabel={designMode?'Tree overview workspace':'Epoch inspection workspace. Tab next epoch, Shift+Tab previous epoch; W/S also navigate.'} onKeyDown={epochKeys}
    toolbar={{portalTarget:toolbarTarget,treeControlsInPane:true,designMode:designMode,onBrowse:()=>{setDesignMode(false);setTreeMode(false);setTreeOpen(true);},onDesign:openTreeDesign,onTags:openTagsForSelection,metadataOpen:metadataOpen,onToggleMetadata:()=>toggleMetadata(!metadataOpen),actions:[
        {label:treeOpen?(designMode?'Hide tree editor':'Hide epoch list'):(designMode?'Show tree editor':'Show epoch list'),icon:GitBranch,run:()=>setTreeOpen(value=>!value)},
        !readContext&&!designMode&&{label:'Import mask file…',icon:FileJson,run:()=>(!readContext&&setMasksOpen(true)),disabled:busy},
        !readContext&&!designMode&&onImport&&{label:'Add data store',icon:Upload,run:onImport,disabled:busy},
      ]}} toolbarChildren={<>
      {focusCell&&<button className="inspection-focus-chip" disabled={designBlocked||busy} onClick={clearCellFocus} title="Clear cell focus and navigate all matching cells">{datedCellLabel(protocol.cells?.find(cell=>cell.cell_uuid===focusCell)||focusedEpoch||{},true)} <X size={12}/></button>}
    </>} before={<>
    {readContext&&draftSelection&&draftSelectionTarget&&createPortal(<IncomingSelectionTools {...draftSelection} source={{kind:'protocol',protocolId:id,readContext,query:protocolSearch,queryRevision:listQueryRevision}} cells={viewCells} freshCells={freshCells} filtered={Object.keys(filters||{}).length>0} targets={targets} cell={cellTagRequest} epoch={focusedEpoch} focusUuid={focused} onSelect={selectOverviewTargets} viewSelected={!!selectedView} onViewSelected={toggleSelectedView} disabled={draftSelection.disabled||busy||!cellsReady}/>,draftSelectionTarget)}
    <SourceEligibilityNotice eligibility={protocol.source_eligibility} onStores={onStores}/>
    {!designMode&&<>

    {masksOpen&&<SelectionMaskDialog busy={busy} onClose={()=>setMasksOpen(false)}>
      <section className="selection-mask-json"><h3>Protocol JSON mask</h3><p>Save or restore inclusion decisions for the full protocol query, including cells outside the current view.</p>
        <button disabled={designBlocked||busy} onClick={saveMask}><Download size={14}/> Save JSON mask</button>{' '}
        <input ref={maskInput} type="file" accept=".json,application/json" hidden onChange={importMask}/>
        <button disabled={designBlocked||busy} onClick={()=>maskInput.current?.click()}><Upload size={14}/> Import JSON mask</button>
      </section>
      {error&&<p className="tag-exchange-error" role="alert">{error}</p>}
      {maskMessage&&<p className="tag-import-success" role="status"><Check size={15}/>{maskMessage}</p>}
    </SelectionMaskDialog>}
    </>}{!designMode&&maskMessage&&<div className="mask-result" role="status"><Check size={15}/><span>{maskMessage}</span><button className="icon-button" onClick={()=>setMaskMessage('')} aria-label="Dismiss mask result"><X size={14}/></button></div>}
    {(cellPage.error||cellRevisionError)&&<div className="inspector-operation-error" role="alert">{cellPage.error||'Dataset changed while loading the cell list. Refresh before selecting epochs.'}<button onClick={()=>{loadedRows.reload();cellRows.reload();}}>Refresh epoch list</button></div>}
    {error&&<div className="inspector-operation-error" role="alert">{error}<button className="icon-button" onClick={()=>setError('')} aria-label="Dismiss operation error"><X size={14}/></button></div>}
</>}
    layout={{layoutRef,sizes:paneSizes,treeOpen,metadataOpen,onResize:changePane,onResizeCommit:savePane}} designMode={designMode}
    builder={{projectId,protocolId:id,readContext,selectedEpochs:targets,setSelectedEpochs:selectOverviewTargets,actionsDisabled:designBlocked||busy||!!draftSelection?.disabled||!cellsReady,onAnnotationsChanged:annotationChanged,summaryEnabled:!readContext,catalogPath:readRoot+'/tree-fields',summaryContext:{predicate:{all:[]},protocol_uuid:id,filters},queryString:protocolSearch,revision:pageRevision,value:splits.split(',').filter(Boolean),onChange:changeSplits,preview:tree.data,loading:tree.loading,error:tree.error}} columnTree={{selectionAuthority:designSelectionAuthority,readPending:designMode&&!treeStatus.error&&designBlocked,onAnnotationsChanged:annotationChanged,collapseRequest:collapseRequest,externalCollapseControl:true,actionsDisabled:designBlocked||busy||!!draftSelection?.disabled||!cellsReady,inclusionForEpoch:annotationState.apply,onToggleInclusion:(item,included)=>curate({included},'focused',item.epoch_uuid),cells:viewCells,selectedEpochs:targets,setSelectedEpochs:selectOverviewTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);if(!readContext)selectTargets([]);toggleMetadata(true);setDesignMode(false);setCellTagRequest((protocol.cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},presentation:"columns",protocolId:id,readContext,filters:filters,splits:splits,revision:pageRevision,design:true,selected:focused,initialNavigation:designNavigation,onNavigationChange:setDesignNavigation,onMetadata:receiveTree,onStatus:receiveTreeStatus,onSelectEpoch:focusTreeEpoch}} treePane={{selectionTools:readContext?<><IncomingTagSummary summary={incomingTags} onFilter={onTagFilter} disabled={designBlocked||busy||!pageReady}/></>:null,treeMode:treeMode,onTreeMode:value=>{setTreeMode(value);if(value)changePane('tree',Math.max(420,paneSizes.tree));},onDesign:openTreeDesign,designDisabled:busy,collapseRequest:collapseRequest,onCollapse:()=>setCollapseRequest(value=>value+1),treeProps:{selectionAuthority:treeSelectionAuthority,onAnnotationsChanged:annotationChanged,actionsDisabled:designBlocked||busy||!!draftSelection?.disabled||!cellsReady,inclusionForEpoch:annotationState.apply,onToggleInclusion:(item,included)=>curate({included},'focused',item.epoch_uuid),cells:viewCells,selectedEpochs:targets,setSelectedEpochs:selectOverviewTargets,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cellUuid,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);if(!readContext)selectTargets([]);toggleMetadata(true);setDesignMode(false);setCellTagRequest((protocol.cells||[]).find(cell=>cell.cell_uuid===cellUuid)||{cell_uuid:cellUuid,label:epoch.cell_label,date:epoch.date,cell_type:epoch.cell_type});},protocolId:id,readContext,filters,splits,revision:pageRevision,selected:focused,initialNavigation:designNavigation,onNavigationChange:setDesignNavigation,onSelectEpoch:focusTreeEpoch,onMetadata:receiveTree,onStatus:receiveTreeStatus},listRef:epochListRef,listKey:presentationScope,listProps:{navigationRequest:listNavigationRequest,navigationScope:JSON.stringify([projectId,presentationScope]),initialNavigation:listNavigation,onNavigationChange:setListNavigation,membershipReady:cellsReady,onAnnotationsChanged:annotationChanged,cells:viewCells||[],source:{kind:'protocol',protocolId:id,readContext,query:protocolSearch,queryRevision:listQueryRevision},revision:pageRevision,inclusionForEpoch:annotationState.apply,focused:cellTagRequest?null:focused,onFocus:focusTreeEpoch,selectedCell:cellTagRequest?.cell_uuid,onSelectCell:(cell,epoch)=>{focusTreeEpoch(epoch.epoch_uuid,epoch);if(!readContext)selectTargets([]);toggleMetadata(true);setCellTagRequest(cell);},targets,setTargets:selectOverviewTargets,disabled:busy||!!draftSelection?.disabled||!cellsReady,navigationDisabled:busy||!navigationReady,onToggleInclusion:(epoch,included)=>curate({included},'focused',epoch.epoch_uuid)}}}
    resource={{scope:id,...epoch,loading:!epoch.error&&(!!pendingNavigation||(!!focused&&(epoch.loading||!focusedEpoch))),retry:epoch.reload}}
    epoch={focusedEpoch} targets={targets} navigation={{position:focusedPageIndex<0?-1:offset+focusedPageIndex,total:rows.data?.total||0,loading:!!pendingNavigation||rows.loading,disabled:busy,onMove:moveEpoch}}
    readContext={readContext} traceRevision={annotationState.epochRevision} inclusion={{incoming:!!readContext,disabled:designBlocked||busy||!pageReady,scope:'pinned dataset',onToggle:(epoch,included)=>curate({included},'focused',epoch.epoch_uuid)}} detailDisabled={designBlocked||busy} onQC={onQC} tags={tagEntry}
    detailExtras={focusedEpoch&&(readContext?<IncomingEpochReview epoch={focusedEpoch} disabled={designBlocked||busy||!pageReady} onReview={reviewed=>curate({reviewed},'focused')}/>:<>        {busy&&<p className="curation-progress" role="status">{operationMessage}</p>}
        <div className="tags"><span>Dataset-only tags:</span>
          {(focusedEpoch.curation?.tags||[]).map(t=><button key={t} disabled={designBlocked||busy} aria-label={`Remove tag ${t} from focused epoch only`} title="Remove from focused epoch only" onClick={()=>curate({tags_remove:[t]},'focused')}>{t}<X size={13}/></button>)}
          {!focusedEpoch.curation?.tags?.length&&<span>No tags</span>}
          {focusedEpoch.curation?.included===false&&<Badge kind="warning">Excluded from export · still visible</Badge>}
        </div>
        <details className="optional-review"><summary>Optional review marker · {focusedEpoch.curation?.review_state==='approved'?'Reviewed':'Not marked'}</summary>
          <p>Use this marker if it helps your workflow. Included epochs can be exported without it; “reviewed only” is an optional export filter.</p>
          <button disabled={designBlocked||busy} onClick={()=>curate({review_state:!targets.length&&focusedEpoch.curation?.review_state==='approved'?'unreviewed':'approved'})}><Eye size={14}/>
            {targets.length?`Mark ${actionScope} reviewed`:focusedEpoch.curation?.review_state==='approved'?'Clear focused epoch review marker':'Mark focused epoch reviewed'}
          </button>
        </details></>)} metadata={{selectionCell:cellTagRequest,selectedEpochs:readContext?[]:targets,onClearSelection:()=>selectTargets([]),catalog:metadataCatalog,onClose:()=>toggleMetadata(false),connections:focusedEpoch&&<EpochConnections epoch={focusedEpoch} protocolName={humanize(protocol.definition?.name)}/>}}/>;
}

export default function Inspector(props){return <NavigationLoadingProvider><InspectorContent {...props}/></NavigationLoadingProvider>;}
