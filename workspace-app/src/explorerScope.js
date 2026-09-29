// A summary for a previous click never authorizes the currently focused epoch.
export function explorerFocusState(summary,focused,{loading=false,error=null}={}){
  if(!focused)return 'none';
  if(loading||summary?.focused_uuid!==focused)return 'pending';
  if(error)return 'error';
  if(summary.focused_in_scope===true)return 'included';
  if(summary.focused_in_scope===false)return 'excluded';
  return 'invalid';
}
