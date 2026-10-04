// Isolated browser regression: real components/profile, HTTP boundary fixtures only.
// Run from any cwd: node desktop/e2e/stable-content-inert.e2e.cjs
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../../workspace-app');
const profile = '11111111-1111-4111-8111-111111111111';
const oldId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const freshId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const annotations = {epoch_tags:[],cell_tags:[],revisions:{epoch:{[profile]:0},cell:{[profile]:0}},cell_epoch_count:1};
const fixture = `
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import StableContent from '/src/components/StableContent.jsx';
import AnnotationTags from '/src/components/AnnotationTags.jsx';
import {AnnotationProfileProvider} from '/src/annotationProfile.js';
const annotations=${JSON.stringify(annotations)};
function Fixture(){
 const [phase,setPhase]=useState('ready');
 const epoch={epoch_uuid:phase==='fresh'?'${freshId}':'${oldId}',cell_uuid:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',annotations};
 return <AnnotationProfileProvider projectId="owned-inert-fixture">
 <div style={{width:800,padding:30}}>
 {['loading','error','blocked','fresh'].map(p=><button key={p} onClick={()=>setPhase(p)}>Show {p}</button>)}
 <button id="before">Before content</button>
 <StableContent scope="fixture" data={epoch} loading={phase==='loading'} error={phase==='error'?'Fixture failure':null} blocked={phase==='blocked'}>
 <AnnotationTags epoch={epoch} revision={0} targetScope="epoch"/>
 </StableContent><button id="after">After content</button></div>
 </AnnotationProfileProvider>;
}
createRoot(document.getElementById('root')).render(<Fixture/>);
`;
(async()=>{
 let server,browser;
 const records=[],failures=[];
 try {
  const {createServer}=await import(pathToFileURL(path.join(root,'src/test-support/isolatedVite.js')));
  const {default:react}=await import(pathToFileURL(path.join(root,'node_modules/@vitejs/plugin-react/dist/index.js')));
  server=await createServer({root,configFile:false,logLevel:'error',plugins:[react(),{
   name:'owned-inert-fixture',resolveId(id){if(id==='/inert-fixture.jsx')return path.join(root,'inert-fixture.jsx');},
   load(id){if(id===path.join(root,'inert-fixture.jsx'))return fixture;},
   configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__fixture__')return next();res.setHeader('Content-Type','text/html');res.end('<div id="root"></div><script type="module" src="/inert-fixture.jsx"></script>');});}
  }],server:{host:'127.0.0.1',port:0,hmr:false}});
  await server.listen();
  const origin=`http://127.0.0.1:${server.httpServer.address().port}`;
  browser=await chromium.launch({executablePath:process.env.DISCO_CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--no-first-run','--no-default-browser-check']});
  console.log(JSON.stringify({node:process.version,chrome:browser.version()}));
  for(const phase of ['loading','error','blocked'])for(const gesture of ['pointer','keyboard']){
   const context=await browser.newContext();
   try{
    const writes=[],unexpected=[];
    await context.route('**/*',async route=>{
     const request=route.request(),url=new URL(request.url());
     if(url.origin!==origin){unexpected.push(url.href);return route.abort();}
     if(!url.pathname.startsWith('/api/'))return route.continue();
     let data;
     if(url.pathname==='/api/annotation-profiles'&&request.method()==='GET')data={profiles:[{profile_uuid:profile,display_name:'Fixture Author'}],selected_profile_uuid:profile};
     else if(url.pathname==='/api/annotations'&&request.method()==='POST'){writes.push(request.postDataJSON());data={changed:1};}
     else if(url.pathname==='/api/annotation-tags')data={tags:[]};
     else if(url.pathname.endsWith('/annotations')&&request.method()==='GET')data=annotations;
     else{unexpected.push(`${request.method()} ${url.pathname}`);return route.abort();}
     return route.fulfill({json:data});
    });
    const page=await context.newPage();
    await page.goto(`${origin}/__fixture__`);
    await page.getByRole('button',{name:'Fixture Author'}).waitFor();
    const input=page.locator('[role=combobox]');
    await input.fill('retained-draft');
    const node=await input.elementHandle();
    await page.getByRole('button',{name:`Show ${phase}`,exact:true}).click();
    const state=await node.evaluate(el=>({inert:el.closest('.stable-content-body').inert,attribute:el.closest('.stable-content-body').hasAttribute('inert'),disabled:el.disabled,same:el===document.querySelector('[role=combobox]')}));
    await page.evaluate(()=>{window.trusted=[];for(const type of ['click','keydown'])document.addEventListener(type,e=>window.trusted.push({type,key:e.key,trusted:e.isTrusted,inside:!!e.target.closest?.('.stable-content-body')}),true);});
    if(gesture==='pointer'){
     const box=await page.getByRole('button',{name:'Add epoch tag',includeHidden:true}).boundingBox();
     await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
    }else{
     await page.locator('#before').click();
     await page.keyboard.press('Tab');
     state.tabSkipped=await page.locator('#after').evaluate(el=>el===document.activeElement);
     const box=await input.boundingBox();
     await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
     await page.keyboard.press('Enter');
    }
    // Round-trip the browser task queue and allow the mocked fetch to settle.
    await page.waitForTimeout(150);
    const staleWrites=writes.slice(),events=await page.evaluate(()=>window.trusted);
    await page.getByRole('button',{name:'Show fresh',exact:true}).click();
    await input.fill('fresh-draft');
    const ready=await node.evaluate(el=>({same:el===document.querySelector('[role=combobox]'),inert:el.closest('.stable-content-body').inert,attribute:el.closest('.stable-content-body').hasAttribute('inert')}));
    await input.press('Enter');
    await page.waitForFunction(()=>document.querySelector('.annotation-result')?.textContent.includes('fresh-draft'));
    const record={phase,gesture,state,staleWrites,ready,writes,events,unexpected};records.push(record);
    try{
     assert.deepEqual(staleWrites,[],'trusted stale gestures must not reach the mutation boundary');
     assert.equal(state.same,true,'retained input identity');assert.equal(state.disabled,false,'wrapper barrier exercised with enabled input');
     assert.equal(state.inert,true,'waiting subtree must be natively inert');assert.equal(state.attribute,true,'waiting inert attribute');
     if(gesture==='keyboard')assert.equal(state.tabSkipped,true,'Tab skips the retained subtree');
     assert.ok(events.length&&events.every(e=>e.trusted),'real trusted browser input');
     assert.deepEqual(ready,{same:true,inert:false,attribute:false},'same input recovers when fresh');
     assert.equal(writes.length,1,'only the fresh recovery gesture writes');
     assert.equal(writes.at(-1).target_uuids[0],freshId,'fresh input saves against fresh epoch');
     assert.deepEqual(unexpected,[],'fixture is fully isolated');
    }catch(error){failures.push(`${phase}/${gesture}: ${error.message}`);}
   }finally{await context.close();}
  }
  console.log(JSON.stringify({records,failures},null,2));
  assert.deepEqual(failures,[]);
 }finally{await browser?.close();await server?.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
