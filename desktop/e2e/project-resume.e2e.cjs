'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {createFixture,launch,gracefulQuit,run}=require('./helpers.cjs');
const {verifyResources}=require('../updater-validation.cjs');
const output=path.resolve(__dirname,'../../docs/dev/startup-boundary');
(async()=>{
 const fixture=await createFixture({reuse:false});
 const runtime=path.join(fixture.bundle,'Contents/Resources/runtime');
 const manifest=JSON.parse(await fs.readFile(path.join(runtime,'runtime-manifest.json')));
 await fs.mkdir(output,{recursive:true});
 await run(path.join(runtime,'python/bin/python3.11'),['-B',path.join(__dirname,'seed-startup-projects.py'),path.join(runtime,'application'),fixture.home,runtime]);
 const projects=JSON.parse(await fs.readFile(path.join(fixture.home,'projects.json')));
 let application,page;const errors=[],timings=[];
 async function start(){
  const time=performance.now();({application,page}=await launch(fixture));
  page.on('pageerror',error=>errors.push(error.message));return time;
 }
 async function quit(){await gracefulQuit(application,page);application=null;}
 async function open(project){
  const result=await page.evaluate(async directory=>{
   const response=await fetch('/api/projects/open-folder',{method:'POST',headers:{'Content-Type':'application/json','X-Workspace-Request':'1'},body:JSON.stringify({directory})});
   return {status:response.status,body:await response.json()};
  },project.path);assert.equal(result.status,200,JSON.stringify(result.body));
  await page.evaluate(url=>window.location.assign(url),result.body.url);
 }
 async function profile(){const close=page.getByRole('button',{name:'Close tag author',exact:true});if(await close.isVisible())await close.click();}
 async function unmount(project){
  await profile();await page.getByRole('button',{name:'Unmount current project',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Unmount project',exact:true});
  await dialog.getByRole('button',{name:'Unmount project',exact:true}).click();
  await page.locator('.project-launcher').waitFor({timeout:30000});
  const inventory=await page.evaluate(()=>fetch('/api/projects').then(r=>r.json()));
  assert.equal(inventory.projects.some(p=>p.path===project.path),false);
  assert.ok(await fs.stat(path.join(project.path,'project.json')));
 }
 try{
  const first=await start();await page.locator('.project-launcher').waitFor({timeout:20000});
  timings.push({milestone:'first_launch_chooser_ms',ms:performance.now()-first});
  await open(projects.small);
  await page.getByRole('region',{name:'Project infographic'}).waitFor({timeout:120000});
  await profile();await page.getByRole('button',{name:'Data stores',exact:true}).click();
  await page.getByRole('heading',{name:'Data stores',exact:true}).waitFor();await quit();
  const preference=JSON.parse(await fs.readFile(path.join(fixture.userData,'startup-session.json')));
  assert.equal(preference.projectPath,projects.small.path);assert.equal(preference.view,'stores');
  for(let sample=0;sample<5;sample++){
   const began=await start();let chooserSeen=false;
   await page.exposeFunction('recordChooser',()=>{chooserSeen=true;});
   await page.addInitScript(()=>new MutationObserver(()=>{if(document.querySelector('.project-launcher'))window.recordChooser();}).observe(document,{childList:true,subtree:true}));
   await page.getByRole('button',{name:projects.small.name+', current project',exact:true}).waitFor({timeout:20000});
   timings.push({sample,milestone:'last_project_shell_ms',ms:performance.now()-began});console.log(JSON.stringify(timings.at(-1)));
   await page.getByRole('heading',{name:'Data stores',exact:true}).waitFor({timeout:120000});
   timings.push({sample,milestone:'restored_data_view_ms',ms:performance.now()-began});
   assert.equal(chooserSeen,false,'Normal relaunch must skip the chooser');
   await profile();if(sample<4)await quit();
  }
  const close=performance.now();await unmount(projects.small);
  timings.push({milestone:'unmount_to_chooser_ms',ms:performance.now()-close});
  assert.equal(JSON.parse(await fs.readFile(path.join(projects.small.path,'database/native-owner.json'))).clean_shutdown,true);
  await quit();await start();await page.locator('.project-launcher').waitFor({timeout:20000});
  const large=performance.now();await open(projects.large);
  await page.getByRole('button',{name:projects.large.name+', current project',exact:true}).waitFor({timeout:20000});
  timings.push({milestone:'sparse_200gb_project_shell_ms',ms:performance.now()-large});
  await page.getByRole('alert').filter({hasText:'Project data could not open'}).waitFor({timeout:20000});
  await quit();
  for(let sample=0;sample<5;sample++){
   const began=await start();
   await page.getByRole('button',{name:projects.large.name+', current project',exact:true}).waitFor({timeout:20000});
   timings.push({sample,milestone:'sparse_200gb_last_project_shell_ms',ms:performance.now()-began});console.log(JSON.stringify(timings.at(-1)));
   await page.getByRole('alert').filter({hasText:'Project data could not open'}).waitFor({timeout:20000});
   if(sample<4)await quit();
  }
  await unmount(projects.large);await quit();
  assert.deepEqual(errors,[]);await verifyResources(runtime,manifest.resources);
  const receipt={fixture:fixture.root,application_version:manifest.application_version,source_commit:manifest.source_commit,source_dirty:manifest.source_dirty,method:'Actual packaged Electron, isolated HOME/profile; five fresh-process restores each of an empty native project and a sparse 200 GB / 10,000-file project, OS caches uncontrolled; sparse 200 GB invalid database is a failure-isolation control, not a populated database benchmark. Timings include Playwright overhead.',timings,last_project_resumed:true,last_view_restored:true,chooser_skipped:true,loaded_project_unmounted_cleanly:true,failed_data_project_unmounted:true,unmounted_project_not_reopened:true,page_errors:errors};
  receipt.shell_target_ms=2000;
  receipt.shell_target_met=timings.filter(x=>['last_project_shell_ms','sparse_200gb_last_project_shell_ms'].includes(x.milestone)).every(x=>x.ms<receipt.shell_target_ms);
  await fs.writeFile(path.join(output,'project-resume-packaged.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt,null,2));
  assert.equal(receipt.shell_target_met,true,'Every measured restored shell must be usable within two seconds');
 }finally{if(application){await page.screenshot({path:path.join(output,'resume-failure.png')}).catch(()=>{});console.error(await page.locator('body').innerText().catch(()=>''));await quit().catch(error=>console.error(error.message));}}
})().catch(error=>{console.error(error);process.exitCode=1;});
