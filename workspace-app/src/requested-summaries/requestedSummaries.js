/**
 * Public requested-summaries entry; see ./AGENTS.md for the complete interface,
 * identity, cancellation and authority contract and executable consumer examples.
 */
import {jointComponents} from '../typed-query/jointGrouping.js';
import {predicateIdentity} from '../typed-query/predicateIdentity.js';

export const SUMMARY_PREFERENCES_VERSION=1;
export function summaryPreferenceKey(project,protocol,view){
  return `workspace.summary-preferences.v1:${JSON.stringify([project,protocol,view])}`;
}
export function summaryPreferences(value){
  // This is a new explicit schema. Saved layouts are seeds, never preferences.
  if(value?.version!==SUMMARY_PREFERENCES_VERSION||!Array.isArray(value.fields))return {version:SUMMARY_PREFERENCES_VERSION,fields:[]};
  return {version:SUMMARY_PREFERENCES_VERSION,fields:[...new Set(value.fields.filter(id=>typeof id==='string'&&id))]};
}
export function predicateSummaryFields(node){
  if(!node)return [];
  if(node.field)return [node.field];
  if(node.not)return predicateSummaryFields(node.not);
  return (node.children||node.all||node.any||[]).flatMap(predicateSummaryFields);
}
export function requestedSummaryFields({registry=[],axes=[],predicate,preferences,all=false}){
  const available=new Set(registry.map(field=>field.id));
  const selected=all?[...available]:[...axes,...predicateSummaryFields(predicate),...summaryPreferences(preferences).fields];
  const ids=[...new Set(selected.flatMap(id=>jointComponents(id).length?jointComponents(id):[id]))];
  return {fields:ids.filter(id=>available.has(id)),unavailable:ids.filter(id=>!available.has(id))};
}
export const summaryRequestKey=request=>predicateIdentity(JSON.parse(JSON.stringify(request)));
export function fieldsWithSummaries(fields,state){
  if(state.status!=='ready')return fields;
  return fields.map(field=>{
    const facet=state.result?.summaries?.[field.id];
    if(!facet)return field;
    const values=facet.values||[];
    // Buckets are typed; a null value is recorded, distinct from absent fields.
    const result={...field,choices:values.map(value=>({...value})),choices_truncated:facet.values_truncated,
      missing_count:facet.missing_count,present_count:facet.present_count,summary_available:true,
      examples:values.slice(0,3).map(item=>JSON.stringify(item.value))};
    if(facet.values_truncated===false){
      result.distinct_count=values.length;
      result.recorded_distinct_count=values.filter(item=>item.type!=='null').length;
      result.null_count=values.filter(item=>item.type==='null').reduce((sum,item)=>sum+item.count,0);
    }
    return result;
  });
}

// Registry annotation witnesses describe global eligibility. A job may add a
// frozen binding or scoped annotation witness, so admission compares only the
// common immutable/source authority. Subsequent polls use the exact job token.
export function registryMatchesSummaryGeneration(registry,context){
  if(!registry||!context)return false;
  return ['metadata','typed','source','publication'].every(key=>
    !Object.hasOwn(registry,key)||(Object.hasOwn(context,key)&&predicateIdentity(registry[key])===predicateIdentity(context[key])));
}

// The controller consumes a small adapter so lifecycle tests need no API/server.
// Local sequence fencing remains necessary even when AbortSignal is ignored.
export function createSummaryController({adapter,onState,pollMs=250,schedule=setTimeout,unschedule=clearTimeout}){
  let serial=0,active=null,disposed=false;
  const publish=(run,state)=>{if(!disposed&&active===run&&!run.stopped)onState({...state,key:run.key});};
  function release(run){
    if(!run||run.stopped)return;
    run.stopped=true;run.controller.abort();if(run.timer!=null)unschedule(run.timer);
    if(run.receipt?.request_id&&run.receipt.status==='pending')Promise.resolve().then(()=>adapter.cancel(run.receipt.request_id)).catch(()=>{});
  }
  async function receive(run,receipt){
    // A submission may return its job after navigation/cancellation.
    if(disposed||active!==run||run.stopped){
      if(receipt?.request_id&&receipt.status==='pending')Promise.resolve().then(()=>adapter.cancel(receipt.request_id)).catch(()=>{});
      return;
    }
    if(typeof receipt?.request_id!=='string'||!receipt.request_id||(run.receipt?.request_id&&receipt.request_id!==run.receipt.request_id))throw Error('Invalid metadata summary request identity.');
    const previousGeneration=run.receipt?.generation;
    run.receipt=receipt;
    if(!['pending','ready','cancelled','stale','failed'].includes(receipt?.status))throw Error('Invalid metadata summary status.');
    if(receipt.status==='ready'&&(!receipt.result||!receipt.result.summaries))throw Error('Missing metadata summary result.');
    const generationMatches=previousGeneration
      ?predicateIdentity(receipt.generation)===predicateIdentity(previousGeneration)
      :!run.request.generation||registryMatchesSummaryGeneration(run.request.generation,receipt.generation);
    if(!generationMatches){
      publish(run,{status:'stale',generation:receipt.generation,result:null,error:null});release(run);return;
    }
    publish(run,{...receipt,result:receipt.status==='ready'?receipt.result:null,error:receipt.error||null});
    if(receipt.status==='pending'){
      if(!receipt.request_id)throw Error('Missing metadata summary request identity.');
      run.timer=schedule(()=>execute(run,()=>adapter.poll(receipt.request_id,run.controller.signal)),pollMs);
    }
  }
  async function execute(run,operation){
    try{await receive(run,await operation());}
    catch(error){if(active===run&&!run.stopped&&!disposed){
      publish(run,{status:error.data?.status==='stale'?'stale':'failed',generation:error.data?.generation,result:null,error:error.message});
      release(run);
    }}
  }
  return {
    start(request){
      release(active);const run={serial:++serial,key:summaryRequestKey(request),request,controller:new AbortController(),stopped:false};active=run;
      publish(run,{status:'pending',result:null,error:null});
      execute(run,()=>adapter.submit(request,run.controller.signal));return run.key;
    },
    cancel(){if(active&&!active.stopped){publish(active,{status:'cancelled',result:null,error:null});release(active);}},
    dispose(){disposed=true;release(active);active=null;},
  };
}
