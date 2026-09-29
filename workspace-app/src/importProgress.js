export const IMPORT_TERMINAL=new Set(['success','failed','failure','complete','completed','complete_with_warnings','duplicate','interrupted']);
const labels={queued:'Queued',checking_duplicates:'Checking file contents',freezing_baselines:'Preserving current protocol datasets',validating:'Parsing and validating',refreshing_workspace:'Refreshing the main catalog',rerunning_protocols:'Checking saved protocol queries',complete:'Import complete',completed:'Import complete',success:'Import complete',complete_with_warnings:'Imported with follow-up warnings',duplicate:'Already imported · skipped',failed:'Import failed',failure:'Import failed',interrupted:'Import interrupted'};
const finite=value=>typeof value==='number'&&Number.isFinite(value);
export const isImportPending=job=>!!job&&typeof job.status==='string'&&!IMPORT_TERMINAL.has(job.status);
export const sourceName=job=>[job?.source_filename,job?.source,job?.source_path].find(value=>typeof value==='string'&&value)?.split(/[\\/]/).pop() || 'Recording';
export function elapsedLabel(seconds){
  if(!finite(seconds))return 'Time unavailable';
  const value=Math.max(0,Math.floor(seconds));
  return value<60?`${value}s`:value<3600?`${Math.floor(value/60)}m ${value%60}s`:`${Math.floor(value/3600)}h ${Math.floor(value%3600/60)}m`;
}
export function byteLabel(bytes){
  if(!finite(bytes))return '—';
  if(bytes<1024)return `${Math.round(bytes)} B`;
  if(bytes<1024**2)return `${(bytes/1024).toFixed(1)} KB`;
  if(bytes<1024**3)return `${(bytes/1024**2).toFixed(1)} MB`;
  return `${(bytes/1024**3).toFixed(2)} GB`;
}
export function actualProgress(progress){
  if(!progress||!finite(progress.completed)||!finite(progress.total)||progress.completed<0||progress.total<=0||progress.completed>progress.total)return null;
  const unit=progress.unit || 'items';
  const counts=unit==='bytes'?`${byteLabel(progress.completed)} / ${byteLabel(progress.total)}`:`${progress.completed.toLocaleString()} / ${progress.total.toLocaleString()} ${unit}`;
  return {completed:progress.completed,total:progress.total,percent:progress.completed/progress.total*100,label:counts};
}
function age(timestamp,now){const value=Date.parse(timestamp);return Number.isFinite(value)?Math.max(0,(now-value)/1000):null;}
export function jobProgressView(job,now=Date.now(),observedAt=now){
  const pending=isImportPending(job),advance=pending?Math.max(0,(now-observedAt)/1000):0;
  const progress=job.progress || {};
  const committed=progress.commit_state==='committed'||job.catalog_committed===true;
  const interrupted=job.status==='interrupted'||typeof job.status!=='string';
  const failed=['failed','failure'].includes(job.status);
  const warning=job.status==='complete_with_warnings'||(['complete','completed','success'].includes(job.status)&&Array.isArray(job.warnings)&&job.warnings.length>0)||(failed&&committed);
  const elapsed=finite(job.elapsed_seconds)?job.elapsed_seconds+advance:age(job.started_at || job.created_at,job.finished_at?Date.parse(job.finished_at):now);
  const stageElapsed=finite(job.stage_elapsed_seconds)?job.stage_elapsed_seconds+advance:age(progress.stage_started_at,job.finished_at?Date.parse(job.finished_at):now);
  const progressAge=finite(job.progress_age_seconds)?job.progress_age_seconds+advance:age(progress.updated_at,now);
  const label=interrupted?(committed?'Imported · follow-up interrupted':'Interrupted · catalog state unconfirmed'):failed&&committed?'Imported · follow-up failed':warning?'Imported with follow-up warnings':labels[job.status] || 'Import in progress';
  return {pending,committed,interrupted,failed:failed&&!committed,warning,label,
    stage:progress.stage_label || labels[progress.stage] || labels[job.status] || 'Waiting for stage details',
    elapsed,stageElapsed,progressAge,heartbeatAge:age(job.heartbeat_at,now),
    count:actualProgress(progress),
    requiresReconciliation:job.requires_reconciliation===true||interrupted,
    staleProgress:pending&&progressAge!==null&&progressAge>=30};
}
export function selectImportJob(jobs,dismissed,now=Date.now()){
  const active=jobs.find(isImportPending);if(active)return active;
  const job=jobs[0];if(!job||dismissed.has(`${job.job_uuid}:${job.status}`))return null;
  const finishedAge=age(job.finished_at || job.created_at,now);
  return job.status==='interrupted'||['failed','failure','complete_with_warnings'].includes(job.status)||(finishedAge!==null&&finishedAge<600)?job:null;
}

export function sourceCountsLabel(job){
  const counts=job.progress?.counts || {};
  return ['cells','epochs','responses','stimuli'].filter(key=>Number.isInteger(counts[key])&&counts[key]>=0).map(key=>`${counts[key].toLocaleString()} ${key}`).join(' · ');
}
export function importMonitorDelay({loading,pending,error,watching=false}){
  if(loading)return null;
  return pending||watching?2500:error?10000:null;
}

export function shouldRefreshImportCompletion(previous,current,watchingRequest=false,recovered=false){
  return recovered||(previous!==current&&(previous!==null||(watchingRequest&&current!=='')));
}
