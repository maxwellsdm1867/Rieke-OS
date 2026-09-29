import test from 'node:test';
import assert from 'node:assert/strict';
import {IMPORT_TERMINAL,actualProgress,jobProgressView,isImportPending,selectImportJob,sourceName,elapsedLabel} from './importProgress.js';
const now=Date.parse('2026-09-27T12:05:00Z');
test('determinate progress requires actual bounded completed and total counts',()=>{
  assert.equal(actualProgress({completed:7,total:10,unit:'epochs'}).percent,70);
  assert.equal(actualProgress({completed:0,total:10,unit:'epochs'}).percent,0);
  for(const progress of [{},{completed:4},{total:10},{completed:4,total:0},{completed:11,total:10},{completed:-1,total:10},{completed:'4',total:10}])assert.equal(actualProgress(progress),null);
  assert.equal(actualProgress({completed:1024,total:2048,unit:'bytes'}).label,'1.0 KB / 2.0 KB');
});
test('fresh monitor heartbeat never implies parser progress or a guessed ETA',()=>{
  const view=jobProgressView({status:'validating',elapsed_seconds:100,stage_elapsed_seconds:80,progress_age_seconds:70,heartbeat_at:'2026-09-27T12:04:59Z',progress:{stage_label:'Parsing metadata'}},now,now-1000);
  assert.equal(view.elapsed,101);assert.equal(view.stageElapsed,81);assert.equal(view.progressAge,71);assert.equal(view.heartbeatAge,1);
  assert.equal(view.staleProgress,true);assert.equal(view.pending,true);assert.equal(view.count,null);
});
test('committed warnings and uncertain interruptions are terminal and scientifically distinct',()=>{
  for(const status of ['complete_with_warnings','interrupted']){assert.equal(IMPORT_TERMINAL.has(status),true);assert.equal(isImportPending({status}),false);}
  const committed=jobProgressView({status:'failed',progress:{commit_state:'committed'}},now);
  assert.equal(committed.failed,false);assert.equal(committed.warning,true);assert.match(committed.label,/Imported/);
  const unknown=jobProgressView({status:'interrupted',catalog_committed:null,progress:{commit_state:'unknown'}},now);
  assert.equal(unknown.requiresReconciliation,true);assert.doesNotMatch(unknown.label,/Imported/);
  const failed=jobProgressView({status:'failed',warnings:[{message:'diagnostic'}],progress:{commit_state:'not_started'}},now);
  assert.equal(failed.failed,true);assert.equal(failed.label,'Import failed');
});
test('completion stops elapsed timer and progress completion is not overall completion',()=>{
  const job={status:'validating',elapsed_seconds:20,progress:{completed:100,total:100,unit:'bytes'}};
  assert.equal(jobProgressView(job,now,now-5000).pending,true);
  assert.equal(jobProgressView({...job,status:'complete'},now,now-5000).elapsed,20);
  assert.equal(elapsedLabel(72),'1m 12s');
});
test('only latest terminal job is promoted; historical failures are not resurfaced after dismissal',()=>{
  const jobs=[{job_uuid:'new',status:'complete',finished_at:'2026-09-27T12:04:00Z'},{job_uuid:'old',status:'failed'}];
  assert.equal(selectImportJob(jobs,new Set(),now).job_uuid,'new');
  assert.equal(selectImportJob(jobs,new Set(['new:complete']),now),null);
  assert.equal(selectImportJob([{job_uuid:'running',status:'validating'},...jobs],new Set(['running:validating']),now).job_uuid,'running');
});
test('malformed optional source/status fields do not crash progress presentation',()=>{
  assert.equal(sourceName({source:{path:'bad'}}),'Recording');assert.equal(sourceName({source:'/a/file.h5'}),'file.h5');
  assert.equal(sourceName({source:'C:\\data\\file.h5'}),'file.h5');
  assert.equal(isImportPending({status:[]}),false);
  assert.equal(jobProgressView({status:[],warnings:null},now).requiresReconciliation,true);
});
test('monitor polling waits for its bounded request and recovers connection errors without mutation',async()=>{
  const {importMonitorDelay}=await import('./importProgress.js');
  assert.equal(importMonitorDelay({loading:true,pending:true,error:null}),null);
  assert.equal(importMonitorDelay({loading:false,pending:true}),2500);
  assert.equal(importMonitorDelay({loading:false,error:'timed out',pending:false}),10000);
  assert.equal(importMonitorDelay({loading:false,pending:false,watching:true}),2500);
  assert.equal(importMonitorDelay({loading:false,pending:false,error:null}),null);
});
test('confirmed commit with reconciliation remains a warning, not an unknown commit',async()=>{
  const {sourceCountsLabel}=await import('./importProgress.js');
  const job={status:'complete_with_warnings',catalog_committed:true,requires_reconciliation:true,progress:{commit_state:'committed',counts:{cells:5,epochs:690}}};
  const view=jobProgressView(job,now);
  assert.equal(view.committed,true);assert.equal(view.requiresReconciliation,true);assert.equal(view.interrupted,false);assert.equal(view.failed,false);
  assert.equal(sourceCountsLabel(job),'5 cells · 690 epochs');
});
test('first recovered terminal response refreshes catalog for an outstanding submitted request',async()=>{
  const {shouldRefreshImportCompletion}=await import('./importProgress.js');
  assert.equal(shouldRefreshImportCompletion(null,'job:complete',true),true);
  assert.equal(shouldRefreshImportCompletion(null,'job:complete',false),false);
  assert.equal(shouldRefreshImportCompletion(null,'',true),false);
  assert.equal(shouldRefreshImportCompletion('job:complete','job:complete',true),false);
  assert.equal(shouldRefreshImportCompletion('','job:complete',false),true);
});
test('monitor recovery refreshes failed workspace reads even when membership is unchanged',async()=>{
  const {shouldRefreshImportCompletion}=await import('./importProgress.js');
  assert.equal(shouldRefreshImportCompletion('job:duplicate','job:duplicate',false,true),true);
  assert.equal(shouldRefreshImportCompletion('job:duplicate','job:duplicate',false,false),false);
  assert.equal(shouldRefreshImportCompletion(null,'',false,true),true);
});
