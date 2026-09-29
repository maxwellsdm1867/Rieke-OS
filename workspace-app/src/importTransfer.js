// A known HTTP rejection never queued an import. A lost response may have.
export function importFailureState(previous,error,finishedAt=new Date().toISOString()){
  const requestRejected=error.requestRejected===true || (error.status>=400&&error.status<500);
  return {...previous,phase:'error',error:error.message,requestRejected,
    finished_at:requestRejected?finishedAt:undefined};
}
export function transferElapsedSeconds(transfer,now=Date.now()){
  return Math.max(0,((transfer.finished_at?Date.parse(transfer.finished_at):now)-Date.parse(transfer.started_at))/1000);
}
