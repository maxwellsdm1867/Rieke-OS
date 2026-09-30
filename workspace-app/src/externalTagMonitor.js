// Sequential polling prevents a slow scan from overlapping itself. A first scan
// also invalidates data fetched before pending messages were ingested on reopen.
export function startExternalTagMonitor({scan,onChange,onStatus,onError,visible=()=>true,
  schedule=setTimeout,cancel=clearTimeout,interval=3000}){
  let stopped=false,running=false,timer=null,revision=null,failures=0;
  async function check(){
    if(stopped||running)return;
    cancel(timer);running=true;
    try{
      const result=await scan();
      if(stopped)return;
      if(typeof result?.revision!=='string')throw new Error('Tag scan did not return an annotation revision.');
      if(revision!==result.revision){revision=result.revision;onChange();}
      failures=0;onStatus(result);
    }catch(error){if(!stopped){failures++;onError(error.message);}}
    finally{running=false;if(!stopped)timer=schedule(()=>visible()?check():arm(),Math.min(30000,interval*2**failures));}
  }
  function arm(){if(!stopped)timer=schedule(()=>visible()?check():arm(),interval);}
  check();
  return {check,stop(){stopped=true;cancel(timer);}};
}
