// Sequential polling prevents a slow scan from overlapping itself. The first
// scan only establishes the baseline; it invalidates loaded data only when it
// ingested tag messages during this session (received at or after start), since
// earlier receipts were already part of every read the app has made.
export function startExternalTagMonitor({scan,onChange,onStatus,onError,visible=()=>true,
  schedule=setTimeout,cancel=clearTimeout,interval=3000,startedAt=Date.now()}){
  let stopped=false,running=false,timer=null,revision=null,failures=0;
  const ingestedNow=result=>Array.isArray(result.receipts)&&result.receipts.some(item=>item?.addition_count>0&&Date.parse(item.received_at)>=startedAt);
  async function check(){
    if(stopped||running)return;
    cancel(timer);running=true;
    try{
      const result=await scan();
      if(stopped)return;
      if(typeof result?.revision!=='string')throw new Error('Tag scan did not return an annotation revision.');
      if(revision!==result.revision){const baseline=revision===null;revision=result.revision;if(!baseline||ingestedNow(result))onChange();}
      failures=0;onStatus(result);
    }catch(error){if(!stopped){failures++;onError(error.message);}}
    finally{running=false;if(!stopped)timer=schedule(()=>visible()?check():arm(),Math.min(30000,interval*2**failures));}
  }
  function arm(){if(!stopped)timer=schedule(()=>visible()?check():arm(),interval);}
  check();
  return {check,stop(){stopped=true;cancel(timer);}};
}
