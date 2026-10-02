/* Independent input-to-observable-render measurements for the actual app.
 * The caller owns native truth assertions and exact source/generation fences.
 * A failed/censored action never becomes a completed timing sample.
 */
const {performance}=require('node:perf_hooks');

function generationKey(value){
 if(value===null||value===undefined)throw new Error('Missing generation fence');
 const ordered=item=>Array.isArray(item)?item.map(ordered):item&&typeof item==='object'?
  Object.fromEntries(Object.keys(item).sort().map(key=>[key,ordered(item[key])])):item;
 return JSON.stringify(ordered(value));
}

function validateReceipt(receipt){
 if(!receipt.input||!receipt.input.trusted)throw new Error('Missing trusted UI input');
 if(!receipt.truth_checked)throw new Error('Native truth assertion did not complete');
 if(!receipt.source_hash||!receipt.generation_before||!receipt.generation_after)throw new Error('Missing source or generation fence');
 const before=receipt.generation_before,after=receipt.generation_after;
 const allowed=receipt.allowed_generation_dimensions||[];
 if(allowed.some(key=>!['annotation','publication','binding'].includes(key)))throw new Error('Scientific source changes cannot be waived');
 if(allowed.length){
  if(typeof before!=='object'||typeof after!=='object')throw new Error('Mutation receipts require complete generation tokens');
  const keep=token=>Object.fromEntries(Object.entries(token).filter(([key])=>!allowed.includes(key)));
  if(generationKey(keep(before))!==generationKey(keep(after)))throw new Error('Scientific source generation changed during a mutation');
 }else if(generationKey(before)!==generationKey(after))throw new Error('Generation changed during a read action');
 if(!Number.isFinite(receipt.event_to_stable_ms)||receipt.event_to_stable_ms<0)throw new Error('Invalid render duration');
 if(receipt.event_to_stable_ms>receipt.cap_ms)throw new Error('Render exceeded its timing cap');
 return receipt;
}

async function measureRenderedAction(page,{id,sourceHash,generation,act,assertTruth,capMs=45000,allowedGenerationDimensions=[]}){
 if(typeof assertTruth!=='function')throw new Error('An independent truth assertion is required');
 const before=await generation();
 await page.evaluate(()=>{
  const state={input:null};window.__nativeQualificationInput=state;
  const capture=event=>{
   if(state.input)return;
   state.input={type:event.type,trusted:event.isTrusted,started:performance.now()};
  };
  state.capture=capture;
  for(const type of ['pointerdown','keydown','input','wheel'])document.addEventListener(type,capture,true);
 });
 const started=performance.now();let timer;
 const work=(async()=>{
  await act();
  await assertTruth();
  const render=await page.evaluate(async()=>{
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   const input=window.__nativeQualificationInput.input;
   return {input,event_to_stable_ms:input?performance.now()-input.started:null};
  });
  // The post-render authority probe is outside click-to-paint time. Its failure
  // still rejects the sample. assertTruth should use immutable preloaded truth.
  const after=await generation();
  return validateReceipt({id,source_hash:sourceHash,generation_before:before,
   generation_after:after,allowed_generation_dimensions:allowedGenerationDimensions,
   cap_ms:capMs,truth_checked:true,...render});
 })();
 try{
  return await Promise.race([work,new Promise((_,reject)=>{
   timer=setTimeout(()=>reject(new Error(`Action ${id} censored at ${capMs}ms`)),capMs);
  })]);
 }catch(error){
  // Close this page before another sample if pending act/assertion work exists.
  error.qualification={id,status:'failed_or_censored',wall_ms:performance.now()-started,
   cap_ms:capMs,source_hash:sourceHash,completed_samples:0};throw error;
 }finally{
  clearTimeout(timer);
  await page.evaluate(()=>{
   const state=window.__nativeQualificationInput;
   if(state)for(const type of ['pointerdown','keydown','input','wheel'])document.removeEventListener(type,state.capture,true);
   delete window.__nativeQualificationInput;
  }).catch(()=>{});
 }
}
module.exports={measureRenderedAction,validateReceipt};
