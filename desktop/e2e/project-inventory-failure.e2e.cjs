'use strict';
// Real packaged app, denied owned directory, UI retry and clean ordinary Quit.
// This does not manufacture an OS-blocked syscall or touch real project roots.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {createFixture,launch,gracefulQuit,ownedControl}=require('./qualification-helpers.cjs');
const resultPath=process.env.RIEKE_E2E_RESULT;
if(!resultPath)throw Error('Set RIEKE_E2E_RESULT to a new evidence file');
const receipt={format:'disco-project-inventory-failure-v1',passed:false,checks:[],failures:[]};
let fixture,application,page,workspace;
async function main(){
 fixture=await createFixture();receipt.fixture_root=fixture.root;
 const manifest=JSON.parse(await fs.readFile(path.join(fixture.bundle,'Contents/Resources/runtime/runtime-manifest.json'),'utf8'));
 receipt.source_commit=manifest.source_commit;receipt.source_dirty=manifest.source_dirty;
 workspace=path.join(fixture.home,'Documents','RecordingWorkspace');
 await fs.mkdir(workspace,{recursive:true});await fs.chmod(workspace,0);
 ({application,page}=await launch(fixture));
 await page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:60000});
 await page.getByText(/Project folders could not be read/).waitFor();
 assert.equal(await page.getByText('No projects yet',{exact:true}).count(),0);
 const health=await ownedControl(fixture,'health');
 assert.equal(health.ready,true);assert.equal(health.services.length,0);
 receipt.checks.push({name:'denied directory renders chooser with retry, without opening a database',passed:true});
 const retry=page.getByRole('button',{name:'Retry project list',exact:true});
 // Let the automatic initial refresh settle while access is still denied.
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(button=>button.textContent==='Retry project list'&&!button.disabled));
 await fs.chmod(workspace,0o700);
 await retry.click();
 await page.getByText('No projects yet',{exact:true}).waitFor();
 assert.equal(await page.getByText(/Project folders could not be read/).count(),0);
 receipt.checks.push({name:'explicit retry recovers the real project list after access returns',passed:true});
 await fs.chmod(workspace,0);await page.reload();
 await page.getByText(/Project folders could not be read/).waitFor();
 const began=Date.now();await gracefulQuit(application,page);application=null;
 await assert.rejects(fs.access(path.join(fixture.userData,'desktop-service.json')),{code:'ENOENT'});
 const services=JSON.parse(await fs.readFile(path.join(fixture.userData,'backend/desktop-services.json'),'utf8'));
 assert.equal(services.services.length,0);assert.equal(services.database_operations.length,0);
 receipt.checks.push({name:'ordinary Quit after listing failure removes root ownership and leaves no project operations',passed:true,elapsed_ms:Date.now()-began});
 receipt.passed=true;
}
main().catch(error=>{receipt.failures.push(error.message);process.exitCode=1;}).finally(async()=>{
 if(workspace)await fs.chmod(workspace,0o700).catch(()=>{});
 if(application)try{await gracefulQuit(application,page);}catch(error){receipt.failures.push('Cleanup unconfirmed: '+error.message);}
 await fs.mkdir(path.dirname(resultPath),{recursive:true});await fs.writeFile(resultPath,JSON.stringify(receipt,null,2)+'\n');
 console.log(JSON.stringify(receipt));
});
