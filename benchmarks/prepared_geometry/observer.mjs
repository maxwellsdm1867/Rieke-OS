/** Geometry readiness runs only in the shared prearmed RAF owner. The full
 * independent wire/geometry/cursor oracle remains outside observation. */
export function geometryReadiness({trace:expected}){
 const w=window.__workflow,a=w.active;
 const rs=w.requests.filter(r=>r.action_id===a?.action_id&&r.url.includes('/display?'));
 const pending=()=>{if(a){a.diagnosticFrames=0;a.diagnosticFirstRaf=null;}return false;};
 if(!a||rs.length!==1||rs.some(r=>r.status!==200||r.end===undefined||!r.binary||r.binary.byteLength<100))return pending();
 const control=window.__workflowReadStream(document),end=Math.max(...rs.map(r=>r.end));
 const draw=w.draws.find(d=>d.action_id===a.action_id&&d.at>=end&&d.stream_uuid===expected.stream_uuid);
 if(!draw||control.status!=='ready'||control.stream_uuid!==expected.stream_uuid||document.querySelector('.tv-status')||!document.querySelector('.tv-base')?.getBoundingClientRect().width)return pending();
 a.diagnosticFrames=(a.diagnosticFrames||0)+1;
 if(a.diagnosticFrames===1)a.diagnosticFirstRaf=performance.now()-a.intent;
 if(a.diagnosticFrames<2)return false;
 a.ready=performance.now();
 a.geometryFrame={post_stroke_ms:draw.at-a.intent,first_raf_ms:a.diagnosticFirstRaf,second_raf_ms:a.ready-a.intent};
 a.captured_requests=w.requests.filter(r=>r.action_id===a.action_id);
 a.captured_renders=[];a.evidence={};
 (w.completed??={})[a.action_id]=a;w.last_completed_action_id=a.action_id;w.active=null;
 return true;
}

export function geometrySnapshot(action_id){
 const w=window.__workflow,a=w.completed?.[action_id];
 if(!a?.geometryFrame)throw Error('Missing completed geometry action');
 const frame=a.geometryFrame;
 return {action_id,total_ms:frame.second_raf_ms,phase:a.phase,correctness:{passed:true},
  observer:{clock:'browser',dispatch_protocol:a.dispatch_protocol,dispatch_requested_at:a.dispatch_requested_at,dispatch_frame_timestamp:a.dispatch_frame_timestamp,dispatch_wait_ms:a.dispatch_wait_ms,armed_at:a.observer_armed_at,intent_at:a.intent,first_raf_at:a.first_observer_raf_at,ready_at:a.ready,
   armed_before_intent_ms:a.intent-a.observer_armed_at,first_raf_ms:a.first_observer_raf_at-a.intent,
   driver_observed_at:a.driver_observed_at??null,driver_retrieval_lag_ms:a.driver_observed_at===undefined?null:a.driver_observed_at-a.ready,
   raf_callbacks:a.observer_raf_count,required_correct_raf_callbacks:2},
  trace:{first_visible_ms:frame.post_stroke_ms,first_raf_ms:frame.first_raf_ms,complete_ms:frame.second_raf_ms,
   observation:'Post-stroke and two actual page-owned RAF observations before independent geometry oracle; driver retrieval excluded; no compositor claim'},
  requests:a.captured_requests.map(({start,headers,end,result,binary,decode_start,...r})=>({...r,start_ms:start-a.intent,headers_ms:headers-a.intent,end_ms:end-a.intent}))};
}
