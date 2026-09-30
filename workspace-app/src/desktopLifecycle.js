const savers=new Set(),writes=new Set();
export const desktopBridge=()=>globalThis.window?.riekeDesktop || null;
export function registerDraftSaver(save){savers.add(save);return()=>savers.delete(save);}
export function trackWrite(operation){
  writes.add(operation);
  operation.then(()=>writes.delete(operation),()=>writes.delete(operation));
  return operation;
}
export async function flushDesktopDrafts(){
  await Promise.all([...writes]);
  await Promise.all([...savers].map(save=>save()));
}
export function installDesktopLifecycle(bridge=desktopBridge()){
  if(!bridge)return()=>{};
  return bridge.onPrepareClose(async ({requestId})=>{
    let ok=false;
    try{await flushDesktopDrafts();ok=true;}catch{}
    await bridge.acknowledgeDrafts(requestId,{ok});
  });
}
