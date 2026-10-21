import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createSourceSession,launchBrowser} from './browser.mjs';

export const pairedProtocol='paired-independent-browsers-BCCBBC-v1';
export const pairedOrder=Object.freeze([
 ['baseline',0],['candidate',0],['candidate',1],
 ['baseline',1],['baseline',2],['candidate',2],
].map(([role,sample])=>Object.freeze({role,sample})));

// Two independent browsers preserve each source's first-trace graphics state.
// Source builds finish before browser startup; no warmup sample is omitted.
// Dependencies are injectable only for tests, never through the CLI or plan.
export async function runPaired(plan,{create=createSourceSession,launch=launchBrowser}={}){
 if(!plan||typeof plan.pair_id!=='string'||!plan.pair_id||!plan.sources?.baseline||!plan.sources?.candidate)throw Error('Invalid paired source plan');
 const sessions={},browsers={},errors=[];
 const pair={id:plan.pair_id,protocol:pairedProtocol,sources:Object.fromEntries(['baseline','candidate'].map(role=>[role,plan.sources[role].binding])),order:pairedOrder,completed:[]};
 try{
  for(const role of ['baseline','candidate']){
   sessions[role]=await create(plan.sources[role]);
   sessions[role].receipt.pair=pair;sessions[role].receipt.pair_role=role;
   await sessions[role].prepare();
  }
  const launchOrder=process.env.DISCO_DIAGNOSTIC_REVERSE_LAUNCH==='1'?['candidate','baseline']:['baseline','candidate'];
  pair.diagnostic_only=true;pair.diagnostic_launch_order=launchOrder;
  for(const role of launchOrder)browsers[role]=await launch(plan.sources[role].root,{processFile:plan.sources[role].process_file});
  pair.browser_version=browsers.baseline.version();
  if(browsers.candidate.version()!==pair.browser_version)throw Error('Pinned browser versions differ');
  pair.browser_instances=Object.fromEntries(['baseline','candidate'].map(role=>[role,browsers[role].geometryOwner.pid]));
  if(pair.browser_instances.baseline===pair.browser_instances.candidate)throw Error('Sources must use independent browsers');
  for(const [execution_index,{role,sample}] of pairedOrder.entries()){
   await sessions[role].sample(browsers[role],sample,{protocol:pairedProtocol,pair_id:pair.id,source_role:role,execution_index,browser_instance:pair.browser_instances[role]});
   pair.completed.push({role,sample,execution_index});
  }
 }catch(error){errors.push(error);}
 finally{
  for(const browser of Object.values(browsers))try{await browser.close();}catch(error){errors.push(error);}
  // Finish both even when one capture or cleanup fails. Every receipt records
  // the same incomplete schedule; partial source success cannot qualify a pair.
  for(const session of Object.values(sessions))try{await session.finish(errors[0]??null);}catch(error){errors.push(error);}
 }
 if(errors.length)throw new AggregateError(errors,'Paired geometry execution failed');
 return pair;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const file=process.argv[2];
 Promise.resolve().then(async()=>runPaired(JSON.parse(await fs.readFile(file,'utf8')))).catch(error=>{console.error(error);process.exitCode=1;});
}
