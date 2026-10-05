// Transfer counters describe browser-sent bytes only; receipt establishes acceptance.
export function uploadRecording(file,onProgress,{inactivityMs=60000}={}){
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest(),body=new FormData();body.append('file',file);
    let timer,timedOut=false;
    const clear=()=>clearTimeout(timer);
    const heartbeat=()=>{clear();timer=setTimeout(()=>{timedOut=true;xhr.abort();},inactivityMs);};
    const fail=error=>{clear();reject(error);};
    xhr.open('POST','/api/imports');xhr.setRequestHeader('X-Workspace-Request','1');
    xhr.upload.onprogress=event=>{heartbeat();onProgress({phase:'uploading',loaded:event.loaded,total:event.lengthComputable?event.total:null});};
    xhr.upload.onload=()=>{heartbeat();onProgress({phase:'awaiting_job'});};
    xhr.onprogress=heartbeat;
    xhr.onerror=()=>fail(new Error('Connection lost while submitting the recording. The server may have received it. Refresh job status before submitting again.'));
    xhr.onabort=()=>fail(new Error(timedOut?`No upload or response progress for ${Math.round(inactivityMs/1000)} seconds. Server acceptance is unconfirmed; refresh job status before submitting again.`:'The transfer was interrupted. Server acceptance is unconfirmed; refresh job status before submitting again.'));
    xhr.onload=()=>{
      clear();
      let result;try{result=JSON.parse(xhr.responseText);}catch{fail(new Error('The server returned an unreadable response. Check import history before retrying.'));return;}
      if(xhr.status<200||xhr.status>=300){
        const rejected=[400,401,403,404,405,409,413,415,422,429].includes(xhr.status);
        const message=result.error || result.message || `Import request returned HTTP ${xhr.status}`;
        const error=new Error(rejected?message:`${message}. Server acceptance is unconfirmed; refresh import history before retrying.`);
        error.requestRejected=rejected;fail(error);return;
      }
      if(typeof result.job_uuid!=='string'){fail(new Error('The server did not return an import job identity. Check import history before retrying.'));return;}
      resolve(result);
    };
    heartbeat();xhr.send(body);
  });
}
