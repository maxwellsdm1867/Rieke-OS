import {useLayoutEffect,useMemo,useRef,useState} from 'react';
import {api} from '../../api.js';
import {resolveIncomingTreeSelection} from "../incomingTreeSelection.js";
import {useWorkspaceRequest} from "../../workspaceRequest.js";
import {mergeEpochSelection,toggleEpochSelection} from '../../epochSelection.js';
import {incomingTreeSelectionScope,incomingBranchOn,incomingBranchCommand} from '../incomingSelection.js';

export function IncomingEpochSelect({epoch,selected=[],onSelect,onToggle,disabled=false}){
  if(!onSelect)return null;
  const checked=selected.includes(epoch.epoch_uuid);
  return <button type="button" role="switch" className="incoming-selection-switch" aria-label={`Select epoch ${epoch.epoch_number??epoch.epoch_uuid}`} aria-checked={checked} title={`${checked?'Deselect':'Select'} this epoch${onToggle?'; Shift-click to select or deselect a range':''}`} disabled={disabled} onClick={event=>{event.stopPropagation();if(onToggle)onToggle(event);else onSelect(toggleEpochSelection(selected,epoch.epoch_uuid,Infinity));}}><span className="incoming-switch-track" aria-hidden="true"><span/></span><span>{checked?'Deselect':'Select'}</span></button>;
}
export function useIncomingTreeSelection(props,page=null){
  const request=useWorkspaceRequest(api);
  const [error,setError]=useState(''),[working,setWorking]=useState(false),[localIntent,setLocalIntent]=useState(null),[,renderQueue]=useState(0);
  const current=useRef(props),owner=useRef(null),interrupted=useRef(false);current.current=props;
  const scopeKey=incomingTreeSelectionScope(props),operationKey=JSON.stringify([scopeKey,props.actionsDisabled,props.active,props.selectionAuthority?.identity]);
  const lifetime=useMemo(()=>({operationKey}),[operationKey,request]);
  const intent=props.treeSelectionIntent===undefined?localIntent:props.treeSelectionIntent;
  const intentRef=useRef(intent);intentRef.current=intent;
  const selection=()=>JSON.stringify(current.current.selectedEpochs||[]);
  const changeIntent=value=>current.current.onTreeSelectionIntentChange?current.current.onTreeSelectionIntentChange(value):setLocalIntent(value);
  const rootCurrent=props.active!==false&&!props.actionsDisabled&&page&&page.candidate_scope_revision===props.readContext?.candidate_scope_revision;
  useLayoutEffect(()=>{
    if(intent&&intent.scope!==scopeKey){if(props.treeSelectionIntent===undefined)setLocalIntent(null);return;}
    if(rootCurrent&&intent?.scope===scopeKey){
      if(intent.revision===null)changeIntent({...intent,revision:page.revision});
      else if(intent.revision!==page.revision)changeIntent(null);
    }
  },[rootCurrent,page?.revision,scopeKey,intent]);
  function cancel(q,message){
    q.active?.controller.abort();for(const command of q.commands)command.done();
    q.commands=[];q.active=null;q.awaiting=null;q.projected=intentRef.current;q.expectedIntent=intentRef.current;q.expectedSelection=selection();
    if(owner.current===q&&q.live){setWorking(false);renderQueue(value=>value+1);if(message){setError(message);current.current.onTreeSelectionFeedback?.(message);}}
  }
  useLayoutEffect(()=>{
    const q={lifetime,live:true,commands:[],active:null,awaiting:null,projected:intentRef.current,expectedIntent:intentRef.current,expectedSelection:selection()};owner.current=q;
    if(interrupted.current){interrupted.current=false;setWorking(false);if(!current.current.onTreeSelectionFeedback)setError('The view refreshed before this selection finished. Switch the branch again.');}
    return()=>{
      q.live=false;
      if(q.commands.length){interrupted.current=true;current.current.onTreeSelectionFeedback?.('The view refreshed before this selection finished. Switch the branch again.');}
      q.active?.controller.abort();for(const command of q.commands)command.done();q.commands=[];
      if(owner.current===q)owner.current=null;
    };
  },[lifetime]);
  function pump(q){
    if(owner.current!==q||!q.live||q.active||q.awaiting||!q.commands.length)return;
    if(selection()!==q.expectedSelection||intentRef.current!==q.expectedIntent){cancel(q,'Selection changed while loading. Switch this group again.');return;}
    const command=q.commands[0],controller=new AbortController();q.active={command,controller};setWorking(true);
    resolveIncomingTreeSelection({scope:current.current,path:command.path,revision:command.revision,count:command.count,request,signal:controller.signal}).then(ids=>{
      if(owner.current!==q||!q.live||controller.signal.aborted)return;
      if(selection()!==q.expectedSelection||intentRef.current!==q.expectedIntent)throw Error('Selection changed while loading. Switch this group again.');
      const remove=new Set(ids),selected=current.current.selectedEpochs||[];
      const next=command.on?mergeEpochSelection(selected,ids,props.readContext?.selection_manifests?Infinity:1000):selected.filter(id=>!remove.has(id));
      const nextIntent=incomingBranchCommand(q.expectedIntent,scopeKey,command.revision,command.path,command.on);
      q.awaiting={beforeSelection:q.expectedSelection,beforeIntent:q.expectedIntent};q.expectedSelection=JSON.stringify(next);q.expectedIntent=nextIntent;
      q.commands.shift();q.active=null;
      current.current.setSelectedEpochs?.(next);changeIntent(nextIntent);
      setWorking(q.commands.length>0);renderQueue(value=>value+1);command.done();
    }).catch(error=>{if(owner.current===q&&q.live&&!controller.signal.aborted)cancel(q,error.message);});
  }
  // A following command starts only after BOTH controlled publications commit.
  // Intermediate commits may contain either old or new values, never unrelated ones.
  useLayoutEffect(()=>{
    const q=owner.current;if(!q?.live)return;
    if(q.awaiting){
      if(selection()===q.expectedSelection&&intent===q.expectedIntent)q.awaiting=null;
      else if(![q.expectedSelection,q.awaiting.beforeSelection].includes(selection())||![q.expectedIntent,q.awaiting.beforeIntent].includes(intent)){cancel(q,'Selection changed while loading. Switch this group again.');return;}
      else return;
    }
    if(q.commands.length){if(selection()!==q.expectedSelection||intent!==q.expectedIntent){cancel(q,'Selection changed while loading. Switch this group again.');return;}}
    else{q.expectedSelection=selection();q.expectedIntent=intent;q.projected=intent;}
    pump(q);
  });
  function on(item,branchPage){return incomingBranchOn(intent,scopeKey,branchPage?.revision,item.path||[]);}
  function pending(item,branchPage){return owner.current?.lifetime===lifetime?owner.current.commands.findLast(command=>command.revision===branchPage?.revision&&JSON.stringify(command.path)===JSON.stringify(item.path||[])):undefined;}
  function select(item,branchPage,event){
    event?.preventDefault();event?.stopPropagation();
    const q=owner.current;
    if(!props.readContext||props.actionsDisabled||props.active===false||!q?.live||q.lifetime!==lifetime)return Promise.resolve();
    if(!Number.isSafeInteger(item.count)||item.count<1||!props.readContext?.selection_manifests&&item.count>1000){cancel(q,'The complete branch count is unavailable. Refresh this view.');return Promise.resolve();}
    if(q.commands.length>=32){cancel(q,'Too many pending selection changes. Wait for the current view and select again.');return Promise.resolve();}
    const path=[...(item.path||[])],nextOn=!incomingBranchOn(q.projected,scopeKey,branchPage.revision,path);
    q.projected=incomingBranchCommand(q.projected,scopeKey,branchPage.revision,path,nextOn);
    let done;const result=new Promise(resolve=>{done=resolve;});q.commands.push({path,revision:branchPage.revision,count:item.count,on:nextOn,done});
    setError('');current.current.onTreeSelectionFeedback?.('');setWorking(true);renderQueue(value=>value+1);pump(q);return result;
  }
  return {select:props.readContext&&props.setSelectedEpochs?select:null,on,pending,working,feedback:error?<p className="incoming-tree-feedback" role="alert">{error}</p>:working?<p className="incoming-tree-feedback tree-transient-status" role="status">Updating downstream selection…</p>:null};
}
