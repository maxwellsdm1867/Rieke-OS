// Restores a location, not scientific results or mutation authority.
export function createStartupRestore({bridge,inventory,request,navigate,onState=()=>{}}){
  let alive=true,cancelled=false,active=false,finishing=false;
  const current=()=>alive&&!cancelled;
  async function start(){
    await Promise.resolve();if(!current())return;
    try{
      const saved=await bridge.startupSession();if(!current()||!saved)return;
      active=true;
      const project=inventory.projects?.find(p=>p.path===saved.projectPath&&p.uuid===saved.projectId);
      if(!project?.available)throw Error('The last project is missing, moved or changed. Choose its current folder to continue.');
      onState({phase:'opening',project:project.name});
      const report=await request('/projects/inspect-folder',{method:'POST',body:{directory:project.path}});
      if(!current())return;
      if(report.valid!==true||report.kind!=='project'||report.project?.uuid!==project.uuid||report.project?.path!==project.path||report.desktop_compatibility?.requires_migration)throw Error('The saved project needs inspection or migration. Choose it manually.');
      const opened=await request('/projects/open-folder',{method:'POST',body:{directory:project.path}});
      // Main authenticates the child and compares the exact saved folder/UUID.
      // Cancellation after spawn closes that owned child through graceful close.
      finishing=true;const accepted=await bridge.finishStartup(opened.url);
      if(current()&&accepted?.restored){onState({phase:'complete'});navigate?.();}
    }catch(error){if(alive)onState({phase:'failed',error:error.message});}
    finally{if(alive)onState({phase:cancelled?'cancelled':'settled'});}
  }
  return {start,supersede(){cancelled=true;if(active)void bridge.cancelStartup?.();},async cancel(){cancelled=true;onState({phase:'cancelling'});await bridge.chooseStartup();},close(){alive=false;if(active&&!finishing)void bridge.cancelStartup?.();}};
}
