// Visual source-parity control only. Synthetic HTTP responses are confined to
// this test's isolated browser; production source and native E2E never import them.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..'),workspace=path.join(root,'workspace-app');
const project='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const profile={profile_uuid:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',name:'UI fixture',selected:true};
const fixtures={
 '/projects':{launcher:false,current_project_uuid:project,projects:[{uuid:project,path:'/fixture/project',name:'Appearance sample',current:true,available:true}]},
 '/overview':{project:{project_uuid:project,display_name:'Appearance sample'},counts:{cells:0,epochs:0,duration_seconds:0},cells:[],protocols:[],sources:[],events:[]},
 '/annotation-profiles':{profiles:[profile],selected_profile_uuid:profile.profile_uuid},
 '/protocol-suggestions':{suggestions:[],approved_history:[]},'/jobs':{jobs:[]},
 '/data-stores':{data_stores:[]},'/project-preferences':{format:'rieke-project-preferences',version:1,project_uuid:project,state:{},revisions:{}},
 '/metadata/status':{},'/annotations/scan':{changed:false},'/app/version':{version:'0.1.5'},
 '/app/updates/check':{state:'Current',installed:'0.1.5'},'/events':{events:[]},'/exports':{exports:[]},
};
(async()=>{
 const {createServer}=await import(pathToFileURL(require.resolve('vite',{paths:[workspace]})).href);
 const server=await createServer({root:workspace,server:{host:'127.0.0.1',port:0,strictPort:true}});
 await server.listen();
 const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
 const chrome=process.env.DISCO_CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
 let browser;
 const output=process.env.DISCO_UI_PARITY_OUTPUT;
 const receipt={kind:'production-live-source-visual-fixture',scientific_e2e:false,native_measurement:false,production_mock_import:false,checks:[],unexpected_requests:[],screenshots:[]};
 try{
  browser=await chromium.launch({...(fs.existsSync(chrome)?{executablePath:chrome}:{}),headless:true,args:['--no-first-run','--no-default-browser-check']});
  const context=await browser.newContext({viewport:{width:1500,height:1050},colorScheme:'light'}),page=await context.newPage();
  const failures=[];page.on('pageerror',error=>failures.push(error.message));
  let saved={theme:'light',icon:'disco'},writes=0,failNext=false;
  await page.route('**/api/**',async route=>{
   const req=route.request(),url=new URL(req.url()),key=url.pathname.slice(4);
   let value,status=200;
   if(key==='/app/appearance'){
    if(req.method()==='POST'){
     if(failNext){failNext=false;status=507;value={error:'Fixture preference write failed'};}
     else {const {theme}=req.postDataJSON();saved={theme,icon:theme==='fred'?'rieke':'disco'};writes++;value=saved;}
    }else value=saved;
   }else if(Object.hasOwn(fixtures,key))value=fixtures[key];
   else {receipt.unexpected_requests.push(key);status=501;value={error:'UI fixture has no response for this endpoint'};}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  });
  await page.goto(origin);
  await page.getByRole('heading',{name:'Appearance sample',exact:true}).waitFor();
  await page.getByRole('button',{name:'Data stores',exact:true}).click();
  await page.getByRole('heading',{name:'Data stores',exact:true}).waitFor();
  const palette=page.locator('.rail .appearance-rail-button');
  await palette.waitFor({state:'visible'});
  const box=await palette.boundingBox(),avatar=await page.locator('.rail .avatar').boundingBox();
  assert.ok(box&&avatar&&box.y<avatar.y,'Palette button must sit above the profile icon');
  await palette.click();
  const dialog=page.getByRole('dialog',{name:'Appearance',exact:true});
  await dialog.waitFor();assert.equal(await dialog.getByRole('radio').count(),4);
  const choose=async name=>{
   const radio=page.getByRole('radio',{name:new RegExp(`^${name}`)});
   await dialog.locator('label').filter({has:radio}).click();
   await page.waitForFunction(theme=>document.documentElement.dataset.appearance===theme,name.toLowerCase());
   await page.getByText('Applies immediately. Remembered across projects.',{exact:true}).waitFor();
  };
  const capture=async name=>{
   if(!output)return;
   fs.mkdirSync(output,{recursive:true});const file=path.join(output,`${name}.png`);await page.screenshot({path:file});receipt.screenshots.push(path.basename(file));
  };
  await choose('Dark');
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');
  const colors=await page.evaluate(()=>{
   const style=getComputedStyle(document.documentElement),main=getComputedStyle(document.querySelector('.main-shell'));
   return {background:style.getPropertyValue('--background').trim(),ink:style.getPropertyValue('--ink').trim(),accent:style.getPropertyValue('--accent').trim(),main:main.backgroundColor};
  });
  receipt.dark_colors=colors;await capture('dark-theme-picker');
  await page.getByRole('button',{name:'Close appearance',exact:true}).click();
  await capture('dark-data-stores');
  for(const name of ['Current','Archived','All'])assert.equal(await page.getByRole('button',{name:new RegExp(`^${name}\\b`)}).count(),1);
  for(const name of ['Open H5 folder','Check sources','Import H5s'])await page.getByRole('button',{name,exact:true}).waitFor();
  await page.getByRole('button',{name:'App Updates',exact:true}).waitFor();
  receipt.checks.push('lower-left palette above profile','four rendered theme choices','dark data-store controls and App Updates');
  await page.reload();await palette.waitFor();
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  receipt.checks.push('saved theme survives App reload');
  await palette.click();await choose('Fred');
  assert.equal(await page.locator('link[rel="icon"]').getAttribute('href'),'/rieke-emblem.png');
  await capture('fred-theme-picker');await choose('Light');
  assert.equal(await page.locator('link[rel="icon"]').getAttribute('href'),'/disco-icon.png');
  await choose('System');
  await page.emulateMedia({colorScheme:'dark'});await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page.emulateMedia({colorScheme:'light'});await page.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  receipt.checks.push('Fred emblem and Light disco icon','System reacts to device scheme changes');
  await dialog.getByRole('radio',{name:/^System/}).focus();
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(()=>document.documentElement.dataset.appearance==='light');
  await page.getByText('Applies immediately. Remembered across projects.',{exact:true}).waitFor();
  receipt.checks.push('theme cards support radio keyboard navigation');failNext=true;
  await dialog.locator('label').filter({has:page.getByRole('radio',{name:/^Dark/})}).click();
  await page.getByText('Your previous appearance is restored. The change was not saved.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');assert.equal(saved.theme,'light');
  receipt.checks.push('failed save restores prior theme');
  assert.deepEqual(failures,[]);assert.deepEqual(receipt.unexpected_requests,[]);
  receipt.status='passed';receipt.preference_writes=writes;
  await context.close();
 }finally{
  if(browser)await browser.close();await server.close();
  if(output){fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');}
 }
 console.log(JSON.stringify(receipt));
})().catch(error=>{console.error(error);process.exitCode=1;});
