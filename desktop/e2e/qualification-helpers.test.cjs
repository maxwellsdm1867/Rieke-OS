'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {cleanupOwnedFixture}=require('./qualification-helpers.cjs');
test('owned failure cleanup uses ordinary renderer Quit and observes successful exit',async()=>{
 const child=new EventEmitter();child.exitCode=null;let called=0;
 const page={evaluate:async callback=>{assert.match(String(callback),/riekeDesktop.quit/);called++;child.exitCode=0;child.emit('exit',0);}};
 assert.deepEqual(await cleanupOwnedFixture({process:()=>child},page,{timeout:50}),{state:'orderly-exit'});assert.equal(called,1);
});
test('unresponsive ordinary Quit is bounded and retained without force termination',async()=>{
 const child=new EventEmitter();child.exitCode=null;child.kill=()=>assert.fail('Cleanup must never force termination');
 const began=Date.now(),result=await cleanupOwnedFixture({process:()=>child},{evaluate:()=>new Promise(()=>{})},{timeout:20});
 assert.equal(result.state,'owned-fixture-retained');assert.match(result.reason,/deadline/);assert.ok(Date.now()-began<500);
});
test('cleanup does not reuse a stale page after the owned process has exited',async()=>{
 const result=await cleanupOwnedFixture({process:()=>({exitCode:0})},{evaluate:()=>assert.fail('No stale bridge call')});
 assert.deepEqual(result,{state:'already-exited',exit_code:0});
});

test('project draft targeting uses canonical owned paths and isolates UUID-sharing copies from launcher',async()=>{
 const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
 const {projectDraftPath}=require('./qualification-helpers.cjs');
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'disco-draft-target-'));
 try{
  const home=path.join(root,'home'),userData=path.join(home,'state'),first=path.join(home,'first'),second=path.join(home,'second'),alias=path.join(home,'alias');
  for(const directory of [userData,first,second])await fs.mkdir(directory,{recursive:true});
  await fs.symlink(first,alias);const uuid='12345678-1234-4234-8234-123456789abc';
  const direct=await projectDraftPath({home,userData},{uuid,path:first});
  assert.equal(await projectDraftPath({home,userData},{uuid,path:alias}),direct,'Canonical aliases must target the same owned view');
  assert.notEqual(await projectDraftPath({home,userData},{uuid,path:second}),direct,'UUID-sharing project copies must remain isolated');
  assert.ok(direct.startsWith(path.join(await fs.realpath(userData),'scoped-views')+path.sep));
  assert.notEqual(direct,path.join(userData,'drafts',uuid+'.json'));
  await assert.rejects(projectDraftPath({home,userData},{uuid:'launcher',path:first}),/separate root store/);
  await assert.rejects(projectDraftPath({home,userData},{uuid,path:root}),/escapes its owned HOME/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
