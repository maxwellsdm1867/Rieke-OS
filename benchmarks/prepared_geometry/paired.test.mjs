import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {runPaired,pairedOrder,pairedProtocol} from './paired.mjs';
import {removeBuildLinks} from './build.mjs';

function fixture(failure={}){
 const events=[],sessions={};let active=false,launches=0;
 const plan={pair_id:'1'.repeat(32),sources:Object.fromEntries(['baseline','candidate'].map(role=>[role,{root:role,binding:{commit:role}}]))};
 const browsers=Object.fromEntries(['baseline','candidate'].map((role,i)=>[role,{geometryOwner:{pid:failure.shared?200:200+i},version:()=>failure.version&&role==='candidate'?'other-browser':'pinned-browser',async close(){events.push('browser-close-'+role);if(failure.close)throw Error('browser cleanup failed');}}]));
 const create=async source=>{
  const role=source.root;
  const session={receipt:{},async prepare(){events.push('prepare-'+role);if(failure.prepare===role)throw Error('build failed');},
   async sample(received,index,observation){
    assert.equal(received,browsers[role]);assert.equal(observation.browser_instance,browsers[role].geometryOwner.pid);assert.equal(active,false,'source actions must never overlap');active=true;
    assert.equal(observation.source_role,role);assert.equal(observation.protocol,pairedProtocol);assert.equal(observation.pair_id,plan.pair_id);
    assert.equal(observation.execution_index,events.filter(x=>x.startsWith('sample-')).length);
    events.push(`sample-${role}-${index}`);await Promise.resolve();active=false;
    if(failure.sample===`${role}-${index}`)throw Error('exact wire oracle failed');
   },async finish(error){events.push('finish-'+role);session.error=error;if(failure.finish===role)throw Error('receipt write failed');}};
  sessions[role]=session;return session;
 };
 const launch=async root=>{assert.deepEqual(events.slice(0,2),['prepare-baseline','prepare-candidate']);assert.ok(['baseline','candidate'].includes(root));launches++;events.push('launch-'+root);if(failure.launch)throw Error('browser unavailable');return browsers[root];};
 return {plan,events,sessions,create,launch,get launches(){return launches;}};
}
test('both source builds precede two independent browsers and exactly six serial source-isolated samples',async()=>{
 const f=fixture();const pair=await runPaired(f.plan,f);
 assert.equal(f.launches,2);
 assert.deepEqual(f.events,['prepare-baseline','prepare-candidate','launch-baseline','launch-candidate','sample-baseline-0','sample-candidate-0','sample-candidate-1','sample-baseline-1','sample-baseline-2','sample-candidate-2','browser-close-baseline','browser-close-candidate','finish-baseline','finish-candidate']);
 assert.deepEqual(pair.completed,pairedOrder.map((row,i)=>({...row,execution_index:i})));
 assert.equal(f.sessions.baseline.receipt.pair,pair);assert.equal(f.sessions.candidate.receipt.pair,pair);
 assert.deepEqual(pair.sources,{baseline:{commit:'baseline'},candidate:{commit:'candidate'}});
 assert.equal(f.sessions.baseline.receipt.pair_role,'baseline');assert.equal(f.sessions.candidate.receipt.pair_role,'candidate');
});
test('a failed exact oracle stops the fixed schedule without retries and fails both receipts',async()=>{
 const f=fixture({sample:'candidate-1'});await assert.rejects(runPaired(f.plan,f),/execution failed/);
 assert.deepEqual(f.events.filter(x=>x.startsWith('sample-')),['sample-baseline-0','sample-candidate-0','sample-candidate-1']);
 for(const role of ['baseline','candidate'])assert.match(String(f.sessions[role].error),/exact wire oracle/);
 assert.deepEqual(f.sessions.baseline.receipt.pair.completed,[{role:'baseline',sample:0,execution_index:0},{role:'candidate',sample:0,execution_index:1}]);
 assert.ok(f.events.includes('browser-close-baseline'));assert.ok(f.events.includes('browser-close-candidate'));
});
for(const failure of [{prepare:'candidate'},{launch:true},{close:true},{finish:'baseline'},{shared:true},{version:true}])test(`paired lifecycle refuses ${JSON.stringify(failure)} and finishes both created sources`,async()=>{
 const f=fixture(failure);await assert.rejects(runPaired(f.plan,f),/execution failed/);
 assert.ok(f.events.includes('finish-baseline'));assert.ok(f.events.includes('finish-candidate'));
 if(failure.prepare||failure.launch||failure.shared||failure.version)assert.equal(f.events.some(x=>x.startsWith('sample-')),false);
});
test('missing source plan never starts a partial experiment',async()=>{
 const f=fixture();delete f.plan.sources.candidate;
 await assert.rejects(runPaired(f.plan,f),/Invalid paired source plan/);assert.deepEqual(f.events,[]);
});
test('build-only source and dependency links are unlinked without following targets',async t=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'geometry-links-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const target=path.join(root,'actual-source');await fs.mkdir(target);await fs.writeFile(path.join(target,'keep'),'scientific source');
 const links=['src','node_modules'].map(name=>path.join(root,name));for(const link of links)await fs.symlink(target,link,'dir');
 await removeBuildLinks(links);assert.equal(await fs.readFile(path.join(target,'keep'),'utf8'),'scientific source');
 for(const link of links)await assert.rejects(fs.lstat(link),{code:'ENOENT'});
 const replaced=path.join(root,'unexpected-file');await fs.writeFile(replaced,'preserve');
 await assert.rejects(removeBuildLinks([replaced]),/was replaced/);assert.equal(await fs.readFile(replaced,'utf8'),'preserve');
});

test('diagnostic reversed launch keeps the exact six-sample schedule and source ownership',async t=>{
 const original=process.env.DISCO_DIAGNOSTIC_REVERSE_LAUNCH;
 process.env.DISCO_DIAGNOSTIC_REVERSE_LAUNCH='1';t.after(()=>{if(original===undefined)delete process.env.DISCO_DIAGNOSTIC_REVERSE_LAUNCH;else process.env.DISCO_DIAGNOSTIC_REVERSE_LAUNCH=original;});
 const f=fixture();const pair=await runPaired(f.plan,f);
 assert.deepEqual(f.events.filter(x=>x.startsWith('launch-')),['launch-candidate','launch-baseline']);
 assert.deepEqual(f.events.filter(x=>x.startsWith('sample-')),['sample-baseline-0','sample-candidate-0','sample-candidate-1','sample-baseline-1','sample-baseline-2','sample-candidate-2']);
 assert.deepEqual(pair.diagnostic_launch_order,['candidate','baseline']);assert.equal(pair.diagnostic_only,true);
});
