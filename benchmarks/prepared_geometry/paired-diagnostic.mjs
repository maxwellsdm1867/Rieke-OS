// Diagnostic only. Fixed order, all samples preserved; no qualification bypass.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
const root=process.env.GITHUB_WORKSPACE,temp=process.env.RUNNER_TEMP;
const output=path.join(temp,'frame-diagnostic'),coordination=path.join(output,'coordination');
await fs.mkdir(coordination,{recursive:true});
const {chromium}=createRequire(path.join(root,'desktop/package.json'))('playwright');
const servers={};
const children=[],results=[];
const sequence=[['baseline',0],['candidate',0],['candidate',1],['baseline',1],['baseline',2],['candidate',2]];
await fs.writeFile(path.join(output,'plan.json'),JSON.stringify({diagnostic_only:true,sequence,samples_each:3,shared_browser:false,independent_browsers:true,fresh_contexts:true,baseline:'4de896f2e0b4ea966b5a428c3d2314f93fba935f',candidate:'f8488b95157be906e5bad63272a1d5a131805c47'},null,2));
async function waitFile(name){const until=Date.now()+300000;for(;;){if(children.some(p=>p.exitCode!==null&&p.exitCode!==0))throw Error('Diagnostic worker failed');try{await fs.access(path.join(coordination,name));return;}catch{}if(Date.now()>until)throw Error('Diagnostic rendezvous timed out: '+name);await new Promise(r=>setTimeout(r,50));}}
try{
 for(const arm of ['baseline','candidate']){
  const log=await fs.open(path.join(output,arm+'.log'),'w');
  const child=spawn(path.join(temp,'trace-python/bin/python'),['-B','tools/benchmark_prepared_geometry.py','run','--source-root',path.join(temp,'trace-'+arm),'--output',path.join(output,'run-'+arm)],{cwd:root,env:{...process.env,DISCO_DIAGNOSTIC_ENDPOINT_FILE:path.join(coordination,arm+'-endpoint'),DISCO_DIAGNOSTIC_COORDINATION:coordination,DISCO_DIAGNOSTIC_ARM:arm},stdio:['ignore',log.fd,log.fd]});
  children.push(child);results.push(new Promise(resolve=>child.once('close',code=>resolve({arm,code}))));await log.close();
 }
 await Promise.all(['baseline','candidate'].map(arm=>waitFile(arm+'-built')));
 for(const arm of ['baseline','candidate'])servers[arm]=await chromium.launchServer({headless:true,args:['--no-first-run','--no-default-browser-check']});
 for(const arm of ['baseline','candidate'])await fs.writeFile(path.join(coordination,arm+'-endpoint'),servers[arm].wsEndpoint());
 await fs.writeFile(path.join(output,'browser-instances.json'),JSON.stringify(Object.fromEntries(Object.entries(servers).map(([arm,server])=>[arm,server.process().pid]))));
 await Promise.all(['baseline','candidate'].map(arm=>waitFile(arm+'-ready')));
 for(const [arm,index] of sequence){await fs.writeFile(path.join(coordination,arm+'-'+index+'-permit'),'permit');await waitFile(arm+'-'+index+'-done');console.log(JSON.stringify({completed:arm,sample:index}));}
 const rows=await Promise.all(results);await fs.writeFile(path.join(output,'run-status.json'),JSON.stringify(rows,null,2));
 for(const arm of ['baseline','candidate']){const receipt=JSON.parse(await fs.readFile(path.join(output,'run-'+arm,'receipt.json'),'utf8'));console.log(JSON.stringify({arm,status:receipt.status,timings:receipt.samples?.map(row=>row.trace)}));}
 if(rows.some(row=>row.code!==0))throw Error('Diagnostic worker failed');
}finally{for(const child of children)if(child.exitCode===null)child.kill('SIGTERM');for(const server of Object.values(servers))await server.close();}
