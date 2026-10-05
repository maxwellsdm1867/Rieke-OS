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

// A pool belongs to one transport/scope. Callers supply the complete read key;
// completed responses are never retained here. Each consumer owns its signal.
export function createSharedReads(request,{deferAbort=false}={}){
  const pending=new Map();
  function load(key,path,options={}){
    const {signal,...requestOptions}=options;
    const cancelled=()=>Object.assign(new Error('Request cancelled'),{name:'AbortError'});
    if(signal?.aborted)return Promise.reject(cancelled());
    let entry=pending.get(key);
    if(!entry){
      entry={controller:new AbortController(),consumers:new Set(),abortTimer:null};
      pending.set(key,entry);
      const settle=(error,data)=>{
        if(pending.get(key)===entry)pending.delete(key);
        clearTimeout(entry.abortTimer);
        for(const consumer of entry.consumers){consumer.cleanup();error?consumer.reject(error):consumer.resolve(data);}
        entry.consumers.clear();
      };
      let work;
      try{work=request(path,{...requestOptions,signal:entry.controller.signal});}catch(error){work=Promise.reject(error);}
      Promise.resolve(work).then(data=>settle(null,data),error=>settle(error));
    }
    clearTimeout(entry.abortTimer);entry.abortTimer=null;
    return new Promise((resolve,reject)=>{
      const consumer={resolve,reject,cleanup:()=>signal?.removeEventListener('abort',abort)};
      function abort(){
        consumer.cleanup();entry.consumers.delete(consumer);reject(cancelled());
        if(!entry.consumers.size){
          // Let the foreground subscribe during the same React effect commit,
          // including cached-metadata continuations, before retiring prefetch.
          const retire=()=>{
            if(entry.consumers.size||pending.get(key)!==entry)return;
            pending.delete(key);entry.controller.abort();
          };
          if(deferAbort)entry.abortTimer=setTimeout(retire,0);else retire();
        }
      }
      entry.consumers.add(consumer);signal?.addEventListener('abort',abort,{once:true});
    });
  }
  return {load};
}
