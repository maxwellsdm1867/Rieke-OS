import {productionRuntime,runtimeOption,buildWorkflowProduction,productionMiddleware,attestProductionPage} from './production-runtime.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {fixtureSource,installObserver,installTraceControlReader,installBinaryTraceOracle} from './fixture-app.mjs';
import {attachLedger} from '../navigation-probe.mjs';
import {appInventory,appLimits,appFixtureSource,runAppSample,TRAILING_MS,BACKGROUND_PATHS} from './app-suite.mjs';

export function options(argv){const value={samples:3,profile:false,module_timing:false,runtime:'production',suite:'core'};for(let i=0;i<argv.length;i+=2){if(!argv[i].startsWith('--')||argv[i+1]===undefined)throw Error('Expected --key value');value[argv[i].slice(2).replaceAll('-','_')]=argv[i+1];}for(const key of ['source_root','server_json','output'])if(!value[key])throw Error(`Missing --${key.replaceAll('_','-')}`);value.samples=Number(value.samples);if(!Number.isInteger(value.samples)||value.samples<1)throw Error('samples must be positive');value.profile=profileEnabled(value.profile);value.module_timing=moduleTimingEnabled(value.module_timing);value.runtime=runtimeOption(value.runtime,value.profile);if(!['core','app'].includes(value.suite))throw Error('suite must be core or app');return value;}


/** Profiling is an explicit diagnostic pass, never implicit benchmark work. */
export function profileEnabled(value=false){
  if(value===true||value==='true')return true;
  if(value===false||value==='false')return false;
  throw Error('profile must be true or false');
}
export function moduleTimingEnabled(value=false){
  if(value===true||value==='true')return true;
  if(value===false||value==='false')return false;
  throw Error('module-timing must be true or false');
}
export function phasePlan(config){
  const phases=[{phase:'ordinary',samples:config.samples}];
  if(profileEnabled(config.profile)){
    const samples=Number(config.profile_samples??1);
    if(!Number.isInteger(samples)||samples<1)throw Error('profile samples must be positive');
    phases.push({phase:'profile',samples});
  }
  return phases;
}

// Fixed core inventory; variants not executed are retained as explicit gaps.
export const inventory=[['view.open','cold-component'],['view.return','warm-resource'],['tree.open','main-columns'],['tree.expand','main-first-cell'],['tree.next_page','main-cell-epochs'],['tree.split_change','remove-epoch-block'],['tree.selection','incoming-select-all'],['tree.selection','incoming-deselect-all'],['predicate.search','cell-equality'],['workbench.prepare','fresh'],['workbench.prepare','receipt-replay'],['workbench.open','prepared-return'],['trace.inspect','first-owned-waveform'],['trace.inspect','frozen-workbench-300k'],['trace.inspect','frozen-workbench-1m']];
const limits=['Owned shell mounts production components; full App navigation/session restoration unmeasured.','DOM/RAF and canvas calls are observations, not compositor presentation.','Development Vite/React runtime; not installed desktop performance.','Split add/reorder/recorded-field variants, hierarchy, queued/range selections, predicate selectivity/continuation, preparation invalidation/new-operation reuse, and trace supersession/scroll remain unmeasured.'];

/** Browser-side gate uses only independently specified fixture expectations and
 * rendered state. Network payload validation adds identity/count evidence, never
 * replaces the visible readiness boundary. */
export function readiness(spec){
  const observedAt=performance.now();
  const w=window.__workflow, a=w.active;
  const pending=()=>{a.frames=0;a.signature=null;return false;};
  const visible=el=>!!el&&el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0&&getComputedStyle(el).visibility!=='hidden';
  const requests=w.requests.filter(r=>r.action_id===a.action_id);
  const aborted=r=>spec.allowAborted&&r.status===undefined&&/AbortError/.test(r.error||'');
  if(requests.some(r=>!aborted(r)&&(r.error||r.status>=400)))throw Error('Action API request failed: '+JSON.stringify(requests.filter(r=>!aborted(r)&&(r.error||r.status>=400)).map(r=>({url:r.url,status:r.status,error:r.error}))));
  // A combined response is transport evidence for the same first page, not a
  // synthetic /epochs request. Keep this helper inside the serialized browser gate.
  const preparedPage=saved=>{
    const object=value=>!!value&&typeof value==='object'&&!Array.isArray(value);
    const canonical=value=>JSON.stringify(value,(_key,item)=>object(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
    for(const record of [...requests].reverse()){
      const result=record.result;
      if(result?.query_revision===saved.candidate_scope_revision&&Array.isArray(result?.epochs))return result;
      const b=result?.bootstrap,c=b?.context,p=b?.page,definition=saved.context?.protocol?.definition;
      if(!b)continue;
      const root=saved.root,protocol=definition?.protocol_uuid,project=definition?.project_uuid;
      const endpoint=typeof record.url==='string'?record.url.split('?')[0]:null;
      if(!root||!protocol||!project||root!==`/protocols/${protocol}/workbench/candidates/${saved.candidate_revision_uuid}`||
        ![`${root}/context`,`/protocols/${protocol}/workbench/prepare`].map(url=>'/api'+url).includes(endpoint)||
        !Number.isInteger(record.status)||record.status<200||record.status>=300||
        result.candidate_revision_uuid!==saved.candidate_revision_uuid||result.candidate_scope_revision!==saved.candidate_scope_revision||
        b.contract_version!==1||b.kind!=='workbench_initial_page'||b.root!==root||
        b.protocol_uuid!==protocol||b.project_uuid!==project||b.candidate_revision_uuid!==saved.candidate_revision_uuid||
        typeof b.actor!=='string'||!b.actor||saved.actor!==undefined&&b.actor!==saved.actor||
        c?.candidate_revision_uuid!==saved.candidate_revision_uuid||c?.candidate_scope_revision!==saved.candidate_scope_revision||
        c.query_revision!==saved.candidate_scope_revision||c.counts?.incoming_epochs!==spec.preparedUuids.length||c.publication_blocked!==false||
        c.protocol?.definition?.protocol_uuid!==protocol||
        c.protocol?.definition?.project_uuid!==project||c.protocol?.query_revision!==saved.candidate_scope_revision||
        !Number.isSafeInteger(c.expected_binding_version)||c.expected_binding_version<0||
        c.expected_binding_version!==saved.context.expected_binding_version||c.protocol.expected_binding_version!==c.expected_binding_version||
        !object(c.generation)||p?.candidate_scope_revision!==saved.candidate_scope_revision||p.query_revision!==saved.candidate_scope_revision||
        p.expected_binding_version!==c.expected_binding_version||canonical(p.generation)!==canonical(c.generation)||
        !Number.isSafeInteger(p.total)||p.total<0||p.offset!==0||p.limit!==60||
        !Array.isArray(p.epochs)||p.epochs.length!==Math.min(60,p.total)||!Array.isArray(p.cells)||
        b.request?.offset!==0||b.request?.limit!==60||b.request?.include_cells!==true||
        !object(b.request.filters)||Object.keys(b.request.filters).length)continue;
      const cells=new Map();let valid=true;
      for(const cell of p.cells){if(typeof cell?.cell_uuid!=='string'||!cell.cell_uuid||cells.has(cell.cell_uuid)||!Number.isSafeInteger(cell.epochs)||cell.epochs<0){valid=false;break;}cells.set(cell.cell_uuid,cell.epochs);}
      const ids=new Set(),shown=new Map();
      for(const row of p.epochs){if(typeof row?.epoch_uuid!=='string'||!row.epoch_uuid||ids.has(row.epoch_uuid)||!cells.has(row.cell_uuid)){valid=false;break;}ids.add(row.epoch_uuid);shown.set(row.cell_uuid,(shown.get(row.cell_uuid)||0)+1);if(shown.get(row.cell_uuid)>cells.get(row.cell_uuid))valid=false;}
      if(valid&&[...cells.values()].reduce((sum,count)=>sum+count,0)===p.total)return p;
    }
    return null;
  };
  const elements=[...document.querySelectorAll(spec.selector)];
  const current=elements.filter(visible).filter(el=>!spec.text||el.textContent.includes(spec.text));
  if(!current.length)return pending();
  if(spec.text&&!current.some(el=>el.textContent.includes(spec.text)))return pending();
  if(spec.totalText&&!document.body.textContent.includes(spec.totalText))return pending();
  if(spec.splitLabels){const labels=[...document.querySelectorAll('.tb-steps [aria-label^="Reorder "]')].map(el=>el.getAttribute('aria-label'));if(JSON.stringify(labels)!==JSON.stringify(spec.splitLabels))return pending();}
  if(spec.enabled&&!current.some(el=>!el.disabled))return pending();
  if(document.querySelector('.column-tree[aria-busy="true"]'))return pending();
  let evidence={selector:spec.selector,text:spec.text||null};
  if(spec.membership){if(!document.querySelector('.inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const r=[...w.requests].reverse().find(r=>r.result?.total===spec.membership&&Array.isArray(r.result?.epochs)&&Array.isArray(r.result?.cells));if(!r)return pending();evidence.total=spec.membership;evidence.query_revision=r.result.query_revision;}
  if(spec.searchUuids){if(!document.querySelector('.matching-epochs .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const r=[...requests].reverse().find(r=>r.url.includes('/explore/epochs')&&Array.isArray(r.result?.epochs));if(!r)return pending();const got=r.result.epochs.map(e=>e.epoch_uuid);if(JSON.stringify(got)!==JSON.stringify(spec.searchUuids.slice(0,got.length))||r.result.total!==spec.searchUuids.length||got.length!==Math.min(60,spec.searchUuids.length))return pending();evidence.result_uuids=got;evidence.total=r.result.total;}
  if(spec.savedPrepared){const saved=w.incomingSession?.prepared;for(const key of ['candidate_revision_uuid','queue_revision','candidate_scope_revision'])if(saved?.[key]!==spec.savedPrepared[key])return pending();if(!document.querySelector('.incoming-browser .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const p=preparedPage(saved);if(!p||p.total!==spec.preparedUuids.length||JSON.stringify(p.epochs.map(e=>e.epoch_uuid))!==JSON.stringify(spec.preparedUuids.slice(0,60)))return pending();evidence.prepared=spec.savedPrepared;}
  if(spec.selected){const session=w.incomingSession;const draft=session?.drafts?.[session?.prepared?.candidate_revision_uuid];if(JSON.stringify(draft?.selected)!==JSON.stringify(spec.selected))return pending();evidence.selected_uuids=draft.selected;}
  if(spec.pressed){const el=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')===spec.pressed.label);if(!el||el.disabled||el.getAttribute('aria-pressed')!==String(spec.pressed.value))return pending();evidence.pressed=spec.pressed;}
  if(spec.requestDone){const r=requests.find(r=>r.method===spec.requestDone.method&&r.url.split('?')[0].endsWith(spec.requestDone.path)&&r.status>=200&&r.status<300&&r.end!==undefined);if(!r)return pending();evidence.request_done={method:r.method,path:spec.requestDone.path,status:r.status};}
  if(spec.focusedLabel){const el=document.querySelector('[aria-current="true"]');if(!visible(el)||el.getAttribute('aria-label')!==spec.focusedLabel||document.body.textContent.includes('Loading epoch…'))return pending();evidence.focused=spec.focusedLabel;}
  if(spec.bodyText){if(!document.body.textContent.includes(spec.bodyText))return pending();evidence.body_text=spec.bodyText;}
  if(spec.enabledButton){const el=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')===spec.enabledButton||b.textContent.trim()===spec.enabledButton);if(!visible(el)||el.disabled)return pending();evidence.enabled_button=spec.enabledButton;}
  if(spec.settledPath){const got=[...document.querySelectorAll(spec.settledPath.selector)].filter(visible).map(el=>el.getAttribute('data-epoch-uuid'));evidence.path_kept=JSON.stringify(got)===JSON.stringify(spec.settledPath.uuids);evidence.terminal_count=got.length;}
  if(spec.uuids){const got=current.map(el=>el.getAttribute('data-epoch-uuid'));if(JSON.stringify(got)!==JSON.stringify(spec.uuids))return pending();evidence.uuids=got;}
  if(spec.trace){
    const expected=spec.trace;a.trace_expected={...expected,end:expected.start+expected.count,...(spec.traceRoot?{root:spec.traceRoot,candidate_scope_revision:spec.traceRevision}:{})};
    for(const r of requests)if(r.binary&&!r.result){if(r.content_type?.split(';')[0]!=='application/vnd.disco.trace-f64le.v1')throw Error('Unexpected binary trace media type');r.result=window.__workflowDecodeBinaryTrace(r.binary);}
    const traceRequests=requests.filter(r=>r.result?.epoch_uuid===expected.epoch_uuid&&r.result?.stream_uuid===expected.stream_uuid&&(Array.isArray(r.result?.values)||Object.hasOwn(r.result??{},'windows')));
    const chunks=traceRequests.flatMap(r=>{
      const d=r.result;
      if(!Object.hasOwn(d,'windows'))return [r];
      if(!Array.isArray(d.windows)||d.windows.length<2||d.windows.length>10||!Number.isSafeInteger(d.count)||d.count<1||d.count>1000000||d.count!==d.windows.reduce((n,v)=>n+v.count,0)||d.start!==d.windows[0]?.start)throw Error('Trace batch envelope mismatch');
      if(spec.traceRevision&&d.candidate_scope_revision!==spec.traceRevision)throw Error('Trace batch scope mismatch');
      for(const child of d.windows)for(const key of ['epoch_uuid','stream_uuid','source_sha256','sample_rate','units','total_samples','decimated'])if(child[key]!==d[key])throw Error('Trace batch header mismatch');
      return d.windows.map(result=>({...r,result}));
    });
    if(!chunks.length)return pending();
    let cursor=expected.start,lastEnd=0;
    for(const r of chunks){
      const d=r.result;
      for(const key of ['sample_rate','units','source_sha256'])if(expected[key]!==undefined&&d[key]!==expected[key])throw Error('Trace mismatch '+key);
      if(spec.traceRoot){
        const url=new URL(r.url,'http://fixture');
        if(url.pathname!=='/api'+spec.traceRoot+'/epochs/'+expected.epoch_uuid+'/trace'||url.searchParams.get('candidate_scope_revision')!==spec.traceRevision)throw Error('Trace scope mismatch');
      }
      for(const key of ['start','count'])if(!Number.isSafeInteger(d[key]))throw Error('Trace mismatch '+key);
      if(d.count<1||d.count>100000||d.start!==cursor||cursor+d.count>expected.start+expected.count)throw Error('Trace chunk gap, overlap or bounds mismatch');
      if(d.values.length!==d.count)throw Error('Incomplete trace values');
      if(expected.ramp&&(d.total_samples!==expected.count||d.decimated!==false))throw Error('Trace total or decimation mismatch');
      if(expected.ramp&&d.values.some((v,i)=>v!==d.start+i))throw Error('Incorrect waveform sample');
      if(cursor===expected.start&&expected.values_first!==undefined&&d.values[0]!==expected.values_first)throw Error('Incorrect first waveform sample');
      cursor+=d.count;lastEnd=Math.max(lastEnd,r.end);
      if(cursor===expected.start+expected.count&&expected.values_last!==undefined&&d.values.at(-1)!==expected.values_last)throw Error('Incorrect last waveform sample');
    }
    if(cursor!==expected.start+expected.count)return pending();
    const control=window.__workflowReadStream(document);a.trace_control=control;
    if(control.status==='incompatible')throw Error('Harness incompatible with Response stream: '+JSON.stringify(control));
    if(control.status!=='ready'||control.stream_uuid!==expected.stream_uuid)return pending();
    if(!w.draws.some(v=>v.action_id===a.action_id&&v.at>=lastEnd&&v.stream_uuid===expected.stream_uuid))return pending();
    if(document.querySelector('.tv-status'))return pending();
    a.first_trace_at??=w.draws.find(v=>v.action_id===a.action_id&&v.at>=lastEnd&&v.stream_uuid===expected.stream_uuid).at;
    a.trace_observation_at=observedAt;
    evidence.trace={epoch_uuid:expected.epoch_uuid,stream_uuid:expected.stream_uuid,start:expected.start,count:expected.count,sample_rate:chunks[0].result.sample_rate,units:chunks[0].result.units,values_count:cursor-expected.start,chunks:chunks.length,requests:traceRequests.length,...(spec.traceRoot?{root:spec.traceRoot,candidate_scope_revision:spec.traceRevision}:{}),...(expected.source_sha256?{source_sha256:expected.source_sha256}:{})};
  }
  if(spec.requestPath){const r=[...requests].reverse().find(r=>r.url.includes(spec.requestPath)&&r.result);if(!r)return pending();evidence.response=r.result;if(spec.prepared){if(typeof spec.expectedReused!=='boolean'||r.result.reused!==spec.expectedReused)throw Error('Preparation reuse classification mismatch');if(spec.expectedCandidate&&r.result.candidate_revision_uuid!==spec.expectedCandidate)throw Error('Preparation replay changed candidate');if(spec.expectedOperation&&r.result.operation_uuid!==spec.expectedOperation)throw Error('Preparation replay changed operation');if(spec.expectedPrepareStatus!==undefined&&r.status!==spec.expectedPrepareStatus)throw Error('Preparation HTTP status mismatch');const session=w.incomingSession,prepared=session?.prepared;if(!prepared?.candidate_revision_uuid)return pending();if(prepared.candidate_revision_uuid!==r.result.candidate_revision_uuid||prepared.queue_revision!==r.result.queue_revision||prepared.candidate_scope_revision!==r.result.candidate_scope_revision)return pending();if(prepared.context?.counts?.incoming_epochs!==spec.preparedUuids.length||prepared.context?.publication_blocked)return pending();const draft=session.drafts?.[prepared.candidate_revision_uuid];if(draft?.selected?.length||draft?.receipt)throw Error('Preparation silently selected or merged');const page=preparedPage(prepared);if(!page||page.total!==spec.preparedUuids.length||page.epochs.length!==Math.min(60,spec.preparedUuids.length))return pending();if(JSON.stringify(page.epochs.map(e=>e.epoch_uuid))!==JSON.stringify(spec.preparedUuids.slice(0,page.epochs.length)))throw Error('Wrong prepared membership');if(!document.querySelector('.incoming-browser .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();evidence.prepared={candidate_revision_uuid:prepared.candidate_revision_uuid,queue_revision:prepared.queue_revision,candidate_scope_revision:prepared.candidate_scope_revision,total:page.total,epoch_uuids:page.epochs.map(e=>e.epoch_uuid),reused:r.result.reused,operation_uuid:r.result.operation_uuid,http_status:r.status};}if(spec.expectedCount!==undefined){const count=r.result.matched_count??r.result.count??r.result.total_epochs??r.result.pending_epoch_count;if(count!==spec.expectedCount)throw Error('Incorrect result count '+count+' expected '+spec.expectedCount);}}
  // Two successive RAF observations of the same correct result, in page clock.
  a.first_correct_observation_at??=observedAt;
  const signature=JSON.stringify(evidence);if(a.signature!==signature){a.signature=signature;a.frames=0;}a.frames++;
  if(a.frames<2)return false;
  a.ready=a.trace_observation_at??performance.now();a.correctness_validation_finished_at=performance.now();a.evidence=evidence;
  // Close capture in the same browser task that declares readiness. Delayed
  // effects can no longer acquire this completed action's correlation header.
  a.captured_requests=requests.filter(r=>r.start<=a.ready);
  a.captured_renders=(w.renders||[]).filter(r=>r.action_id===a.action_id);
  (w.completed??={})[a.action_id]=a;w.last_completed_action_id=a.action_id;w.active=null;
  return true;
}

/** Dispatch a synthetic click at a real frame boundary, then observe only later
 * frames. The clock starts immediately before el.click(), including its complete
 * synchronous handler. Predispatch waiting is bounded and recorded separately. */
export function armAction(el,{action_id,phase,spec,timeoutMs}){
  return new Promise((resolve,reject)=>{
    const w=window.__workflow,requestedAt=performance.now(),dispatchTimeoutMs=15000;
    if(!Number.isFinite(timeoutMs)||timeoutMs<=0)return reject(Error('Invalid action timeout'));
    if(w.active||w.pending_action)return reject(Error('Previous action still active or pending'));
    const reservation={action_id};w.pending_action=reservation;
    let launchFrame,frame,dispatchTimer,timer,closed=false,a;
    const close=()=>{
      closed=true;cancelAnimationFrame(launchFrame);cancelAnimationFrame(frame);
      clearTimeout(dispatchTimer);clearTimeout(timer);
      if(w.pending_action===reservation)delete w.pending_action;
    };
    const fail=error=>{close();(w.observation_errors??={})[action_id]=String(error);reject(error);};
    const poll=timestamp=>{
      if(closed)return;
      if(w.active!==a)return fail(Error('Action ownership changed before readiness'));
      if(performance.now()-a.intent>timeoutMs)return fail(Error('Action readiness timed out'));
      // A dispatch frame can never count as a correct observation, even if a
      // scheduler delivers another callback with that same frame timestamp.
      if(timestamp<=a.dispatch_frame_timestamp||timestamp===a.last_observer_frame_timestamp){frame=requestAnimationFrame(poll);return;}
      a.last_observer_frame_timestamp=timestamp;
      a.first_observer_raf_at??=performance.now();a.observer_raf_count++;
      try{if(window.__workflowReadiness(spec)){close();return;}}
      catch(error){fail(error);return;}
      frame=requestAnimationFrame(poll);
    };
    const dispatch=timestamp=>{
      if(closed)return;
      if(w.pending_action!==reservation||w.active)return fail(Error('Action ownership changed before dispatch'));
      if(!el.isConnected)return fail(Error('Action target detached'));
      if(performance.now()-requestedAt>=dispatchTimeoutMs)return fail(Error('Action dispatch timed out'));
      if(el.disabled){launchFrame=requestAnimationFrame(dispatch);return;}
      a={action_id,phase,frames:0,observer_raf_count:0,dispatch_protocol:'raf-aligned-click-v1',dispatch_requested_at:requestedAt,dispatch_frame_timestamp:timestamp};
      frame=requestAnimationFrame(poll);
      a.observer_armed_at=performance.now();w.active=a;
      clearTimeout(dispatchTimer);delete w.pending_action;
      a.intent=performance.now();a.dispatch_wait_ms=a.intent-requestedAt;
      timer=setTimeout(()=>fail(Error('Action readiness timed out')),timeoutMs);
      try{if(spec?.gesture==='hold'){a.gesture='hold';a.hold_ms=spec.holdMs;el.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',isPrimary:true,button:0,buttons:1}));}else el.click();resolve();}catch(error){fail(error);}
    };
    dispatchTimer=setTimeout(()=>fail(Error('Action dispatch timed out')),dispatchTimeoutMs);
    launchFrame=requestAnimationFrame(dispatch);
  });
}

export function observationFinished(action_id){
  const w=window.__workflow,error=w.observation_errors?.[action_id];
  if(error)throw Error(error);
  const a=w.completed?.[action_id];
  if(!a)return false;
  a.driver_observed_at??=performance.now();
  return true;
}

export function snapshotAction(action_id){const w=window.__workflow,a=w.completed?.[action_id];if(!a)throw Error('Missing completed action');const requests=a.captured_requests;return {action_id:a.action_id,total_ms:a.ready-a.intent,phase:a.phase,...(a.observer_armed_at!==undefined?{observer:{clock:'browser',dispatch_protocol:a.dispatch_protocol,dispatch_requested_at:a.dispatch_requested_at,dispatch_frame_timestamp:a.dispatch_frame_timestamp,dispatch_wait_ms:a.dispatch_wait_ms,armed_at:a.observer_armed_at,intent_at:a.intent,first_raf_at:a.first_observer_raf_at,first_correct_at:a.first_correct_observation_at,ready_at:a.ready,driver_observed_at:a.driver_observed_at??null,armed_before_intent_ms:a.intent-a.observer_armed_at,first_raf_ms:a.first_observer_raf_at-a.intent,first_correct_ms:a.first_correct_observation_at-a.intent,driver_retrieval_lag_ms:a.driver_observed_at===undefined?null:a.driver_observed_at-a.ready,raf_callbacks:a.observer_raf_count,required_correct_raf_callbacks:2}}:{}),correctness:{passed:true,...a.evidence},...(a.first_trace_at?{trace:{expected:a.trace_expected,first:{...a.evidence.trace,end:a.evidence.trace.start+a.evidence.trace.count},complete:{...a.evidence.trace,end:a.evidence.trace.start+a.evidence.trace.count},first_visible_ms:a.first_trace_at-a.intent,complete_ms:a.ready-a.intent,observation:'post-stroke timestamp plus second stable DOM/RAF observation captured before that observation correctness work; first-frame oracle work can delay second RAF; no compositor claim',correctness_validation_after_observation_ms:Math.max(0,a.correctness_validation_finished_at-a.ready)}}:{}),requests:requests.map(({start,headers,end,result,binary,decode_start,...r})=>({...r,start_ms:start-a.intent,headers_ms:headers===undefined?null:headers-a.intent,end_ms:end===undefined?null:end-a.intent})),frontend_spans:requests.filter(r=>r.start<a.ready).flatMap((r,i)=>{const parent={id:'request-'+i,module:'api-transport',name:'request-through-consumption',request_id:r.request_id,start_ms:r.start-a.intent,end_ms:Math.min(r.end??a.ready,a.ready)-a.intent,clipped_at_ready:r.end===undefined||r.end>a.ready,clock:'browser',inclusive:true,interpretation:'HTTP wait plus response consumption; backend work is nested, not exclusive CPU'};return [parent,...(r.decode_start!==undefined&&r.decode_start<a.ready?[{id:'body-'+i,parent_id:parent.id,module:'api-response-consumption',name:'response-json-consumption',request_id:r.request_id,start_ms:r.decode_start-a.intent,end_ms:parent.end_ms,clipped_at_ready:parent.clipped_at_ready,clock:'browser',inclusive:true,interpretation:'Includes body wait and JSON decode, not exclusive CPU'}]:[])];}),react_renders:a.captured_renders,cache_classification:requests.length?'requests-observed':'no-request-observed',...(a.gesture?{gesture:a.gesture,hold_ms:a.hold_ms}:{})};}

export function assertFinalizedRequests(sample){
  const seen=new Set();
  for(const row of sample.requests){
    if(!row.request_id||seen.has(row.request_id)||row.action_id!==sample.action_id)throw Error('Missing or duplicate request correlation');
    seen.add(row.request_id);
    if(row.error||!Number.isInteger(row.status)||row.status<200||row.status>=300||row.end_ms===null)throw Error('Failed or incomplete captured request');
  }
}

export async function resetPreparation(meta,{timeoutMs=900000}={}){
  if(meta.fixture!=='workflow-owned-v4')throw Error('Owned preparation reset contract unavailable');
  const start=performance.now();let attempts=0;
  while(performance.now()-start<timeoutMs){
    attempts++;
    const response=await fetch(`http://127.0.0.1:${meta.port}/__benchmark__/reset-preparation`,{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Request':'1'},body:'{}',signal:AbortSignal.timeout(Math.ceil(timeoutMs-(performance.now()-start)))});
    const body=await response.text();
    // A browser abort may finish locally before Flask finishes its read. Only
    // this explicit busy refusal is retryable; changed authority fails closed.
    if(response.status===409&&body.includes('Other owned fixture requests are still active')){await new Promise(resolve=>setTimeout(resolve,500));continue;}
    if(!response.ok)throw Error(`Owned preparation reset failed: ${response.status} ${body}`);
    const receipt=JSON.parse(body);
    if(receipt.reset!==true||receipt.ready!==true||receipt.epochs!==meta.epochs||receipt.main_count!==meta.main_count||receipt.incoming_count!==meta.incoming_count)throw Error('Owned preparation reset did not attest readiness');
    return {...receipt,attempts,setup_wait_ms:performance.now()-start,included_in_headline:false};
  }
  throw Error('Owned preparation reset timed out waiting for idle fixture');
}

export async function run(config){
  const phases=phasePlan(config);
  const root=path.resolve(config.source_root), workspace=path.join(root,'workspace-app'), output=path.resolve(config.output);
  const runtime=runtimeOption(config.runtime,profileEnabled(config.profile));
  await fs.mkdir(output,{recursive:true});const meta=JSON.parse(await fs.readFile(config.server_json,'utf8'));
  if(!Number.isInteger(meta.port)||meta.port<1||meta.port>65535)throw Error('Invalid owned backend port');
  const receipt={runtime,diagnostic_only:runtime==='development',module_timing:moduleTimingEnabled(config.module_timing),profile:profileEnabled(config.profile),setup_receipts:[],format:'disco-workflow-browser-v1',status:'incomplete',epochs:meta.epochs,suite:config.suite||'core',actions:(config.suite==='app'?appInventory:inventory).map(([id,variant])=>({id,variant,samples:[]})),failures:[],gaps:[],limitations:config.suite==='app'?appLimits.slice():limits.slice(0,3),unmeasured_variants:config.suite==='app'?[]:[limits[3]],cleanup:{},observation:'page-prearmed click handler capture to correct DOM on two distinct RAF callbacks; driver retrieval excluded; no compositor claim'};
  if(config.suite!=='app')receipt.limitations[2]=runtime==='production'?'Production React owned shell via Vite API proxy; not installed desktop performance.':'Development Vite/React diagnostic only; cannot qualify the production workflow gate.';
  let server,browser,context;
  const require=createRequire(path.join(workspace,'package.json'));
  let chromium;try{({chromium}=require('playwright'));}catch{({chromium}=createRequire(path.join(root,'desktop/package.json'))('playwright'));}
  try{
    const {createServer}=await import(pathToFileURL(path.join(workspace,'src/test-support/isolatedVite.js')));
    const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
    const entry=path.join(workspace,'__workflow_owned__.jsx');
    const entrySource=config.suite==='app'?appFixtureSource():fixtureSource(meta);
    const production=runtime==='production'?await buildWorkflowProduction(root,meta,output,entrySource):null;
    receipt.production_build=production;receipt.production_attestations=[];
    const serveProduction=production?await productionMiddleware(output,production):null;
    server=await createServer({root:workspace,configFile:false,logLevel:'error',...(production?{optimizeDeps:{noDiscovery:true,include:[]}}:{}),plugins:[react(),{name:'owned-workflow-fixture',resolveId(id){if(id==='/__workflow_owned__.jsx')return entry;},load(id){if(id===entry)return entrySource;},configureServer(s){s.middlewares.use(serveProduction||((req,res,next)=>{if(req.url!=='/__workflow__')return next();res.setHeader('Content-Type','text/html');res.end('<div id="root"></div><script type="module" src="/__workflow_owned__.jsx"></script>');}));}}],server:{host:'127.0.0.1',port:0,hmr:false,proxy:{'/api':{target:`http://127.0.0.1:${meta.port}`,changeOrigin:true,configure(proxy){proxy.on('proxyReq',req=>req.removeHeader('origin'));}}}}});
    await server.listen();receipt.frontend_port=server.httpServer.address().port;
    browser=await chromium.launch({headless:true,...((config.browser_executable||process.env.WORKFLOW_BROWSER_EXECUTABLE)?{executablePath:config.browser_executable||process.env.WORKFLOW_BROWSER_EXECUTABLE}:{}),args:['--no-first-run','--no-default-browser-check']});
    receipt.environment={click_dispatch_protocol:'raf-aligned-click-v1',node:process.version,browser:browser.version(),viewport:{width:1500,height:1100},device_scale_factor:1,headless:true,runtime:production?productionRuntime:'vite-react-development'};
    for(const {phase,samples:phaseSamples} of phases)for(let sample=0;sample<phaseSamples;sample++){
      context=await browser.newContext({viewport:{width:1500,height:1100}});const page=await context.newPage();await page.addInitScript(installTraceControlReader,{streams:meta.trace_streams});await page.addInitScript(installBinaryTraceOracle);await page.addInitScript(installObserver,{phase,module_timing:receipt.module_timing});const ledger=attachLedger(page,'workflow');
      page.on('pageerror',e=>receipt.failures.push({phase,sample,error:e.message}));
      await page.goto(`http://127.0.0.1:${receipt.frontend_port}/__workflow__`);
      if(production)receipt.production_attestations.push({phase,sample,stage:'loaded',...await attestProductionPage(page,production,`http://127.0.0.1:${receipt.frontend_port}`)});
      await page.evaluate(`window.__workflowReadiness = (${readiness.toString()})`);
      if(config.suite!=='app')await page.getByRole('button',{name:'Benchmark Main',exact:true}).waitFor();
      const button=name=>page.getByRole('button',{name,exact:true});
      async function measure(id,variant,locator,spec){
        const action_id=`${phase}-${sample}-${id}-${variant}`;
        // The full App cancels superseded reads; record them, never count them as failures.
        if(config.suite==='app')spec={...spec,allowAborted:true};
        await locator.waitFor({state:'visible',timeout:15000});
        const timeoutMs=Number(config.action_timeout_ms||(phase==='profile'?900000:600000));
        try{
          await locator.evaluate(armAction,{action_id,phase,spec,timeoutMs});
          await page.waitForFunction(observationFinished,action_id,{polling:'raf',timeout:timeoutMs+15000});
          const observed=await page.evaluate(snapshotAction,action_id);
          await fs.appendFile(path.join(output,'action-observations.jsonl'),JSON.stringify({id,variant,status:'observed',...observed})+'\n');
          console.log(JSON.stringify({action:id,variant,phase,total_ms:observed.total_ms,status:'observed'}));
          const tailStarted=performance.now(),tailTimeout=Number(config.tail_timeout_ms||180000);
          await page.waitForFunction(action_id=>window.__workflow.completed[action_id].captured_requests.every(r=>r.end!==undefined||r.error),action_id,{timeout:tailTimeout});
          const result=await page.evaluate(snapshotAction,action_id);
          if(config.suite==='app'){const cancelled=r=>r.status===undefined&&/AbortError/.test(r.error||'');result.aborted=result.requests.filter(cancelled);result.requests=result.requests.filter(r=>!cancelled(r));}
          result.tail={wait_ms:performance.now()-tailStarted,timeout_ms:tailTimeout,included_in_headline:false};
          assertFinalizedRequests(result);
          if(config.suite==='app'){
            // Fixed quiet window after readiness; no setup runs meanwhile.
            await page.waitForTimeout(TRAILING_MS);
            result.trailing={window_ms:TRAILING_MS,background_paths:BACKGROUND_PATHS,requests:await page.evaluate(({action_id,windowMs})=>{const w=window.__workflow,a=w.completed[action_id];return w.requests.filter(r=>r.after_action_id===action_id&&r.start<=a.ready+windowMs).map(({result,binary,decode_start,headers,end,start,...r})=>({...r,start_ms:start-a.intent,end_ms:end===undefined?null:end-a.intent}));},{action_id,windowMs:TRAILING_MS})};
          }
          await fs.appendFile(path.join(output,'action-samples.jsonl'),JSON.stringify({id,variant,...result})+'\n');
          // React actualDuration is CPU accounting, deliberately not a wall span.
          receipt.actions.find(a=>a.id===id&&a.variant===variant).samples.push(result);console.log(JSON.stringify({action:id,variant,phase,total_ms:result.total_ms,status:'finalized'}));return result;
        }catch(error){receipt.failures.push({action_id,error:String(error)});await fs.appendFile(path.join(output,'action-failures.jsonl'),JSON.stringify({id,variant,action_id,phase,status:'failed',error:String(error)})+'\n');console.log(JSON.stringify({action:id,variant,phase,status:'failed',error:String(error)}));await fs.writeFile(path.join(output,`${action_id}.txt`),await page.locator('body').innerText());await page.screenshot({path:path.join(output,`${action_id}.png`)});await fs.writeFile(path.join(output,`${action_id}-requests.json`),JSON.stringify(await page.evaluate(()=>window.__workflow.requests.map(({result,binary,...row})=>row)),null,2));await page.evaluate(()=>{window.__workflow.active=null;});throw error;}
      }
      try{
        if(config.suite==='app'){await runAppSample({page,measure,meta,config,sample});if(production)receipt.production_attestations.push({phase,sample,stage:'completed',...await attestProductionPage(page,production,`http://127.0.0.1:${receipt.frontend_port}`)});continue;}
        const edit={selector:'button',text:'Edit Tree',enabled:true,membership:meta.main_count};
        await measure('view.open','cold-component',button('Benchmark Main'),edit);
        await button('Benchmark Away').click();await measure('view.return','warm-resource',button('Benchmark Main'),edit);
        await measure('tree.open','main-columns',button('Edit Tree'),{selector:'.tp-column .tp-branch',enabled:true});
        // Removal must preserve all fixture membership, then navigate date/cell.
        await measure('tree.split_change','remove-epoch-block',button('Remove Epoch block grouping'),{selector:'.tb-steps',splitLabels:['Reorder Recording date, level 1','Reorder Cell, level 2'],totalText:`Current view · ${meta.main_count.toLocaleString('en-US')} epochs`});
        const branches=page.locator('.tp-column .tp-branch');await branches.first().click();
        await page.locator('.tp-column').nth(1).locator('.tp-branch').first().waitFor();
        const expected=meta.first_cell_epochs;
        if(!Array.isArray(expected))throw Error('Independent first_cell_epochs oracle missing');
        await measure('tree.expand','main-first-cell',page.locator('.tp-column').nth(1).locator('.tp-branch').first(),{selector:'.tp-terminal [data-epoch-uuid]',uuids:expected.slice(0,60)});
        if(expected.length>60)await measure('tree.next_page','main-cell-epochs',button('Next page in column 3'),{selector:'.tp-terminal [data-epoch-uuid]',uuids:expected.slice(60,120)});else receipt.gaps.push('tree.next_page fixture too small');
        if(expected.length>60)await button('Previous page in column 3').click();
        await page.locator(`[data-epoch-uuid="${meta.first_epoch}"]`).waitFor();
        await button('Back to epochs').click();
        await page.locator('.cell-tree-date').first().evaluate(el=>{el.open=true;});
        await page.locator('.cell-tree-cell').first().evaluate(el=>{el.open=true;});
        try{await measure('trace.inspect','first-owned-waveform',page.getByRole('button',{name:`Inspect ${meta.date_label} · ${meta.cell_label} epoch 1`,exact:true}),{selector:'.tv-base',trace:meta.trace_expected});}catch{} // Retain failed trace evidence while exercising independent workflows.
        await button('Benchmark Predicate').click();await page.getByText('Metadata summaries: ready',{exact:true}).waitFor({timeout:Number(config.action_timeout_ms||(phase==='profile'?900000:600000))});try{await measure('predicate.search','cell-equality',button('View matching epochs'),{selector:'.mx-results-workflow',requestPath:'/explore/run',expectedCount:expected.length,searchUuids:expected});}catch{}
        await button('Benchmark Away').click();
        // Restore the owned post-import state outside the action clock, only
        // after this browser's outstanding setup effects have drained.
        await page.waitForFunction(()=>window.__workflow.requests.every(r=>r.end!==undefined||r.error),null,{timeout:Number(config.setup_timeout_ms||900000)});
        await page.evaluate(()=>{delete window.__workflow.incomingSession;});
        const reset=await resetPreparation(meta,{timeoutMs:Number(config.setup_timeout_ms||900000)});
        receipt.setup_receipts.push({phase,sample,action:'workbench.prepare/fresh',...reset});
        await fs.appendFile(path.join(output,'setup-receipts.jsonl'),JSON.stringify(receipt.setup_receipts.at(-1))+'\n');
        const preparation=await measure('workbench.prepare','fresh',button('Benchmark Workbench'),{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:meta.incoming_epochs,expectedReused:false,expectedPrepareStatus:201});
        await measure('tree.selection','incoming-select-all',button('Select all'),{selector:'button',text:`Merge (${meta.incoming_count} epochs)`,selected:meta.incoming_epochs});
        await measure('tree.selection','incoming-deselect-all',button('Deselect all'),{selector:'button',text:'Merge (0 epochs)',selected:[]});
        await button('Benchmark Away').click();
        await page.evaluate(()=>{delete window.__workflow.incomingSession;});
        const replay=await measure('workbench.prepare','receipt-replay',button('Benchmark Workbench'),{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:meta.incoming_epochs,expectedReused:false,expectedPrepareStatus:200,expectedCandidate:preparation.correctness.prepared.candidate_revision_uuid,expectedOperation:preparation.correctness.prepared.operation_uuid});
        await button('Benchmark Away').click();await measure('workbench.open','prepared-return',button('Benchmark Workbench'),{selector:'button',text:'Select all',enabled:true,savedPrepared:replay.correctness.prepared,preparedUuids:meta.incoming_epochs});
        await page.locator('.incoming-browser .cell-tree-date').first().evaluate(el=>{el.open=true;});
        await page.locator('.incoming-browser .cell-tree-cell').first().evaluate(el=>{el.open=true;});
        const incomingRow=page.getByRole('button',{name:`Inspect ${meta.date_label} · ${meta.incoming_cell_label} epoch 1`,exact:true});
        const traceRoot='/protocols/'+meta.protocol+'/workbench/candidates/'+replay.correctness.prepared.candidate_revision_uuid;
        await measure('trace.inspect','frozen-workbench-300k',incomingRow,{selector:'.tv-base',trace:meta.incoming_trace_expected,traceRoot,traceRevision:replay.correctness.prepared.candidate_scope_revision});
        await measure('trace.inspect','frozen-workbench-1m',page.getByRole('button',{name:`Inspect ${meta.date_label} · ${meta.incoming_cell_label} epoch 2`,exact:true}),{selector:'.tv-base',trace:meta.million_trace_expected,traceRoot,traceRevision:replay.correctness.prepared.candidate_scope_revision});
      if(production)receipt.production_attestations.push({phase,sample,stage:'completed',...await attestProductionPage(page,production,`http://127.0.0.1:${receipt.frontend_port}`)});
      }catch(error){receipt.failures.push({phase,sample,error:String(error)});}finally{ledger.detach();await fs.writeFile(path.join(output,`browser-requests-${phase}-${sample}.json`),JSON.stringify(await page.evaluate(()=>window.__workflow.requests.map(({result,binary,...row})=>row)),null,2));await fs.writeFile(path.join(output,`ledger-${phase}-${sample}.json`),JSON.stringify(ledger.entries,null,2));await context.close();context=null;}
    }
    for(const action of receipt.actions)if(action.samples.filter(s=>s.phase==='ordinary').length!==config.samples)receipt.gaps.push(`Missing ordinary samples: ${action.id}/${action.variant}`);
    receipt.status=receipt.failures.length?'failed':receipt.gaps.length?'incomplete':'passed';
  }catch(error){receipt.failures.push({error:String(error)});receipt.status='failed';}
  finally{for(const [name,value] of [['context',context],['browser',browser],['vite',server]]){try{if(value)await value.close();receipt.cleanup[name+'_closed']=true;}catch(error){receipt.cleanup[name+'_closed']=false;receipt.failures.push({cleanup:name,error:String(error)});receipt.status='failed';}}await fs.writeFile(path.join(output,'browser.json'),JSON.stringify(receipt,null,2));}
  return receipt;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){run(options(process.argv.slice(2))).then(r=>{console.log(JSON.stringify({status:r.status,failures:r.failures.length,output:'browser.json'}));if(r.status==='failed')process.exitCode=1;}).catch(e=>{console.error(e);process.exitCode=1;});}
