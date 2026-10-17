import {useRef} from 'react';
import {pendingQueueCounts} from '../incoming-workbench/workbenchAuthority.js';
// Reuse the project summary already loaded by App. Proposal history and modal
// visibility are not evidence that the cumulative pending queue is resolved.
export default function useImportReviewStatus(resource,projectId){
  const confirmed=useRef({projectId,count:null});
  if(confirmed.current.projectId!==projectId)confirmed.current={projectId,count:null};
  const rows=resource.data?.workbench_counts;
  // Count exactly what import review shows a card for: mergeable (eligible)
  // pending epochs, with a blocked Main showing no card.
  const blocked=row=>typeof row.main_blocked_reason==='string'&&!!row.main_blocked_reason;
  const complete=!!projectId&&!resource.loading&&!resource.error&&Array.isArray(rows)&&rows.every(row=>typeof row?.protocol_uuid==='string'&&(blocked(row)||pendingQueueCounts(row).epochs!==null));
  if(complete)confirmed.current={projectId,count:new Set(rows.filter(row=>!blocked(row)&&pendingQueueCounts(row).epochs>0).map(row=>row.protocol_uuid)).size};
  return {pendingProtocols:confirmed.current.count,phase:complete?'ready':resource.loading?'loading':'unavailable'};
}
export function importReviewStatusLabel(status){
  const count=status?.pendingProtocols,known=Number.isSafeInteger(count)&&count>=0;
  const pending=known&&count>0?`${count.toLocaleString()} ${count===1?'protocol has':'protocols have'} pending incoming data`:null;
  if(status?.phase==='ready'&&known)return pending||'No incoming data pending review';
  const state=status?.phase==='loading'?'Checking incoming review status':'Incoming review status unavailable';
  return pending?`${pending} (last confirmed). ${state}.`:state;
}
