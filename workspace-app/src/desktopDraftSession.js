export function createDesktopDraftSession({bridge,projectId,snapshot,restore,isBusy,onState=()=>{}}){
  let alive=true,phase='loading',allowPreservedClose=false,resetAllowed=false,loading,saveChain=Promise.resolve();
  function publish(next,message=''){
    phase=next;if(alive)onState({projectId,phase,message,resetAllowed});
  }
  function load(){
    allowPreservedClose=false;resetAllowed=false;publish('loading');
    loading=Promise.resolve().then(()=>bridge.loadDraft(projectId)).then(saved=>{
      if(!alive)return;
      if(saved?.format==='rieke-draft-recovery'){
        resetAllowed=true;publish('recovery','The saved view could not be read. A copy will be kept if you start with a new view.');return;
      }
      if(saved){
        if(saved.format!=='rieke-renderer-draft'||saved.version!==1||saved.projectId!==projectId||!saved.value||typeof saved.value!=='object')throw new Error('Saved view identity is invalid.');
        restore(saved.value);
      }
      publish('ready');
    }).catch(()=>{if(alive)publish('recovery','The saved view could not be loaded. Retry before continuing.');});
    return loading;
  }
  load();
  return {
    flush(){
      const operation=saveChain.catch(()=>{}).then(async()=>{
      await loading;
      if(!alive)throw new Error('Draft session has closed.');
      if(isBusy())throw new Error('An import or queued write is still active.');
      if(phase==='recovery'&&allowPreservedClose)return;
      if(phase!=='ready')throw new Error('Saved view recovery requires an explicit choice.');
      await bridge.saveDraft({projectId,value:{format:'rieke-renderer-draft',version:1,projectId,value:snapshot()}});
      });
      saveChain=operation;return operation;
    },
    async fresh(){
      await loading;
      if(!resetAllowed)throw new Error('The saved view must be read before it can be reset.');
      await bridge.resetDraft(projectId);
      allowPreservedClose=false;resetAllowed=false;publish('ready');
    },
    retry:load,
    preserveForQuit(){allowPreservedClose=true;},
    close(){alive=false;},
  };
}
