import {useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Tag,X} from 'lucide-react';
import {api,number} from '../api.js';
import {resolveTreeGroup,verifyTreeGroup} from '../treeGroupTargets.js';
import {useAnnotationProfile} from '../annotationProfile.js';
import {previewTreeGroup,releaseGroupPreview} from '../treeGroupQueryTags.js';
import {branchLabel} from '../treeBranchPresentation.js';
import AnnotationTags from './AnnotationTags.jsx';
import './TreeGroupTags.css';

export function TreeGroupTagButton({onClick,disabled=false,label='Tag this group',count}){
  return <button type="button" className="tree-group-tag-button" disabled={disabled} onClick={onClick} aria-label={`${label} · ${number(count)} matching epochs`} title={`${label} · ${number(count)} matching epochs`}><Tag size={13}/></button>;
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
    {state.cellUuid&&!state.target&&<div className="tree-group-tag-choices" role="group" aria-label="Choose tag target"><button type="button" disabled={state.loading} onClick={()=>onChoose('cell')}>Tag cell · 1 cell</button><button type="button" disabled={state.loading} onClick={()=>onChoose('epoch')}>Tag matching epochs · {number(state.count)} epochs</button><small>A cell tag is inherited by every epoch of this recorded cell, across protocols and outside the matching group.</small></div>}
    {state.loading&&<p role="status">Verifying the complete group on the server… <button type="button" onClick={onClose}>Cancel</button></p>}
    {state.error&&<p className="annotation-error" role="alert">{state.error}</p>}
    {state.target&&<><p><strong>Target: {state.target.kind==='cell'?'1 recorded cell · inherited cell tag':`${number(state.target.count)} epochs · frozen selection`}</strong></p><p>{state.target.kind==='cell'?'This tag belongs to the recorded cell UUID.':'Saving uses the complete group’s captured epoch identities. They remain the targets if a recording stops matching before the write completes; later tag changes cannot add targets. Closing this editor does not cancel a submitted save.'}</p><AnnotationTags epoch={state.target.epoch} revision={state.revision} targetScope={state.target.kind==='cell'?'cell':'selected'} selectedEpochs={state.target.kind==='epoch'?(state.target.ids||[]):[]} focusRequest={1} reconcileReceipt groupMutation={state.target.groupMutation} verifyTarget={state.target.kind==='cell'?({signal})=>verifyTreeGroup(state.scope,state.revision,api,{signal}):undefined} onChange={onChanged}/></>}
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
      const target=kind==='cell'?await resolveTreeGroup({...args,cellUuid:entry.cellUuid}):await previewTreeGroup({...args,profileUuid});
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
    if(scope.readContext){setState({...entry,error:'Shared group tags are not supported in Incoming Workbench yet.'});return;}
    if(!cellUuid)choose('epoch',entry);
  }
  function changed(result,confirmed){
    // AnnotationTags still reports submitted durable writes after dismissal.
    // Never attach this receipt to a newly focused group or substitute targets.
    current.current.onAnnotationsChanged?.(result,confirmed);
    close();setRevision(value=>value+1);
  }
  return {open,revision,dialog:state?<GroupDialog key={`${state.revision}:${JSON.stringify(state.path)}`} state={state} onClose={close} onChoose={choose} onChanged={changed}/>:null};
}
