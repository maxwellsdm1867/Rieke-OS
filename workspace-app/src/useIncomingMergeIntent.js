import {useEffect,useRef,useState} from 'react';
import {mergeIntentMatches} from './incomingMergeIntent.js';
export default function useIncomingMergeIntent({intent,claim,projectId,protocolId,queue,onOpen}){
  const seen=useRef(new Set()),[pending,setPending]=useState(null),[message,setMessage]=useState('');
  useEffect(()=>{
    if(!intent||seen.current.has(intent.request_uuid))return;
    seen.current.add(intent.request_uuid);
    const authorized=claim?.(intent)===true;
    if(!authorized||!mergeIntentMatches(intent,projectId,protocolId)){setMessage('This merge request is no longer active for this project and protocol. Use Merge all to request a new preview.');return;}
    setPending(intent);setMessage('');onOpen();
  },[intent,claim,projectId,protocolId,onOpen]);
  function finish(message=''){setPending(null);setMessage(message);}
  useEffect(()=>{
    if(!pending)return;
    if(!mergeIntentMatches(pending,projectId,protocolId)){finish('The destination changed. Request a new merge preview.');return;}
    if(queue.loading)return;
    if(queue.error){finish('The incoming queue could not be refreshed. Refresh it before requesting a merge preview.');return;}
    if(!queue.data)return;
    if(!queue.data.capabilities?.cumulative_pending_browse||!queue.data.capabilities?.additive_accept){finish('Cumulative additive merging is unavailable. Inspect the saved proposals in Workbench.');return;}
    if(!Number.isSafeInteger(queue.data.pending_epoch_count)){finish('The pending count is unavailable. Refresh before requesting a merge preview.');return;}
    if(queue.data.pending_epoch_count===0)finish('No pending incoming recordings to merge.');
  },[pending,projectId,protocolId,queue.loading,queue.error,queue.data]);
  return {pending,message,finish};
}
