import {useLayoutEffect,useRef,useState} from 'react';
import {api} from '../../api.js';
import {resolveTreeGroup} from "../../annotations/treeGroupTargets.js";
import {mergeEpochSelection,toggleEpochSelection} from '../../epochSelection.js';
import {incomingTreeSelectionScope,incomingBranchOn,incomingBranchCommand} from '../incomingSelection.js';

export function IncomingEpochSelect({epoch,selected=[],onSelect,disabled=false}){
  if(!onSelect)return null;
  const checked=selected.includes(epoch.epoch_uuid);
  return <button type="button" role="switch" className="incoming-selection-switch" aria-label={`Select epoch ${epoch.epoch_number??epoch.epoch_uuid}`} aria-checked={checked} title={checked?'Deselect this epoch':'Select this epoch'} disabled={disabled||!checked&&selected.length>=1000} onClick={event=>{event.stopPropagation();onSelect(toggleEpochSelection(selected,epoch.epoch_uuid));}}><span className="incoming-switch-track" aria-hidden="true"><span/></span><span>{checked?'Deselect':'Select'}</span></button>;
}
export function useIncomingTreeSelection(props,page=null){
  const [error,setError]=useState(''),[working,setWorking]=useState(false),[localIntent,setLocalIntent]=useState(null),controller=useRef(null),interrupted=useRef(false),current=useRef(props),committed=useRef(null);
  current.current=props;
  const scopeKey=incomingTreeSelectionScope(props),operationKey=JSON.stringify([scopeKey,props.actionsDisabled,props.active]);
  const intent=props.treeSelectionIntent===undefined?localIntent:props.treeSelectionIntent;
  const changeIntent=value=>props.onTreeSelectionIntentChange?props.onTreeSelectionIntentChange(value):setLocalIntent(value);
  const intentRef=useRef(intent);intentRef.current=intent;
  const rootCurrent=props.active!==false&&!props.actionsDisabled&&page&&page.candidate_scope_revision===props.readContext?.candidate_scope_revision;
  // Global Select/Deselect all can run in the epoch list before a tree exists.
  // Bind its command only when a fresh tree page for that same view is available.
  useLayoutEffect(()=>{
    if(intent&&intent.scope!==scopeKey){if(props.treeSelectionIntent===undefined)setLocalIntent(null);return;}
    if(rootCurrent&&intent?.scope===scopeKey){
      if(intent.revision===null)changeIntent({...intent,revision:page.revision});
      else if(intent.revision!==page.revision)changeIntent(null);
    }
  },[rootCurrent,page?.revision,scopeKey,intent]);
  useLayoutEffect(()=>{
    committed.current=operationKey;
    if(interrupted.current){
      interrupted.current=false;setWorking(false);
      if(!current.current.onTreeSelectionFeedback)setError('The view refreshed before this selection finished. Switch the branch again.');
    }
    return()=>{
      committed.current=null;
      const pending=controller.current;
      if(pending){
        interrupted.current=true;controller.current=null;pending.abort();
        current.current.onTreeSelectionFeedback?.('The view refreshed before this selection finished. Switch the branch again.');
      }
    };
  },[operationKey]);
  function on(item,branchPage){return incomingBranchOn(intent,scopeKey,branchPage?.revision,item.path||[]);}
  async function select(item,branchPage,event){
    event?.preventDefault();event?.stopPropagation();
    if(!props.readContext||props.actionsDisabled||props.active===false||controller.current||committed.current!==operationKey)return;
    const request=new AbortController();controller.current=request;setWorking(true);setError('');current.current.onTreeSelectionFeedback?.('');
    const before=JSON.stringify(props.selectedEpochs||[]),beforeIntent=intent,nextOn=!on(item,branchPage),path=item.path||[];
    try{
      if(item.count>1000)throw Error('Switch at most 1,000 epochs at a time. Filter this view or choose a smaller branch.');
      const target=await resolveTreeGroup({scope:props,path,revision:branchPage.revision,count:item.count,request:api,signal:request.signal});
      if(request.signal.aborted||committed.current!==operationKey)return;
      if(JSON.stringify(current.current.selectedEpochs||[])!==before||intentRef.current!==beforeIntent)throw Error('Selection changed while loading. Switch this group again.');
      const selected=current.current.selectedEpochs||[],remove=new Set(target.ids);
      const next=nextOn?mergeEpochSelection(selected,target.ids):selected.filter(id=>!remove.has(id));
      const nextIntent=incomingBranchCommand(intent,scopeKey,branchPage.revision,path,nextOn);
      current.current.setSelectedEpochs?.(next);
      changeIntent(nextIntent);
    }catch(error){if(controller.current===request&&committed.current===operationKey)setError(error.name==='AbortError'?'Tree changed while selecting. Switch the group again.':error.message);}
    finally{if(controller.current===request){controller.current=null;setWorking(false);}}
  }
  return {select:props.readContext&&props.setSelectedEpochs?select:null,on,working,feedback:error?<p className="incoming-tree-feedback" role="alert">{error}</p>:working?<p className="incoming-tree-feedback" role="status">Updating downstream selection…</p>:null};
}
