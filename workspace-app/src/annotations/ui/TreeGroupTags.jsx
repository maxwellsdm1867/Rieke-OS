import {useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Tag,X,CheckSquare} from 'lucide-react';
import {api,number} from "../../api.js";
import {loadIncomingSelection} from "../../incoming-workbench/incomingSelection.js";
import {resolveTreeGroup,verifyTreeGroup} from '../treeGroupTargets.js';
import {useAnnotationProfile} from '../annotationProfile.js';
import {previewTreeGroup,releaseGroupPreview} from '../treeGroupQueryTags.js';
import {branchLabel} from "../../tree-browser/treeBranchPresentation.js";
import AnnotationTags from './AnnotationTags.jsx';
import './TreeGroupTags.css';

export function TreeGroupTagButton({onClick,onSelect,selectionOn,showLabel=false,disabled=false,label='Tag this group',count}){
  const tag=<button type="button" className="tree-group-tag-button" disabled={disabled} onClick={onClick} aria-label={`${label} · ${number(count)} matching epochs`} title={`${label} · ${number(count)} matching epochs`}><Tag size={13}/>{(onSelect||showLabel)&&<span>Tag</span>}</button>;
  return onSelect?<span className="incoming-tree-actions">{typeof selectionOn==='boolean'?<button type="button" role="switch" className="incoming-selection-switch" disabled={disabled||!Number.isSafeInteger(count)||count<1||count>1000} aria-checked={selectionOn} aria-label={`Select all downstream epochs · ${number(count)} epochs`} title={count>1000?"Select at most 1,000 epochs; choose a smaller branch":selectionOn?"Deselect this branch and every downstream epoch":"Select this branch and every downstream epoch"} onClick={onSelect}><span className="incoming-switch-track" aria-hidden="true"><span/></span><span>{selectionOn?'Selected':'Select'}</span></button>:<button type="button" className="incoming-explicit-select" disabled={disabled||!Number.isSafeInteger(count)||count<1||count>1000} aria-label={`Select all downstream epochs · ${number(count)} epochs`} title="Select every scoped epoch below this group" onClick={onSelect}><CheckSquare size={13}/><span>Select</span></button>}{tag}</span>:tag;
}
function GroupDialog({state,onClose,onChoose,onChanged}){
  const dialog=useRef(null);
  useLayoutEffect(()=>{
    const node=dialog.current;node.showModal();
    return()=>{node.close();if(state.trigger?.isConnected&&!state.trigger.disabled)state.trigger.focus({preventScroll:true});};
  },[]);
  return createPortal(<dialog ref={dialog} className="tree-group-tags-dialog" aria-label={state.title} onCancel={event=>{event.preventDefault();onClose();}} onKeyDown={event=>event.stopPropagation()}>
    <header><strong>{state.title}</strong><button type="button" aria-label="Close group tags" onClick={onClose}><X size={16}/></button></header>
    <p>{state.label} · <strong>{number(state.count)} matching epochs when opened</strong></p>
    <p>Shared tags belong to your author profile. Dataset tags and protocol review decisions are separate.</p>
    {state.scope?.readContext&&!state.loading&&<div className="tree-group-tag-choices" role="group" aria-label="Choose tag target">{state.cellUuid&&<button type="button" onClick={()=>onChoose('cell')}>Tag This Cell</button>}{!state.singleEpoch&&<button type="button" onClick={()=>onChoose('epoch')}>Tag All Downstream Epochs · {number(state.count)}</button>}</div>}
    {!state.scope?.readContext&&state.cellUuid&&!state.target&&<div className="tree-group-tag-choices" role="group" aria-label="Choose tag target"><button type="button" disabled={state.loading} onClick={()=>onChoose('cell')}>Tag cell · 1 cell</button><button type="button" disabled={state.loading} onClick={()=>onChoose('epoch')}>Tag matching epochs · {number(state.count)} epochs</button></div>}
    {state.loading&&<p role="status">Verifying the complete group on the server… <button type="button" onClick={onClose}>Cancel</button></p>}
    {state.error&&<p className="annotation-error" role="alert">{state.error}</p>}
    {state.target&&<><p><strong>Target: {state.target.kind==='cell'?'1 recorded cell · inherited cell tag':`${number(state.target.count)} epochs · frozen selection`}</strong></p><p>{state.target.kind==='cell'?'This tag belongs to the recorded cell UUID.':'Saving uses the complete group’s captured epoch identities. They remain the targets if a recording stops matching before the write completes; later tag changes cannot add targets. Closing this editor does not cancel a submitted save.'}</p><AnnotationTags epoch={state.target.epoch} revision={state.revision} targetScope={state.target.kind==='cell'?'cell':state.singleEpoch?'epoch':'selected'} selectedEpochs={state.target.kind==='epoch'&&!state.singleEpoch?(state.target.ids||[]):[]} focusRequest={1} reconcileReceipt groupMutation={state.target.groupMutation} verifyTarget={state.target.kind==='cell'&&!state.directCell?({signal})=>verifyTreeGroup(state.scope,state.revision,api,{signal}):undefined} onChange={onChanged}/></>}
  </dialog>,document.body);
}

export function useTreeGroupTags(props){
  const {profileUuid,openProfile}=useAnnotationProfile();
  const [state,setState]=useState(null),[revision,setRevision]=useState(0);
  const stateRef=useRef(null),request=useRef(null),generation=useRef(0),committedScope=useRef(null),current=useRef(props);current.current=props;stateRef.current=state;
  const scopeKey=JSON.stringify({protocolId:props.protocolId,predicate:props.predicate,filters:props.filters||{},splits:props.splits||'',revision:props.revision,expectedRevision:props.expectedRevision,readContext:props.readContext,actionsDisabled:props.actionsDisabled,profileUuid});
  function close(){void releaseGroupPreview(stateRef.current?.target,api);generation.current++;request.current?.abort();request.current=null;setState(null);}
  useLayoutEffect(()=>{committedScope.current=scopeKey;close();return()=>{committedScope.current=null;generation.current++;request.current?.abort();void releaseGroupPreview(stateRef.current?.target,api);};},[scopeKey]);
  async function choose(kind,entry=state){
    if(committedScope.current!==scopeKey)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;const token=++generation.current;
    setState({...entry,loading:true,error:'',progress:0});
    try{
      const args={scope:entry.scope,path:entry.path,revision:entry.revision,count:entry.count,request:api,signal:controller.signal};
      if(kind!=='cell'&&!profileUuid){openProfile?.();throw Error('Choose a tag author profile, then reopen this group.');}
      const target=kind==='cell'?(entry.directCell?{kind:'cell',count:1,ids:[entry.cellEpoch.epoch_uuid],epoch:entry.cellEpoch}:await resolveTreeGroup({...args,cellUuid:entry.cellUuid})):entry.downstream?{kind:'epoch',epoch:entry.cellEpoch,ids:await loadIncomingSelection({...entry.downstream,cellUuid:entry.cellUuid,request:api,signal:controller.signal}),count:entry.count}:entry.scope.readContext?await resolveTreeGroup(args):await previewTreeGroup({...args,profileUuid});
      if(token===generation.current&&!controller.signal.aborted)setState({...entry,target,loading:false,error:''});
      else void releaseGroupPreview(target,api);
    }catch(error){if(token===generation.current&&!controller.signal.aborted)setState({...entry,loading:false,error:error.message});}
  }
  function open(item,field,page,event,{level=false}={}){
    if(props.actionsDisabled||committedScope.current!==scopeKey)return;
    event?.preventDefault();event?.stopPropagation();
    const scope=JSON.parse(scopeKey);
    const cellUuid=!level&&field?.field==='cell'&&!item.missing&&typeof item.value==='string'&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(item.value)?item.value:null;
    const entry={title:level?'Tag this level':'Tag this group',label:level?`${field?.label||field?.field} · all groups at this level`:branchLabel(item,field?.field),path:[...(item.path||[])],count:item.count,revision:page.revision,cellUuid,scope,trigger:event?.currentTarget||document.activeElement,error:'',progress:0};
    close();setState(entry);
    if(scope.readContext){if(cellUuid)choose('cell',entry);return;}
    if(!cellUuid)choose('epoch',entry);
  }
  function openEpoch(epoch,event,cell=false,downstream=null){
    if(props.actionsDisabled||committedScope.current!==scopeKey)return;
    event?.preventDefault();event?.stopPropagation();close();
    setState({title:cell?'Tag This Cell':'Tag This Epoch',label:`Epoch ${epoch.epoch_number??epoch.epoch_uuid}`,count:downstream?.cells.find(value=>value.cell_uuid===epoch.cell_uuid)?.epochs??1,revision:props.revision,scope:JSON.parse(scopeKey),singleEpoch:!cell,cellUuid:cell?epoch.cell_uuid:null,cellEpoch:epoch,downstream,trigger:event?.currentTarget,target:{kind:cell?'cell':'epoch',count:1,ids:[epoch.epoch_uuid],epoch},directCell:cell});
  }
  function changed(result,confirmed){
    // AnnotationTags still reports submitted durable writes after dismissal.
    // Never attach this receipt to a newly focused group or substitute targets.
    current.current.onAnnotationsChanged?.(result,confirmed);
    close();setRevision(value=>value+1);
  }
  return {open,openEpoch,revision,dialog:state?<GroupDialog key={`${state.revision}:${JSON.stringify(state.path)}`} state={state} onClose={close} onChoose={choose} onChanged={changed}/>:null};
}
