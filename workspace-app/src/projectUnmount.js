import {flushDesktopDrafts,beginProjectUnmount} from './desktopLifecycle.js';
export const unmountDraftKey=project=>`workspace.unmount-view.${project.uuid}:${project.path}`;
export function saveUnmountView(project,value,storage=globalThis.localStorage){
 storage.setItem(unmountDraftKey(project),JSON.stringify({version:1,path:project.path,uuid:project.uuid,value}));
}
export function readUnmountView(project,storage=globalThis.localStorage){
 const raw=storage.getItem(unmountDraftKey(project));if(!raw)return null;
 const saved=JSON.parse(raw);
 if(saved?.version!==1||saved.path!==project.path||saved.uuid!==project.uuid||!saved.value)throw new Error('The saved project view could not be restored.');
 return saved.value;
}
export const clearUnmountView=(project,storage=globalThis.localStorage)=>storage.removeItem(unmountDraftKey(project));
export async function unmountProject({project,request,busy=false,retryClosed=false,launcherUrl,saveView=()=>{}}){
 if(busy)throw new Error('Wait for the current import, accept, export or project operation to finish before unmounting.');
 const release=project.current?beginProjectUnmount(retryClosed):()=>{};
 let discardView,requested=false;
 try{
  if(project.current&&!retryClosed){await flushDesktopDrafts();discardView=await saveView();}
  requested=true;
  const result=await request('/projects/unmount',{method:'POST',body:{path:project.path,project_uuid:project.uuid}});
  if(result.state!=='unmounted')throw new Error('Unmount was not confirmed. Refresh the project list before retrying.');
  if(!result.closed)release();
  return result;
 }catch(error){
  if(project.current&&(retryClosed||(requested&&!error.status))){error.data={...error.data,close_unconfirmed:true,launcher_url:error.data?.launcher_url||launcherUrl};}
  if(error.data?.state!=='closed'&&!error.data?.close_unconfirmed){
   if(error.status>=400&&error.status<500&&error.status!==408&&typeof discardView==='function')discardView();
   release();
  }
  throw error;
 }
}
