import {useLayoutEffect,useRef,useState} from 'react';
import {CheckSquare} from 'lucide-react';
import {api} from '../../api.js';
import {resolveTreeGroup} from '../../treeGroupTargets.js';
import {mergeEpochSelection,toggleEpochSelection} from '../../epochSelection.js';

export function IncomingEpochSelect({epoch,selected=[],onSelect,disabled=false}){
  if(!onSelect)return null;
  const checked=selected.includes(epoch.epoch_uuid);
  return <button type="button" className="incoming-explicit-select" aria-label={`${checked?'Deselect':'Select'} epoch ${epoch.epoch_number??epoch.epoch_uuid}`} aria-pressed={checked} disabled={disabled||!checked&&selected.length>=1000} onClick={event=>{event.stopPropagation();onSelect(toggleEpochSelection(selected,epoch.epoch_uuid));}}><CheckSquare size={13}/><span>Select</span></button>;
}
export function useIncomingTreeSelection(props){
  const [error,setError]=useState(''),[working,setWorking]=useState(false),controller=useRef(null),current=useRef(props),committed=useRef(null);
  current.current=props;
  const scopeKey=JSON.stringify([props.protocolId,props.readContext,props.filters,props.splits,props.revision,props.expectedRevision,props.actionsDisabled]);
  useLayoutEffect(()=>{committed.current=scopeKey;return()=>{committed.current=null;controller.current?.abort();};},[scopeKey]);
  async function select(item,page,event){
    event?.preventDefault();event?.stopPropagation();
    if(!props.readContext||props.actionsDisabled||controller.current)return;
    const request=new AbortController();controller.current=request;setWorking(true);setError('');
    const before=JSON.stringify(props.selectedEpochs||[]);
    try{
      const target=await resolveTreeGroup({scope:props,path:item.path||[],revision:page.revision,count:item.count,request:api,signal:request.signal});
      if(request.signal.aborted||committed.current!==scopeKey)return;
      if(JSON.stringify(current.current.selectedEpochs||[])!==before)throw Error('Selection changed while loading. Select this group again.');
      current.current.setSelectedEpochs?.(mergeEpochSelection(current.current.selectedEpochs||[],target.ids));
    }catch(error){if(committed.current!==null)setError(error.name==='AbortError'?'Tree changed while selecting. Select the group again.':error.message);}
    finally{if(controller.current===request){controller.current=null;setWorking(false);}}
  }
  return {select:props.readContext&&props.setSelectedEpochs?select:null,working,feedback:error?<p className="incoming-tree-feedback" role="alert">{error}</p>:working?<p className="incoming-tree-feedback" role="status">Selecting all downstream epochs…</p>:null};
}
