// Off-tree diagnostic only. Bounded passive callback logging; no new RAF loop.
export function installFrameDiagnostic(){
 const state=window.__traceFrameDiagnostic={version:'passive-frame-v1',frames:[],readiness:[],longtasks:[],visibility:[],dropped:0};
 const put=(list,row,limit=512)=>{if(list.length<limit)list.push(row);else state.dropped++;};
 const visibility=()=>({visibility:document.visibilityState,hidden:document.hidden,focus:document.hasFocus()});
 state.visibility.push({at:performance.now(),...visibility()});
 document.addEventListener('visibilitychange',()=>put(state.visibility,{at:performance.now(),...visibility()},64));
 const nativeRAF=window.requestAnimationFrame.bind(window);let serial=0;
 window.requestAnimationFrame=callback=>{const scheduled=performance.now(),id=++serial;return nativeRAF(timestamp=>{
  const action=window.__workflow?.active,at=performance.now();
  if(!action?.action_id?.startsWith('ordinary-'))return callback(timestamp);
  const row={id,action_id:action.action_id,scheduled_at:scheduled,frame_timestamp:timestamp,entered_at:at,...visibility()};
  try{return callback(timestamp);}finally{row.exited_at=performance.now();row.callback_ms=row.exited_at-at;put(state.frames,row);}
 });};
 try{new PerformanceObserver(entries=>{for(const e of entries.getEntries())put(state.longtasks,{start:e.startTime,duration:e.duration,name:e.name},128);}).observe({type:'longtask',buffered:true});state.longtask_supported=true;}catch(e){state.longtask_supported=false;state.longtask_error=String(e);}
}
// Calls the unchanged readiness function once, then records its result. These
// duplicate predicate observations are diagnostic overhead, outside its clock.
export function wrapReadinessDiagnostic(){
 const original=window.__workflowReadiness;
 window.__workflowReadiness=spec=>{
  const w=window.__workflow,a=w.active,start=performance.now();
  const result=original(spec),end=performance.now(),state=window.__traceFrameDiagnostic;
  if(!a||!spec.trace||state.readiness.length>=128)return result;
  const requests=w.requests.filter(r=>r.action_id===a.action_id&&r.url.includes('/display?'));
  const control=window.__workflowReadStream(document),lastBody=Math.max(...requests.map(r=>r.end??-Infinity));
  const draw=w.draws.find(d=>d.action_id===a.action_id&&d.at>=lastBody&&d.stream_uuid===spec.trace.stream_uuid);
  state.readiness.push({action_id:a.action_id,start,end,result,frame_timestamp:a.last_observer_frame_timestamp,correct_frames:a.diagnosticFrames??0,
   request_count:requests.length,requests:requests.map(r=>({status:r.status,body_complete:r.end!==undefined,binary_bytes:r.binary?.byteLength??0,end:r.end??null})),
   control_status:control.status,control_stream:control.stream_uuid??null,expected_stream:spec.trace.stream_uuid,matching_draw_at:draw?.at??null,
   status_overlay:!!document.querySelector('.tv-status'),canvas_width:document.querySelector('.tv-base')?.getBoundingClientRect().width??0,
   visibility:document.visibilityState,hidden:document.hidden,focus:document.hasFocus(),diagnostic_end:performance.now()});
  return result;
 };
}
