'use strict';
// Normal executable launch; attach automation only AFTER the first-paint marker.
const fs=require('node:fs/promises'),path=require('node:path'),net=require('node:net'),os=require('node:os');
const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
const {createFixture,run}=require('./helpers.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
(async()=>{
 const fixture=await createFixture({reuse:false}),runtime=path.join(fixture.bundle,'Contents/Resources/runtime');
 const manifest=JSON.parse(await fs.readFile(path.join(runtime,'runtime-manifest.json')));
 await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-startup-projects.py'),path.join(runtime,'application'),fixture.home,runtime]);
 const projects=JSON.parse(await fs.readFile(path.join(fixture.home,'projects.json')));
 const cases=[{label:'empty',project:projects.small,epochs:0},{label:'sparse_200gb_10000_files',project:projects.large,failed:true}];
 if(process.argv[2]){
  const dir=await fs.realpath(process.argv[2]),parent=path.dirname(dir),tmp=await fs.realpath(os.tmpdir());
  assert.ok(parent.startsWith(tmp+path.sep)&&path.basename(parent).startsWith('rieke-desktop-smoke-')&&path.basename(dir)==='project');
  assert.equal((await fs.stat(dir)).uid,process.getuid());
  assert.equal(JSON.parse(await fs.readFile(path.join(dir,'database/native-owner.json'))).clean_shutdown,true);
  const p=JSON.parse(await fs.readFile(path.join(dir,'project.json')));
  cases.push({label:'populated_1915_epochs',project:{uuid:p.project_uuid,path:dir,name:p.display_name||p.name},epochs:1915});
 }
 const samples=[];
 for(let sample=0;sample<5;sample++)for(const item of cases){
  const project=item.project;
  await fs.writeFile(path.join(fixture.userData,'startup-session.json'),JSON.stringify({format:'disco-startup-session',version:1,compatibility:manifest.application_version+':view-v1',mode:'resume',projectId:project.uuid,projectPath:project.path,view:'overview'}));
  const debugPort=await port(),began=performance.now();
  const child=spawn(fixture.executable,[`--user-data-dir=${fixture.userData}`,`--remote-debugging-port=${debugPort}`],{env:{...process.env,HOME:fixture.home,TMPDIR:fixture.root,XDG_CONFIG_HOME:fixture.userData,DISCO_STARTUP_DIAGNOSTIC:'1'},stdio:['ignore','pipe','ignore']});
  const exited=new Promise(resolve=>child.once('exit',code=>resolve(code)));
  let browser,page,quitRequested=false;
  const painted=new Promise((resolve,reject)=>{
   let pending='';const timer=setTimeout(()=>reject(Error('No native shell paint marker')),20000);
   child.once('error',error=>{clearTimeout(timer);reject(error);});
   child.once('exit',()=>{clearTimeout(timer);reject(Error('App exited before shell paint'));});
   child.stdout.on('data',bytes=>{pending+=bytes.toString();let end;while((end=pending.indexOf('\n'))>=0){const line=pending.slice(0,end);pending=pending.slice(end+1);if(!line.startsWith('DISCO_SHELL_PAINTED='))continue;
    const marker=JSON.parse(line.slice('DISCO_SHELL_PAINTED='.length));assert.equal(marker.pid,child.pid);assert.equal(marker.kind,'project');clearTimeout(timer);resolve({shell_ms:performance.now()-began,marker});}});
  });
  async function attach(){if(browser)return;browser=await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);page=browser.contexts()[0].pages()[0];}
  async function quit(){await attach();quitRequested=true;await page.evaluate(()=>{void window.riekeDesktop.quit();});let timer;try{assert.equal(await Promise.race([exited,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Native Quit did not finish')),45000);})]),0);}finally{clearTimeout(timer);}}
  try{
   const observation=await painted;await attach();
   assert.equal(await page.getByRole('button',{name:project.name+', current project',exact:true}).isVisible(),true);
   let status;const deadline=Date.now()+120000;
   do{status=await page.evaluate(()=>fetch('/api/project/data-status').then(r=>r.json()));if(['ready','failed'].includes(status.status))break;await delay(100);}while(Date.now()<deadline);
   assert.equal(status.status,item.failed?'failed':'ready');
   if(!item.failed){const overview=await page.evaluate(()=>fetch('/api/overview').then(r=>r.json()));assert.equal(overview.counts.epochs,item.epochs);}
   samples.push({sample,fixture:item.label,shell_ms:observation.shell_ms,data_terminal_ms:performance.now()-began,data_status:status.status});console.log(JSON.stringify(samples.at(-1)));
   await quit();
   if(!item.failed)assert.equal(JSON.parse(await fs.readFile(path.join(project.path,'database/native-owner.json'))).clean_shutdown,true);
  }finally{if(child.exitCode===null&&!quitRequested)await quit();if(browser)await browser.close();}
 }
 await verifyResources(runtime,manifest.resources);
 const receipt={format:'disco-native-startup-timing',version:1,fixture:fixture.root,source_commit:manifest.source_commit,source_dirty:manifest.source_dirty,application_version:manifest.application_version,method:'Normal executable spawn. No Node debugger. No CDP client attaches until main reports an enabled current-project button observed after animation frames following document load. Parent monotonic elapsed time includes spawn and marker-delivery overhead. Five fresh processes per fixture, interleaved; OS caches uncontrolled. Data readiness measured separately after observer attachment.',samples,shell_target_ms:2000,shell_target_met:samples.every(x=>x.shell_ms<2000),packaged_resources_unchanged:true,clean_shutdown:true};
 const output=path.resolve(__dirname,'../../benchmarks/results/native-startup-'+manifest.source_commit.slice(0,7));await fs.mkdir(output,{recursive:true});
 const file=path.join(output,'startup.json');await fs.writeFile(file,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(file);assert.equal(receipt.shell_target_met,true,'Every native project shell must paint within two seconds');
})().catch(error=>{console.error(error);process.exitCode=1;});
