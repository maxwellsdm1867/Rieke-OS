// Coalesce rapid navigation before starting I/O, and ignore completions from
// superseded requests even when the transport cannot cancel its server work.
export function startResourceRequest({path,delayMs=0,request,onData,onError}){
  const controller=new AbortController();
  const run=()=>Promise.resolve().then(()=>{
    if(controller.signal.aborted)return;
    return request(path,{signal:controller.signal});
  }).then(data=>{if(!controller.signal.aborted)onData(data);})
    .catch(error=>{if(!controller.signal.aborted)onError(error);});
  const timer=delayMs>0?setTimeout(run,delayMs):null;
  if(timer===null)run();
  return ()=>{if(timer!==null)clearTimeout(timer);controller.abort();};
}
export function visibleResourceState({state,path,revision,nonce,hit}){
  if(hit!==undefined)return {data:hit,loading:false,error:null,path,revision,nonce};
  if(state.path===path&&state.revision===revision&&state.nonce===nonce)return state;
  return {data:null,loading:!!path,error:null,path,revision,nonce};
}
