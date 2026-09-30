const savers=new Set(),writes=new Set();
let closing=false;
export const desktopBridge=()=>globalThis.window?.riekeDesktop || null;
export function registerDraftSaver(save){savers.add(save);return()=>savers.delete(save);}
export function assertDesktopWritable(){if(closing)throw new Error('Disco is closing; new changes are paused.');}
export function trackWrite(operation){
  writes.add(operation);
  operation.then(()=>writes.delete(operation),()=>writes.delete(operation));
  return operation;
}
export async function flushDesktopDrafts(){
  const accepted=await Promise.allSettled([...writes]);
  const views=await Promise.allSettled([...savers].map(save=>Promise.resolve().then(save)));
  const failed=accepted.filter(result=>result.status==='rejected');
  const backupOnly=failed.length>0&&failed.every(result=>result.reason?.saved===true);
  const reasons=[];
  if(failed.length)reasons.push(backupOnly?'Accepted changes were committed to the database, but recovery backup coverage is incomplete.':'Some accepted changes were not confirmed. Existing operation records must be reconciled on relaunch.');
  if(views.some(result=>result.status==='rejected'))reasons.push('The latest view could not be saved. The last saved view is retained.');
  if(reasons.length)throw new Error(reasons.join(' '));
}
export function installDesktopLifecycle(bridge=desktopBridge()){
  if(!bridge)return()=>{};
  const status=bridge.onStatus?.(value=>{closing=value.state==='Closing';});
  const prepare=bridge.onPrepareClose(async ({requestId})=>{
    closing=true;let ok=false,reason;
    try{await flushDesktopDrafts();ok=true;}catch(error){reason=error.message;}
    // Explicit quit may have reached its deadline before a delayed write ends.
    try{await bridge.acknowledgeDrafts(requestId,{ok,...(reason?{reason}:{})});}catch{}
  });
  return()=>{prepare?.();status?.();closing=false;};
}
