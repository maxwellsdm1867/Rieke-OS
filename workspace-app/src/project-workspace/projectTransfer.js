// A transfer response must affirm verification before the UI offers its output.
export function verifiedTransferResult(result) {
  if (result?.verified !== true || typeof result.directory !== 'string' || !result.directory.trim()) {
    throw new Error('The server did not confirm a verified project folder. Check the destination before retrying.');
  }
  return result;
}

export function localProjectUrl(url, base) {
  if (typeof url !== 'string') throw new Error('The project service did not return an app URL.');
  const destination = new URL(url, base);
  if (!['http:', 'https:'].includes(destination.protocol) ||
      !['127.0.0.1', 'localhost', '[::1]'].includes(destination.hostname) ||
      destination.username || destination.password) {
    throw new Error('The project service returned an invalid local URL.');
  }
  return destination.href;
}

// A prepared copy contains a logical database backup. It must be restored to
// a new local folder instead of being opened as a live project.
export async function inspectAndOpenProject({directory,request,relocateDestination}) {
  const inspection=await request('/projects/inspect-folder',{method:'POST',body:{directory}});
  if(inspection?.kind==='project-root-suggestions')return {action:'choose-root',inspection,directory};
  if(inspection?.valid!==true)throw new Error('The project folder did not pass inspection.');
  if(inspection.desktop_compatibility?.requires_migration===true)return {action:'migrate',inspection,directory};
  if(inspection.kind==='prepared-transfer')return {action:'restore',inspection,directory};
  if(inspection.kind&&inspection.kind!=='project')throw new Error('The project service returned an unknown folder type.');
  if(relocateDestination){
    const moved=await request('/projects/relocate',{method:'POST',body:{directory,destination:relocateDestination}});
    if(typeof moved.directory!=='string'||!moved.directory.trim())throw new Error('The project service did not return the moved folder.');
    directory=moved.directory;
  }
  const response=await request('/projects/open-folder',{method:'POST',body:{directory}});
  return {action:'open',inspection,directory,url:response.url};
}

export async function runProjectTransfer({mode,directory,destination,request,signal,pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))}) {
  if (!['prepare','restore','migrate'].includes(mode)) throw new Error('Unknown project transfer action.');
  const job=await request(mode==='migrate'?'/projects/migrate-source':mode==='prepare'?'/projects/prepare-transfer':'/projects/restore-transfer',{
    method:'POST',body:{directory,destination},signal,
  });
  if(typeof job?.job_id!=='string'||!job.job_id) throw new Error('The server did not return a transfer job.');
  while(!signal?.aborted){
    const status=await request(`/projects/transfers/${encodeURIComponent(job.job_id)}`,{signal});
    if(status.state==='complete'){
      const result=verifiedTransferResult(status.result);
      if(mode==='migrate'&&(result.migrated!==true||result.source_unchanged!==true))throw new Error('The server did not confirm a verified desktop copy and unchanged source. Check the destination before retrying.');
      return result;
    }
    if(status.state==='failed')throw new Error(status.error||'The project transfer failed.');
    if(status.state!=='running')throw new Error('The server returned an unknown transfer state.');
    await pause(1000);
  }
  throw new Error('Transfer monitoring stopped. The server operation may still be running.');
}
