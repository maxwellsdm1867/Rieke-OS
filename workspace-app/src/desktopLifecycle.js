const savers=new Set(),writes=new Set(),unmountGuards=new Set();
let closing=false,unmounting=false;
export const desktopBridge=()=>globalThis.window?.riekeDesktop || null;
export function registerDraftSaver(save){savers.add(save);return()=>savers.delete(save);}
export function assertDesktopWritable(path){if(closing)throw new Error('DISCO is closing; new changes are paused.');if(unmounting&&path!=='/projects/unmount')throw new Error('Project is unmounting; new changes are paused.');}
export function registerUnmountGuard(check){unmountGuards.add(check);return()=>unmountGuards.delete(check);}
export function beginProjectUnmount(retry=false){
 if(closing||(unmounting&&!retry)||writes.size)throw new Error('Wait for pending changes, accepts and exports to finish before unmounting.');
 if(!retry)for(const check of unmountGuards){const reason=check();if(reason)throw new Error(reason);}
 unmounting=true;return()=>{unmounting=false;};
}
export function trackWrite(operation){
  writes.add(operation);
  operation.then(()=>writes.delete(operation),()=>writes.delete(operation));
  return operation;
}
export const hasPendingDesktopWrites=()=>writes.size>0;
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
// Before submitting an idempotent acceptance (replay by operation_uuid returns
// the existing receipt), pending accepted writes still gate submission, but a
// failed view snapshot does not: the saved view is a convenience, not consent.
// Close/unmount keep the strict flushDesktopDrafts contract above.
export async function flushBeforeSubmission(){
  const accepted=await Promise.allSettled([...writes]);
  const views=await Promise.allSettled([...savers].map(save=>Promise.resolve().then(save)));
  const failed=accepted.filter(result=>result.status==='rejected');
  if(failed.length)throw new Error(failed.every(result=>result.reason?.saved===true)?'Accepted changes were committed to the database, but recovery backup coverage is incomplete.':'Some accepted changes were not confirmed. Existing operation records must be reconciled on relaunch.');
  const viewSaved=views.every(result=>result.status==='fulfilled');
  return {viewSaved,notice:viewSaved?'':'The latest view could not be saved; the merge was still submitted. The last saved view is retained.'};
}
export function installDesktopLifecycle(bridge=desktopBridge()){
  if(!bridge)return()=>{};
  let releaseCheckpoint=null;
  const resume=bridge.onProjectResume?.(()=>{releaseCheckpoint?.();releaseCheckpoint=null;});
  const status=bridge.onStatus?.(value=>{closing=['Closing','Recovery','IntegrityRecovery'].includes(value.state);});
  const prepare=bridge.onPrepareClose(async ({requestId,purpose})=>{
    const checkpoint=purpose==='project-checkpoint';
    if(!checkpoint)closing=true;
    let ok=false,reason;
    try{
      if(checkpoint)releaseCheckpoint=beginProjectUnmount(unmounting);
      await flushDesktopDrafts();ok=true;
    }catch(error){reason=error.message;if(checkpoint){releaseCheckpoint?.();releaseCheckpoint=null;}}
    // Explicit quit may have reached its deadline before a delayed write ends.
    try{await bridge.acknowledgeDrafts(requestId,{ok,...(reason?{reason}:{})});}catch{}
  });
  return()=>{prepare?.();status?.();resume?.();releaseCheckpoint?.();closing=false;};
}
