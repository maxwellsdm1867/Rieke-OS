import test from 'node:test';
import assert from 'node:assert/strict';
import {createSummaryController,fieldsWithSummaries,requestedSummaryFields,summaryPreferences,summaryPreferenceKey} from './requestedSummaries.js';
import {jointId} from '../typed-query/jointGrouping.js';
const generation={metadata:'M',source:'S',annotation:'A',publication:'P'};
const request={predicate:{all:[]},summary_fields:['number'],generation};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function harness(){
 const states=[],jobs=[],cancelled=[],timers=new Map();let id=0;
 const adapter={submit:(request,signal)=>{const work=deferred();jobs.push({request,signal,work});return work.promise;},poll:(id,signal)=>{const work=deferred();jobs.push({id,signal,work});return work.promise;},cancel:id=>{cancelled.push(id);return Promise.resolve();}};
 const client=createSummaryController({adapter,onState:state=>states.push(state),schedule:callback=>{timers.set(++id,callback);return id;},unschedule:id=>timers.delete(id)});
 return {states,jobs,cancelled,timers,client,get state(){return states.at(-1);},tick(){const [id,callback]=timers.entries().next().value;timers.delete(id);callback();}};
}
const pending=id=>({request_id:id,status:'pending',generation});
const ready=id=>({request_id:id,status:'ready',generation,result:{matched_count:0,summaries:{number:{values:[],present_count:0,missing_count:0,values_truncated:false}}}});

test('active axes, nested predicates and explicit preferences request exact IDs without a whitelist',()=>{
 const registry=Array.from({length:201},(_,i)=>({id:`parameters/new${i}`}));
 const axes=[jointId(['parameters/new150','parameters/new200']),'parameters/absent'];
 const preferences={version:1,fields:['parameters/new199','parameters/absent']};
 const predicate={not:{any:[{field:'parameters/new150'},{all:[{field:'parameters/new198'}]}]}};
 assert.deepEqual(requestedSummaryFields({registry,axes,predicate,preferences}),{fields:['parameters/new150','parameters/new200','parameters/new198','parameters/new199'],unavailable:['parameters/absent']});
 assert.equal(requestedSummaryFields({registry,all:true}).fields.length,201);
 assert.deepEqual(axes,[jointId(['parameters/new150','parameters/new200']),'parameters/absent']);
 assert.deepEqual(preferences.fields,['parameters/new199','parameters/absent']);
});
test('preferences are a new versioned protocol/view schema; layouts are never inferred preferences',()=>{
 assert.deepEqual(summaryPreferences({split_order:['history1']}),{version:1,fields:[]});
 assert.deepEqual(summaryPreferences({version:2,fields:['history1']}),{version:1,fields:[]});
 assert.deepEqual(summaryPreferences({version:1,fields:['history1','history1','missing',null]}),{version:1,fields:['history1','missing']});
 const keys=[summaryPreferenceKey('project-A','protocol-A','tree'),summaryPreferenceKey('project-B','protocol-A','tree'),summaryPreferenceKey('project-A','protocol-B','tree'),summaryPreferenceKey('project-A','protocol-A','filter')];
 assert.equal(new Set(keys).size,4);
});
test('missing summaries and pending/stale data never become zero counts or recorded choices',()=>{
 const fields=[{id:'number'},{id:'missing'}];
 for(const status of ['idle','pending','cancelled','failed','stale'])assert.equal(fieldsWithSummaries(fields,{status,result:ready('x').result}),fields);
 const output=fieldsWithSummaries(fields,{status:'ready',result:ready('x').result});
 assert.equal(output[0].distinct_count,0);assert.equal(output[1].distinct_count,undefined);assert.equal(output[1].missing_count,undefined);
});
test('typed null/array/mixed-number summaries preserve exact source values; truncated buckets do not claim distinct counts',()=>{
 const values=[{value:null,type:'null',count:3},{value:[1,'1'],type:'array',count:4},{value:1,type:'number',count:5},{value:'1',type:'string',count:6}];
 const facet={values,present_count:18,missing_count:2,values_truncated:true};
 const field=fieldsWithSummaries([{id:'raw'}],{status:'ready',result:{summaries:{raw:facet}}})[0];
 assert.deepEqual(field.choices,values);assert.equal(field.distinct_count,undefined);assert.equal(field.null_count,undefined);assert.equal(field.missing_count,2);
 facet.values_truncated=false;
 const exact=fieldsWithSummaries([{id:'raw'}],{status:'ready',result:{summaries:{raw:facet}}})[0];
 assert.equal(exact.distinct_count,4);assert.equal(exact.recorded_distinct_count,3);assert.equal(exact.null_count,3);
});
test('A/B/A navigation cancels both old jobs and ignores late submission completions even with the same key',async()=>{
 const h=harness();h.client.start(request);h.client.start({...request,scope:{cell_uuid:'B'}});h.client.start(request);
 assert.equal(h.jobs[0].signal.aborted,true);assert.equal(h.jobs[1].signal.aborted,true);
 h.jobs[2].work.resolve(ready('new-A'));await settle();assert.equal(h.state.request_id,'new-A');
 h.jobs[0].work.resolve(pending('old-A'));h.jobs[1].work.resolve(pending('old-B'));await settle();
 assert.equal(h.state.request_id,'new-A');assert.deepEqual(h.cancelled,['old-A','old-B']);h.client.dispose();
});
test('polling publishes exact ready result and stops; no timers remain after cancel',async()=>{
 const h=harness();h.client.start(request);h.jobs[0].work.resolve(pending('first'));await settle();
 assert.equal(h.state.status,'pending');assert.equal(h.timers.size,1);h.tick();
 h.jobs[1].work.resolve(ready('first'));await settle();assert.equal(h.state.status,'ready');assert.equal(h.state.result.matched_count,0);assert.equal(h.timers.size,0);h.client.dispose();
 const c=harness();c.client.start(request);c.jobs[0].work.resolve(pending('cancel'));await settle();c.client.cancel();await settle();
 assert.equal(c.state.status,'cancelled');assert.equal(c.state.result,null);assert.equal(c.timers.size,0);assert.deepEqual(c.cancelled,['cancel']);c.client.dispose();
});
test('cancelling an unacknowledged submission cancels its later server job and retains cancelled state',async()=>{
 const h=harness();h.client.start(request);h.client.cancel();h.jobs[0].work.resolve(pending('late'));await settle();
 assert.deepEqual(h.cancelled,['late']);assert.equal(h.state.status,'cancelled');h.client.dispose();
});
test('generation drift on poll suppresses otherwise ready data',async()=>{
 const h=harness();h.client.start(request);h.jobs[0].work.resolve(pending('generation'));await settle();h.tick();
 h.jobs[1].work.resolve({...ready('generation'),generation:{...generation,annotation:'new'}});await settle();
 assert.equal(h.state.status,'stale');assert.equal(h.state.result,null);assert.equal(h.timers.size,0);h.client.dispose();
});
test('409 stale submission and failed requests expose states without synthetic results',async()=>{
 for(const status of ['stale','failed']){
  const h=harness();h.client.start(request);const error=Error('Generation changed');if(status==='stale')error.data={status:'stale',generation:{...generation,publication:'new'}};
  h.jobs[0].work.reject(error);await settle();assert.equal(h.state.status,status);assert.equal(h.state.result,null);h.client.dispose();
 }
});
test('cancelled, stale and failed receipts retain no prior result; malformed responses fail',async()=>{
 for(const status of ['cancelled','stale','failed','invented']){
  const h=harness();h.client.start(request);h.jobs[0].work.resolve({request_id:'x',status,generation,result:ready('x').result});await settle();
  assert.equal(h.state.status,status==='invented'?'failed':status);assert.equal(h.state.result,null);h.client.dispose();
 }
});
test('unmount fences late results and cancels outstanding acknowledged and late jobs',async()=>{
 for(const acknowledged of [true,false]){
  const h=harness();h.client.start(request);
  if(acknowledged){h.jobs[0].work.resolve(pending('unmount'));await settle();}
  h.client.dispose();const n=h.states.length;
  if(!acknowledged)h.jobs[0].work.resolve(pending('unmount'));
  await settle();assert.equal(h.states.length,n);assert.equal(h.timers.size,0);assert.deepEqual(h.cancelled,['unmount']);
 }
});

test('polls cannot publish a different job identity even under the same generation',async()=>{
 const h=harness();h.client.start(request);h.jobs[0].work.resolve(pending('correct'));await settle();h.tick();h.jobs[1].work.resolve(ready('other'));await settle();assert.equal(h.state.status,'failed');assert.equal(h.state.result,null);h.client.dispose();
});

test('scoped annotation and binding witnesses are accepted at admission and exact scoped witnesses fence polls',async()=>{
 const h=harness(),registry={...generation,typed:'T'},scoped={...registry,annotation:{shared:'scoped-A',curation:'scoped-C'},binding:7};
 h.client.start({...request,generation:registry,protocol_uuid:'protocol-A'});h.jobs[0].work.resolve({...pending('scoped'),generation:scoped});await settle();assert.equal(h.state.status,'pending');h.tick();h.jobs[1].work.resolve({...ready('scoped'),generation:scoped});await settle();assert.equal(h.state.status,'ready');h.client.dispose();
 for(const witness of ['annotation','binding','typed']){
  const c=harness();c.client.start({...request,generation:registry});c.jobs[0].work.resolve({...pending('scoped'),generation:scoped});await settle();c.tick();c.jobs[1].work.resolve({...ready('scoped'),generation:{...scoped,[witness]:'changed'}});await settle();assert.equal(c.state.status,'stale');assert.equal(c.state.result,null);c.client.dispose();
 }
});
test('registry authority drift and missing authority witnesses reject initial job receipts',async()=>{
 const registry={...generation,typed:'T'};
 for(const witness of ['metadata','typed','source','publication']){
  for(const missing of [false,true]){
   const h=harness(),context={...registry,annotation:'scoped'};if(missing)delete context[witness];else context[witness]='changed';h.client.start({...request,generation:registry});h.jobs[0].work.resolve({...pending('invalid'),generation:context});await settle();assert.equal(h.state.status,'stale');assert.equal(h.state.result,null);assert.deepEqual(h.cancelled,['invalid']);h.client.dispose();
  }
 }
});
