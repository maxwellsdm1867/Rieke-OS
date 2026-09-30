import test from 'node:test';
import assert from 'node:assert/strict';
import {inspectAndOpenProject,localProjectUrl,verifiedTransferResult} from './projectTransfer.js';

test('only a verified transfer with a destination can be presented as ready',()=>{
  const result={verified:true,directory:'/research/shared-project',project_uuid:'project'};
  assert.equal(verifiedTransferResult(result),result);
  for(const invalid of [null,{}, {...result,verified:false},{...result,directory:''},{...result,verified:undefined}]){
    assert.throws(()=>verifiedTransferResult(invalid),/did not confirm/);
  }
});

test('opening restored projects accepts local HTTP URLs and rejects remote or executable destinations',()=>{
  assert.equal(localProjectUrl('http://127.0.0.1:8123','http://localhost:8000'),'http://127.0.0.1:8123/');
  assert.equal(localProjectUrl('http://[::1]:8123/','http://localhost:8000'),'http://[::1]:8123/');
  for(const url of [null,'javascript:alert(1)','https://example.com','file:///tmp/project','http://localhost.example.com','http://user:secret@localhost:8123']){
    assert.throws(()=>localProjectUrl(url,'http://localhost:8000'));
  }
});

test('transfer monitors a job until verification completes and surfaces server failures',async()=>{
  const {runProjectTransfer}=await import('./projectTransfer.js');
  const calls=[];
  const result={verified:true,directory:'/new/project'};
  const replies=[{job_id:'one/two',state:'running'},{state:'running'},{state:'complete',result}];
  const request=async(path,options)=>{calls.push({path,options});return replies.shift();};
  assert.equal(await runProjectTransfer({mode:'restore',directory:'/transfer',destination:'/new/project',request,pause:async()=>{}}),result);
  assert.equal(calls[0].path,'/projects/restore-transfer');
  assert.deepEqual(calls[0].options.body,{directory:'/transfer',destination:'/new/project'});
  assert.equal(calls[1].path,'/projects/transfers/one%2Ftwo');
  const failedReplies=[{job_id:'failed'},{state:'failed',error:'Project service is still running.'}];
  await assert.rejects(runProjectTransfer({mode:'prepare',request:async()=>failedReplies.shift()}),/service is still running/);
  const unverifiedReplies=[{job_id:'unverified'},{state:'complete',result:{directory:'/new/project'}}];
  await assert.rejects(runProjectTransfer({mode:'restore',request:async()=>unverifiedReplies.shift()}),/did not confirm/);
});

test('received portable copies are inspected and routed to restore without opening or moving them',async()=>{
  const calls=[];
  const inspection={valid:true,kind:'prepared-transfer',project:{name:'Shared study'},source_count:2};
  const result=await inspectAndOpenProject({directory:'/received/study',relocateDestination:'/my/study',request:async(path,options)=>{calls.push({path,options});return inspection;}});
  assert.equal(result.action,'restore');
  assert.equal(result.inspection,inspection);
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'/projects/inspect-folder');
  assert.deepEqual(calls[0].options.body,{directory:'/received/study'});
});

test('ordinary projects open after inspection, and optional relocation uses the moved directory',async()=>{
  const calls=[];
  const replies=[{valid:true,kind:'project'},{directory:'/preferred/study'},{url:'http://localhost:8123'}];
  const result=await inspectAndOpenProject({directory:'/received/study',relocateDestination:'/preferred/study',request:async(path,options)=>{calls.push({path,options});return replies.shift();}});
  assert.equal(result.action,'open');
  assert.equal(result.url,'http://localhost:8123');
  assert.deepEqual(calls.map(call=>call.path),['/projects/inspect-folder','/projects/relocate','/projects/open-folder']);
  assert.deepEqual(calls[2].options.body,{directory:'/preferred/study'});
});

test('failed or unrecognized inspection never starts a project service',async()=>{
  for(const inspection of [null,{valid:false},{valid:true,kind:'unrecognized'}]){
    let calls=0;
    await assert.rejects(inspectAndOpenProject({directory:'/received/study',request:async()=>{calls++;return inspection;}}));
    assert.equal(calls,1);
  }
});

test('nearby project roots are returned for explicit selection without opening or moving any candidate',async()=>{
  const inspection={valid:false,kind:'project-root-suggestions',candidates:[{path:'/research/study-a',name:'Study A'},{path:'/research/study-b',name:'Study B'}]};
  const calls=[];
  const result=await inspectAndOpenProject({directory:'/research',relocateDestination:'/chosen/study',request:async(path)=>{calls.push(path);return inspection;}});
  assert.equal(result.action,'choose-root');
  assert.equal(result.inspection,inspection);
  assert.deepEqual(calls,['/projects/inspect-folder']);
});


test('legacy inspection offers a separate desktop copy before opening or relocating',async()=>{
  const inspection={valid:true,kind:'project',desktop_compatibility:{requires_migration:true,migration_available:true}};
  const calls=[];
  const result=await inspectAndOpenProject({directory:'/old/project',relocateDestination:'/new/project',request:async path=>{calls.push(path);return inspection;}});
  assert.equal(result.action,'migrate');
  assert.deepEqual(calls,['/projects/inspect-folder']);
});

test('migration requires verified copy and unchanged source acknowledgments',async()=>{
  const {runProjectTransfer}=await import('./projectTransfer.js');
  for(const extra of [{migrated:true,source_unchanged:true},{migrated:true},{source_unchanged:true}]){
    const result={verified:true,directory:'/desktop/copy',...extra};
    const replies=[{job_id:'copy'},{state:'complete',result}];
    const calls=[];
    const operation=runProjectTransfer({mode:'migrate',directory:'/old/project',destination:'/desktop/copy',request:async(path,options)=>{calls.push({path,options});return replies.shift();}});
    if(extra.migrated&&extra.source_unchanged)assert.equal(await operation,result);
    else await assert.rejects(operation,/unchanged source/);
    assert.equal(calls[0].path,'/projects/migrate-source');
    assert.deepEqual(calls[0].options.body,{directory:'/old/project',destination:'/desktop/copy'});
  }
});
