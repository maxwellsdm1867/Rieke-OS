import EpochViewer from './EpochViewer.jsx';
import {treePreviewScope} from '../pagedTreeRequest.js';
import {predicateWithTagFilters,tagFilterLabel} from '../protocolViewFilter.js';
import {searchInclusionPredicate,searchEpochInclusion,toggleSearchInclusion} from '../searchInclusion.js';
import SearchPresets from './SearchPresets.jsx';
import QueryPresetDialog from './QueryPresetDialog.jsx';
import {searchPresetPayload,validatePresetReceipt} from '../projectSearchPresets.js';
import {rememberSearch,predicateSummary} from '../searchPresets.js';
import {useProjectPreference} from '../useProjectPreference.js';
import ExportSelectionDialog from './ExportSelectionDialog.jsx';
import PredicateDialog from './PredicateDialog.jsx';
import {predicateIdentity} from '../predicateIdentity.js';
import MatchingEpochs from './MatchingEpochs.jsx';
import InspectorActions from './InspectorActions.jsx';
import {explorerFocusState} from '../explorerScope.js';
import {snapshotExplorerState} from '../workspaceNavigation.js';
import {datedCellLabel} from '../recordingIdentity.js';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, ChevronDown, Search, Filter, Download, GitBranch, History, LoaderCircle, RefreshCw, Save, Plus, X } from 'lucide-react';
import { api, humanize, number, time, useResource } from '../api.js';
import { Badge, Metadata, Status } from './Common.jsx';
import {inspectorPaneSizes} from '../inspectorInteraction.js';
import { compilePredicate, conditionCount, newCondition, newGroup, predicateToDraft } from './predicateState.js';
import './MetadataExplorer.css';

const initialSearch=()=>({...newGroup(),children:[{...newCondition(),field:'protocol',operator:'contains'}]});
function draftOf(predicate){const node=predicateToDraft(predicate);return node.kind==='group'?node:{...newGroup(),children:[node]};}
export default function MetadataExplorer({initialEditorOpen=false,openRequest=0,projectId,revision=0,protocols=[],onInspect,initialPredicate=null,initialRevisionId=null,initialProtocolId=null,initialExportIntent=null,onChange,onProtocolApplied,onNewSearch,onExit,onQC,session=null,onSession}) {
  const saved=useRef(session).current;
  const [draft,setDraft]=useState(()=>saved?.draft || (initialPredicate?draftOf(initialPredicate):initialSearch()));
  const [viewFilters,setViewFilters]=useState(saved?.viewFilters||{}),[filteredPreview,setFilteredPreview]=useState({data:null,loading:false,error:null,key:null});
  const [excludedEpochs,setExcludedEpochs]=useState(saved?.excludedEpochs||[]),[exportCandidate,setExportCandidate]=useState(null);
  const [name,setName]=useState(saved?.name ?? 'Metadata selection');
  const [filterSplits,setFilterSplits]=useState(saved?.filterSplits ?? 'date,protocol,cell');
  const [splits,setSplits]=useState(saved?.splits ?? 'date,protocol,cell');
  const [step,setStep]=useState(saved?.step || 'filter');
  const [epochToolbarTarget,setEpochToolbarTarget]=useState(null);
  const [editorOpen,setEditorOpen]=useState(()=>!initialRevisionId&&(!!initialPredicate||initialEditorOpen));
  const shortcutPreferences=useProjectPreference(projectId,'recent_searches');
  const presets=shortcutPreferences.value;
  const [presetError,setPresetError]=useState('');
  const [presetOffset,setPresetOffset]=useState(0),[activePreset,setActivePreset]=useState(saved?.activePreset||null),[presetDialog,setPresetDialog]=useState(null),[importedPreset,setImportedPreset]=useState(null);
  const projectPresets=useResource(`/search-presets?limit=50&offset=${presetOffset}`,revision);
  async function storePreset(entry){setPresetError('');await shortcutPreferences.update(previous=>rememberSearch(previous,entry)).catch(error=>setPresetError(`The search ran, but its shortcut could not be saved to the project: ${error.message}`));}
  const [resultsFromDraft,setResultsFromDraft]=useState(saved?.resultsFromDraft??true),[matchingNavigation,setMatchingNavigation]=useState(saved?.matchingNavigation||null),[destination,setDestination]=useState(initialExportIntent?'export':null);
  const [departedInitial,setDepartedInitial]=useState(false);
  const [initialCandidateLoading,setInitialCandidateLoading]=useState(!!initialRevisionId&&!saved?.applied);
  const [initialCandidateRetry,setInitialCandidateRetry]=useState(0);
  const [applied,setApplied]=useState(saved?.applied || null),[restored,setRestored]=useState(saved?.restored || null);
  const [treeNavigation,setTreeNavigation]=useState(saved?.treeNavigation||null);
  const [path,setPath]=useState(saved?.path || []),[focused,setFocused]=useState(saved?.focused || null);
  // Annotation edits decorate the currently browsed UUIDs; only an explicit
  // refresh may replace their predicate membership. Global summaries can refresh.
  const [annotationHold,setAnnotationHold]=useState(null);
  const viewRevision=annotationHold?.revision??revision;
  const [generation,setGeneration]=useState(0),[historyVersion,setHistoryVersion]=useState(0),[historyOffset,setHistoryOffset]=useState(saved?.historyOffset || 0);
  const [draftPreview,setDraftPreview]=useState({data:null,loading:false,error:null,key:null});
  const [tree,setTree]=useState({data:null,loading:false,error:null});
  const [busy,setBusy]=useState(false),[busyAction,setBusyAction]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(saved?.wasBusy?'A request was in progress when you left. Check Candidate history before saving again.':saved?'Workspace draft restored. No save or protocol update was replayed.':'');
  const draftController=useRef(null),treeController=useRef(null);
  const [pagedInfo,setPagedInfo]=useState(null),[pagedStatus,setPagedStatus]=useState({loading:false,error:null});
  const layoutRef=useRef(null),[layoutWidth,setLayoutWidth]=useState(1100);
  const [groupingWidth,setGroupingWidth]=useState(()=>{try{const value=Number(localStorage.getItem('workspace.explorer.groupingWidth'));return value>=240?value:320;}catch{return 320;}});
  const pane=inspectorPaneSizes(layoutWidth,{tree:groupingWidth},true,false);
  useEffect(()=>setPagedInfo(null),[splits,applied?.revision_uuid,generation]);
  // Tag vocabulary should refresh even while the currently browsed membership is held.
  const catalog=useResource('/explore/predicate-fields',`${revision}:${generation}`);
  useEffect(()=>{if(editorOpen)catalog.reload();},[editorOpen,openRequest]);
  const history=useResource(`/explore/revisions?offset=${historyOffset}&limit=20`,historyVersion);
  const epoch=useResource(focused?`/epochs/${focused}`:null,`${revision}:${generation}`);
  const compiled=useMemo(()=>{
    try{return {predicate:compilePredicate(draft,catalog.data?.fields || null),error:null};}
    catch(error){return {predicate:null,error:error.message};}
  },[draft,catalog.data]);
  const draftKey=predicateIdentity({predicate:compiled.predicate,splits:filterSplits});
  const changedFilter=!!applied&&predicateIdentity(compiled.predicate)!==predicateIdentity(applied.recipe.predicate);
  const changedTree=!!applied&&splits.split(',').map(x=>x.trim()).join(',')!==applied.recipe.splits.split(',').map(x=>x.trim()).join(',');
  const currentDraftPreview=draftPreview.key===draftKey?draftPreview.data:null;
  const previewFieldCount=field=>currentDraftPreview?.catalog?.fields?.find(item=>item.id===field)?.recorded_distinct_count;
  const restoredDiff=restored&&currentDraftPreview?.baseline_diff;
  const treeDiff=tree.data?.baseline_diff;
  const changedMembership=!!treeDiff&&(treeDiff.added>0||treeDiff.removed>0||treeDiff.changed>0||treeDiff.annotation_changed===true);
  const focusState=explorerFocusState(tree.data,focused,tree);
  const focusVerified=['included','excluded'].includes(focusState);
  const focusedInScope=focusState==='included';
  const matches=epoch.data?protocols.filter(protocol=>!protocol.binding&&(protocol.acquisition_protocol===epoch.data.protocol_name ||
    protocol.query?.all?.some(condition=>condition.field==='EpochBlock.protocol_name'&&condition.operator==='eq'&&condition.value===epoch.data.protocol_name))):[];
  useEffect(()=>{onSession?.(snapshotExplorerState({viewFilters,excludedEpochs,draft,name,filterSplits,splits,step,resultsFromDraft,matchingNavigation,path,treeNavigation,focused,applied,restored,historyOffset,activePreset,wasBusy:busy}));},[viewFilters,excludedEpochs,draft,name,filterSplits,splits,step,resultsFromDraft,matchingNavigation,path,treeNavigation,focused,applied,restored,historyOffset,activePreset,busy,onSession]);
  useEffect(()=>{
    if(saved?.applied&&initialCandidateRetry===0){setInitialCandidateLoading(false);return;}
    if(!initialRevisionId){setInitialCandidateLoading(false);return;}
    const controller=new AbortController();setInitialCandidateLoading(true);setApplied(null);setTree({data:null,loading:false,error:null});setError('');
    api(`/explore/revisions/${initialRevisionId}?summary=1`,{signal:controller.signal}).then(result=>{
      if(controller.signal.aborted)return;
      if(!result.recipe||!result.revision_uuid)throw new Error('This candidate does not contain a saved recipe.');
      setApplied(result);if(initialExportIntent)setExportCandidate(result);setDraft(draftOf(result.recipe.predicate));setName(initialExportIntent?.name || result.recipe.name || 'Protocol candidate');
      setSplits(result.recipe.splits);setFilterSplits(result.recipe.splits);setRestored(null);setFocused(null);setPath([]);setTreeNavigation(null);setStep('results');setResultsFromDraft(false);
      setNotice(`Reviewing saved candidate ${result.revision_uuid.slice(0,8)}. The protocol working dataset stays unchanged until you apply it.`);
    }).catch(error=>{if(!controller.signal.aborted)setError(error.message);}).finally(()=>{if(!controller.signal.aborted)setInitialCandidateLoading(false);});
    return()=>controller.abort();
  },[initialRevisionId,initialCandidateRetry]);
  useEffect(()=>()=>{draftController.current?.abort();treeController.current?.abort();},[]);
  useEffect(()=>{
    if(!applied)return;
    if(!focused&&applied.preview&&(step!=='tree'||applied.preview.catalog_summary!==false)&&splits===applied.recipe.splits&&generation===applied.previewGeneration&&viewRevision===applied.previewRevision){setTree({data:applied.preview,loading:false,error:null});return;}
    const controller=new AbortController();treeController.current?.abort();treeController.current=controller;
    setTree(previous=>({...previous,loading:true,error:null}));
    api('/explore/preview',{method:'POST',body:{predicate:applied.recipe.predicate,splits,summary_only:true,catalog_summary:step==='tree',baseline_revision_uuid:applied.revision_uuid,...(focused?{focused_uuid:focused}:{})},signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setTree({data:{...data,_focusedUuid:focused},loading:false,error:null});})
      .catch(error=>{if(!controller.signal.aborted)setTree(previous=>({...previous,loading:false,error:error.message}));});
    return()=>controller.abort();
  },[applied,splits,viewRevision,generation,focused,step]);
  useEffect(()=>{if(focusVerified&&tree.data.focused_in_scope===false)setFocused(null);},[focusVerified,tree.data]);
  const changeSplits=useCallback(fields=>{const text=fields.join(',');setSplits(text);setFilterSplits(text);setPath([]);setTreeNavigation(null);setFocused(null);},[]);
  async function previewDraft(predicate=compiled.predicate,grouping=filterSplits,baseline=restored?.revision_uuid,openResults=false){
    if(!predicate)return;
    const controller=new AbortController();draftController.current?.abort();draftController.current=controller;
    const key=predicateIdentity({predicate,splits:grouping});setDraftPreview({data:null,loading:true,error:null,key});
    try{const data=await api('/explore/preview',{method:'POST',body:{predicate,splits:grouping,summary_only:true,catalog_summary:false,...(baseline?{baseline_revision_uuid:baseline}:{})},signal:controller.signal});if(!controller.signal.aborted){setDraftPreview({data,loading:false,error:null,key});setAnnotationHold(null);if(openResults){setResultsFromDraft(true);setStep('results');setDestination(null);setFocused(null);}}}
    catch(error){if(!controller.signal.aborted)setDraftPreview({data:null,loading:false,error:error.message,key});}
  }
  async function saveRevision(kind,nextStep='results',notifyParent=true){
    if(annotationHold){setError('Refresh results after editing annotations before recording or exporting this selection.');return;}
    const predicate=kind==='filter'?compiled.predicate:applied?.recipe.predicate;
    if(!predicate||busy)return;
    setBusy(true);setBusyAction('save');setError('');setNotice('');
    try{
      const body={predicate,splits:kind==='filter'?filterSplits:splits,name:name.trim() || 'Metadata selection',summary_only:true,catalog_summary:nextStep==='tree'};
      const parent=kind==='filter'?(restored?.revision_uuid || applied?.revision_uuid):applied?.revision_uuid;
      if(parent)body.parent_revision_uuid=parent;
      const result=await api('/explore/revisions',{method:'POST',body});
      if(!result.recipe||!result.revision_uuid)throw new Error('The server did not return a recorded revision. Reload history before retrying.');
      setApplied({...result,previewGeneration:generation,previewRevision:viewRevision});if(result.preview)setTree({data:result.preview,loading:false,error:null});if(notifyParent)onChange?.();setSplits(result.recipe.splits);setFilterSplits(result.recipe.splits);setPath([]);setTreeNavigation(null);setFocused(null);setStep(nextStep);setResultsFromDraft(false);
      if(kind==='filter'){setDraft(draftOf(result.recipe.predicate));setRestored(null);}
      await storePreset({name:body.name,predicate,splits:result.recipe.splits,matched_count:result.summary?.matched_count??result.preview?.matched_count});
      setHistoryVersion(value=>value+1);setHistoryOffset(0);setNotice(nextStep==='tree'?'':`Recorded revision ${result.revision_uuid.slice(0,8)}. Its query and exact epoch membership are preserved.`);return result;
    }catch(error){setError(error.message);}finally{setBusy(false);setBusyAction(null);}
  }
  async function presetRecipe(item){
    if(item.predicate)return item;
    const result=await api(`/explore/revisions/${item.revision_uuid}?summary=1`,{signal:draftController.current.signal});
    if(!result.recipe?.predicate)throw new Error('This saved query has no reusable predicate.');
    return {...result.recipe,matched_count:result.summary?.matched_count,revision_uuid:item.revision_uuid};
  }
  async function usePreset(item,action='run'){
    if(busy)return;
    const controller=new AbortController();draftController.current?.abort();draftController.current=controller;
    setBusy(true);setError('');setNotice('');
    try{
      const preset=await presetRecipe(item);if(controller.signal.aborted)return;
      const nextDraft=draftOf(preset.predicate),predicate=compilePredicate(nextDraft,catalog.data?.fields||null),grouping=preset.splits??'date,cell';
      const nextName=preset.name&&preset.name!=='Metadata selection'?preset.name:predicateSummary(predicate);
      if(action==='pin'){await storePreset({...preset,name:nextName,pinned:!item.pinned});return;}
      if(action==='edit'){setActivePreset(item.preset_uuid?item:null);setImportedPreset(null);setDraft(nextDraft);setName(nextName);setFilterSplits(grouping);setRestored(null);setEditorOpen(true);return;}
      const result=await api('/explore/run',{method:'POST',body:{predicate,splits:grouping,catalog_summary:false},signal:controller.signal});
      if(controller.signal.aborted)return;
      setViewFilters({});setExcludedEpochs([]);setExportCandidate(null);setAnnotationHold(null);setActivePreset(item.preset_uuid?item:null);setImportedPreset(null);setDepartedInitial(true);setDraft(nextDraft);setName(nextName);setFilterSplits(grouping);setSplits(grouping);setRestored(null);setApplied(null);setTreeNavigation(null);setMatchingNavigation(null);setFocused(null);setDestination(null);
      setDraftPreview({data:result,loading:false,error:null,key:predicateIdentity({predicate,splits:grouping})});setResultsFromDraft(true);setStep('results');setEditorOpen(false);
      await storePreset({name:nextName,predicate,splits:grouping,matched_count:result.matched_count,cell_count:result.last_run.cell_count,lastRunAt:result.last_run.ran_at});projectPresets.reload();
    }catch(error){if(!controller.signal.aborted)setError(error.message);}finally{if(!controller.signal.aborted)setBusy(false);}
  }
  async function pinProjectPreset(item){
    if(busy)return;setBusy(true);setBusyAction('preset');setPresetError('');
    try{const result=validatePresetReceipt(await api(`/search-presets/${item.preset_uuid}`,{method:'PUT',body:searchPresetPayload({...item,pinned:!item.pinned},item)}));if(activePreset?.preset_uuid===item.preset_uuid)setActivePreset(result);projectPresets.reload();onChange?.();}
    catch(error){setPresetError(`${error.message} Refresh project searches before trying again.`);}finally{setBusy(false);setBusyAction(null);}
  }
  function importQueryRecipe(recipe){
    const nextDraft=draftOf(recipe.predicate);
    setDraft(nextDraft);setName(recipe.name);setFilterSplits(recipe.splits);setActivePreset(null);setImportedPreset(recipe);setRestored(null);setEditorOpen(true);
    setNotice(`Imported query draft. Review and run it before saving. ${recipe.source_project_uuid&&recipe.source_project_uuid!==projectId?'It will query this project’s catalog; source data and saved memberships are not copied.':'No project data or saved search has changed.'}`);
  }
  function saveQueryPreset(){
    if(!resultPredicate)return;
    setPresetDialog({predicate:structuredClone(resultPredicate),splits:resultSplits,preset:projectPresets.data?.presets?.find(item=>item.preset_uuid===activePreset?.preset_uuid)||activePreset,defaults:{name:name==='Metadata selection'?predicateSummary(resultPredicate).slice(0,160):name,description:importedPreset?.description||''}});
  }
  function savedQueryPreset(row){setActivePreset(row);setName(row.name);setPresetDialog(null);setImportedPreset(null);setPresetOffset(0);projectPresets.reload();setNotice(`${row.reused?'Using existing':'Saved'} “${row.name}” in this project. Rerunning it queries current data; the current selection and protocol datasets are unchanged.`);onChange?.();}
  const baseResultPreview=resultsFromDraft?currentDraftPreview:tree.data;
  const baseResultPredicate=resultsFromDraft?compiled.predicate:applied?.recipe.predicate;
  const resultSplits=resultsFromDraft?filterSplits:splits;
  const resultPredicate=baseResultPredicate?predicateWithTagFilters(baseResultPredicate,viewFilters):null;
  const hasViewFilter=!!tagFilterLabel(viewFilters);
  const filteredKey=predicateIdentity({predicate:resultPredicate,splits:resultSplits,revision:viewRevision,generation});
  const currentFilteredPreview=filteredPreview.key===filteredKey?filteredPreview.data:null;
  const resultPreview=hasViewFilter?currentFilteredPreview:baseResultPreview;
  const resultLoading=hasViewFilter?filteredPreview.loading||!currentFilteredPreview&&!filteredPreview.error:(resultsFromDraft?draftPreview.loading:tree.loading);
  const resultError=hasViewFilter&&filteredPreview.key===filteredKey?filteredPreview.error:(resultsFromDraft?draftPreview.error:tree.error);
  const availableTree=hasViewFilter?{data:currentFilteredPreview,loading:resultLoading,error:resultError}:tree;
  // Search previews intentionally omit scoped field statistics. Wait for the
  // design preview before mounting a builder that displays those statistics.
  const displayTree=step==='tree'&&availableTree.data?.catalog_summary===false
    ?{...availableTree,data:null,loading:!availableTree.error}:availableTree;

  useEffect(()=>{const node=layoutRef.current;if(!node)return;const observer=new ResizeObserver(entries=>setLayoutWidth(entries[0].contentRect.width));observer.observe(node);return()=>observer.disconnect();},[step,focused,initialCandidateLoading,!!displayTree.data,displayTree.loading,!!displayTree.error]);
  useEffect(()=>{
    if(!hasViewFilter||!resultPredicate||step==='filter'||!baseResultPreview)return;
    const controller=new AbortController();
    setFilteredPreview({data:null,loading:true,error:null,key:filteredKey});
    api('/explore/preview',{method:'POST',body:{predicate:resultPredicate,splits:resultSplits,summary_only:true,catalog_summary:step==='tree'},signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setFilteredPreview({data,loading:false,error:null,key:filteredKey});})
      .catch(error=>{if(!controller.signal.aborted)setFilteredPreview({data:null,loading:false,error:error.message,key:filteredKey});});
    return()=>controller.abort();
  },[hasViewFilter,filteredKey,step,!!baseResultPreview]);
  function changeViewFilters(next){setViewFilters(next);setMatchingNavigation(null);setTreeNavigation(null);setPagedInfo(null);setDestination(null);setExportCandidate(null);}

  useEffect(()=>{if(step==='results'&&resultsFromDraft&&!currentDraftPreview&&!draftPreview.loading&&draftPreview.key!==draftKey&&compiled.predicate)previewDraft();},[step,resultsFromDraft,draftKey,currentDraftPreview,draftPreview.loading,draftPreview.key]);
  function annotationsChanged(){
    setAnnotationHold(current=>current||{revision:viewRevision});setDestination(null);onChange?.();
  }
  function refreshResults(){
    if(resultsFromDraft){if(hasViewFilter)setGeneration(value=>value+1);previewDraft();}else{setAnnotationHold(null);setGeneration(value=>value+1);}
  }
  async function prepareDestination(next,fromDraft=resultsFromDraft){
    if(annotationHold){setError('Refresh results after editing annotations before using this selection.');return;}
    if(next==='export'){
      if(busy||!resultPredicate)return;
      setBusy(true);setError('');
      try{
        const result=await api('/explore/revisions',{method:'POST',body:{predicate:searchInclusionPredicate(resultPredicate,excludedEpochs),splits:resultSplits,name:name.trim()||'Metadata selection',summary_only:true,catalog_summary:false,...(applied?.revision_uuid?{parent_revision_uuid:applied.revision_uuid}:{})}});
        if(!result.recipe||!result.revision_uuid)throw new Error('The server did not return an export selection.');
        if(!(result.summary?.matched_count??result.recipe.epoch_count??result.recipe.epochs?.length)){setError('No included epochs remain. Include an epoch before exporting.');return;}
        setExportCandidate(result);setHistoryVersion(value=>value+1);setDestination('export');
      }catch(error){setError(error.message);}finally{setBusy(false);}
      return;
    }
    if(fromDraft||!applied||changedTree||changedMembership){const result=await saveRevision(fromDraft?'filter':'tree',next==='tree'?'tree':'results',next!=='export');if(!result)return;}
    if(next==='tree'){setStep('tree');setDestination(null);}else setDestination(next);
  }
  const previousOpenRequest=useRef(openRequest);
  useEffect(()=>{if(previousOpenRequest.current!==openRequest&&!busy){previousOpenRequest.current=openRequest;editSearch();}},[openRequest,busy]);
  function editSearch(){
    if(step!=='filter'&&baseResultPredicate){setDraft(draftOf(baseResultPredicate));setFilterSplits(resultSplits);}
    setEditorOpen(true);
  }
  async function applyPopupSearch(nextDraft,predicate,signal){
    const result=await api('/explore/run',{method:'POST',body:{predicate,splits:filterSplits,catalog_summary:false},signal});
    if(signal.aborted)return;
    setViewFilters({});setExcludedEpochs([]);setExportCandidate(null);setAnnotationHold(null);setNotice('');setDraft(nextDraft);setDraftPreview({data:result,loading:false,error:null,key:predicateIdentity({predicate,splits:filterSplits})});
    setMatchingNavigation(null);setResultsFromDraft(true);setFocused(null);setDestination(null);setStep('results');setEditorOpen(false);
    await storePreset({name:name==='Metadata selection'?predicateSummary(predicate):name,predicate,splits:filterSplits,matched_count:result.matched_count,cell_count:result.last_run.cell_count,lastRunAt:result.last_run.ran_at});projectPresets.reload();
  }
  function showEpochResults(){
    setFocused(null);setDestination(null);
    setResultsFromDraft(!applied);setStep('results');
  }
  function toggleInclusion(epoch,included){if(busy)return;setExcludedEpochs(ids=>toggleSearchInclusion(ids,epoch.epoch_uuid,included));setDestination(null);setExportCandidate(null);}
  const exportDisabled=!!annotationHold||busy||resultLoading||!!resultError||!resultPreview?.matched_count;
  function openResultsExport(){
    if(step==='tree'){setFocused(null);setResultsFromDraft(false);setStep('results');prepareDestination('export',false);}
    else prepareDestination('export');
  }
  const resultActions=[
        {label:'Edit predicate',icon:Filter,disabled:busy,run:editSearch},
        {label:'Save query preset',icon:Save,disabled:busy||resultLoading||!!resultError||!resultPreview||!resultPredicate,run:saveQueryPreset},
        {label:'Save selection revision',icon:Save,disabled:!!annotationHold||busy||resultLoading||!!resultError||!resultPreview,run:()=>saveRevision(resultsFromDraft?'filter':'tree')},
        {label:'Search presets',icon:History,disabled:busy,run:()=>{setStep('filter');setFocused(null);setDestination(null);}},
        onExit&&{label:'Close search',icon:X,disabled:busy,run:onExit},
      ];
  return <div className={`inspector metadata-explorer predicate-explorer ${focused?'explorer-inspecting':step==='tree'?'tree-design':''}`}>
    {presetDialog&&<QueryPresetDialog {...presetDialog} onClose={()=>setPresetDialog(null)} onSaved={savedQueryPreset} onRefresh={projectPresets.reload}/>}
    {editorOpen&&<PredicateDialog title={step==='filter'?'Search predicate':'Change search criteria'} submitLabel={step==='filter'?'View matching epochs':'Update matching epochs'} previousRun={activePreset?.last_run??resultPreview?.last_run} previousPredicate={activePreset?.last_run?activePreset.predicate:baseResultPredicate} protocols={protocols} projectId={projectId} draft={draft} catalog={catalog} onSearch={applyPopupSearch} onClose={()=>setEditorOpen(false)}/>}
    {step==='filter'?(<header className="mx-heading"><div><div className="eyebrow">SOURCE RECORDINGS</div><h1>{focused?'Inspect selected epoch':step==='results'?'Epoch browser':step==='tree'?'Tree view · advanced':'Search presets'}</h1></div>
      <div className="mx-header-actions">
        {step==='tree'&&<button disabled={busy} onClick={showEpochResults}><ArrowLeft size={15}/> Back to epochs</button>}
        <button disabled={busy} onClick={onNewSearch}><Search size={16}/> New predicate</button>
        {step!=='filter'&&<button className="primary" disabled={!!annotationHold||busy||resultLoading||!!resultError||!resultPreview?.matched_count} onClick={()=>{if(step==='tree'){setFocused(null);setResultsFromDraft(false);setStep('results');prepareDestination('export',false);}else prepareDestination('export');}}><Download size={15}/> Export</button>}
        {step==='filter'&&(applied||currentDraftPreview)&&<button disabled={busy} onClick={()=>{setResultsFromDraft(!!currentDraftPreview);setFocused(null);setDestination(null);setStep('results');}}><ArrowLeft size={15}/> Back to results</button>}
        {step!=='filter'&&<button disabled={busy} onClick={()=>{setStep('filter');setFocused(null);setDestination(null);}}><History size={15}/> Search presets</button>}
        {onExit&&<button className="quiet" disabled={busy} onClick={onExit}><X size={15}/> Close search</button>}
      </div>
    </header>):<header className="mx-heading mx-heading-compact"><strong>{step==='tree'?'Design tree':'Search results'}</strong><div className="mx-header-actions">



    </div><div className="epoch-browser-header-controls" ref={setEpochToolbarTarget}/></header>}
    {hasViewFilter&&resultError&&<div className="mx-operation-error" role="alert"><span>{resultError}</span><button disabled={busy} onClick={()=>changeViewFilters({})}>Clear filter</button><button disabled={busy} onClick={refreshResults}>Refresh results</button></div>}
    {error&&<div className="mx-operation-error" role="alert">{error}<button onClick={()=>setError('')} aria-label="Dismiss error"><X size={14}/></button></div>}
    {step!=='filter'&&shortcutPreferences.error&&<div className="mx-operation-error" role="alert">{shortcutPreferences.error}<button onClick={()=>shortcutPreferences.update(previous=>previous).catch(()=>{})}>Retry shortcut save</button></div>}
    {annotationHold&&<div className="mx-operation-error" role="status"><span>Annotations changed. The current epoch page and selection are retained; refresh results before exporting or applying this query.</span><button disabled={busy||resultLoading} onClick={refreshResults}><RefreshCw size={14}/> Refresh results</button></div>}
    {notice&&<div className="mx-recorded-notice" role="status"><Check size={14}/><span>{notice}</span><button onClick={()=>setNotice('')} aria-label="Dismiss revision notice"><X size={14}/></button></div>}
    {initialCandidateLoading?<div className="mx-candidate-loading" role="status"><LoaderCircle size={18}/> Loading saved candidate…</div>:initialRevisionId&&!applied&&!departedInitial?<div className="mx-candidate-loading"><span>The saved candidate could not be loaded.</span><button onClick={()=>setInitialCandidateRetry(value=>value+1)}>Retry</button></div>:step==='filter'&&!focused?<SearchPresets entries={presets} fields={catalog.data?.fields||[]} history={history} projectPresets={projectPresets} onProjectPin={pinProjectPreset} onImportRecipe={importQueryRecipe} onProjectPage={setPresetOffset} busy={busy||catalog.loading||shortcutPreferences.loading} error={presetError||shortcutPreferences.error||catalog.error} onRun={usePreset} onEdit={item=>usePreset(item,'edit')} onPin={item=>usePreset(item,'pin')}/>:step==='results'?<div className="mx-results-workflow">
      {destination&&exportCandidate&&<ExportSelectionDialog candidate={exportCandidate} projectId={projectId} protocols={protocols} initialProtocolId={initialProtocolId} defaultName={name} defaultFormat={initialExportIntent?.format} disabled={!!annotationHold||busy||resultLoading||!!resultError} onClose={()=>{setDestination(null);onChange?.();}} onApplied={onProtocolApplied} onChanged={()=>onChange?.()}/>}
      {!hasViewFilter&&resultError&&<div className="mx-operation-error" role="alert">{resultError}<button onClick={()=>resultsFromDraft?previewDraft():setGeneration(value=>value+1)}>Refresh results</button></div>}
      {!resultLoading&&!resultError&&resultPreview&&resultPredicate?<MatchingEpochs onQC={onQC} inclusionForEpoch={epoch=>searchEpochInclusion(epoch,excludedEpochs)} onToggleInclusion={toggleInclusion} toolbarTarget={epochToolbarTarget} viewFilters={viewFilters} onViewFilters={changeViewFilters} filterRevision={revision} filterDisabled={busy||!!annotationHold} onExport={openResultsExport} exportDisabled={exportDisabled} designDisabled={!!annotationHold||busy||resultLoading||!!resultError} actions={resultActions} onDesign={()=>{if(!annotationHold&&!busy&&!resultLoading&&!resultError)prepareDestination('tree');}} key={resultPreview.tree_revision} predicate={resultPredicate} splits={resultSplits} preview={resultPreview} session={matchingNavigation} onSession={setMatchingNavigation} onAnnotationsChanged={annotationsChanged} onTagFilter={predicate=>{setDraft(draftOf(predicate));setActivePreset(null);setEditorOpen(true);}} onRefresh={refreshResults}/>:<Status loading={resultLoading} error={resultError}/>}
    </div>:<>
      <Status {...displayTree} retry={()=>setGeneration(value=>value+1)}>{displayTree.data&&applied&&<EpochViewer designMode className="tree-design explorer-design-viewer" ariaLabel="Tree overview workspace"
        toolbar={{portalTarget:epochToolbarTarget,designMode:true,onBrowse:showEpochResults,onExport:openResultsExport,exportDisabled,actions:resultActions}}
        layout={{layoutRef,className:'mx-layout',sizes:pane,treeOpen:true,metadataOpen:false,onResize:(name,value)=>{if(name==='tree')setGroupingWidth(value);},onResizeCommit:(name,value)=>{if(name==='tree')try{localStorage.setItem('workspace.explorer.groupingWidth',String(value));}catch{}}}}
        builder={{catalogData:displayTree.data.catalog,value:splits.split(',').filter(Boolean),onChange:changeSplits,preview:pagedInfo&&pagedInfo.split_order?.join(',')===splits?{...displayTree.data.tree,...pagedInfo,count:displayTree.data.matched_count}:displayTree.data.tree,loading:displayTree.loading||pagedStatus.loading,error:displayTree.error||pagedStatus.error}}
        columnTree={{inclusionForEpoch:epoch=>searchEpochInclusion(epoch,excludedEpochs),onToggleInclusion:toggleInclusion,actionsDisabled:busy,predicate:resultPredicate,...treePreviewScope(displayTree.data),revision:`${viewRevision}:${generation}`,initialNavigation:treeNavigation,onNavigationChange:setTreeNavigation,onRefreshPreview:()=>setGeneration(value=>value+1),onMetadata:setPagedInfo,onStatus:setPagedStatus,selected:matchingNavigation?.focused,onSelectEpoch:uuid=>setMatchingNavigation({revision:displayTree.data.tree_revision,focused:uuid})}}/>}</Status>

    </>}
  </div>;
}
function SearchIcon(){return <Filter size={15}/>;}
