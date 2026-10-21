import {useLayoutEffect,useMemo} from 'react';
import {api as defaultApi} from '../api.js';
import {useWorkspaceRequest,useWorkspaceRequestScope} from '../workspaceRequest.js';
import {useRetainedView} from '../retainedWorkspaceViews.js';
import {CELL_WINDOW} from '../epoch-browser/cellWindows.js';
import {useCellWindows} from '../epoch-browser/useCellWindows.js';

export function useOverviewCells(data,path,revision,{enabled=true}={}){
 const request=useWorkspaceRequest(defaultApi),owner=useWorkspaceRequestScope(),view=useRetainedView();
 const scope=useMemo(()=>({data,path,revision,owner}),[data,path,revision,owner]);
 const list=useCellWindows(scope,async (after,{signal})=>{
  const next=await request(`${path}?cells_limit=${CELL_WINDOW}&cells_after=${after}`,{signal});
  if((data.query_revision!=null&&next.query_revision!==data.query_revision)||
    (data.binding?.revision_uuid!=null&&next.binding?.revision_uuid!==data.binding.revision_uuid)||
    (data.project?.project_uuid!=null&&next.project?.project_uuid!==data.project.project_uuid))throw Error('Cell membership changed. Refresh the overview.');
  return next;
 },{enabled:enabled&&view?.active!==false});
 useLayoutEffect(()=>{list.accept(data);},[scope]);
 const cells=list.cells??data?.cells;
 return {cells,window:list.window,partial:Number.isSafeInteger(data?.cells_total)&&(cells?.length??0)<data.cells_total};
}
