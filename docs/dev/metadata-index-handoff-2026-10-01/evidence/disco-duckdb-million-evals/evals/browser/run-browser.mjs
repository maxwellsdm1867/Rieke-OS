import {createRequire} from 'node:module';
import {readFile,writeFile} from 'node:fs/promises';
import os from 'node:os';
import {performance as hostPerformance} from 'node:perf_hooks';
const require=createRequire(process.env.DISCO_NODE_PACKAGE || '/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/workspace-app/package.json');
const playwright=createRequire(process.env.DISCO_PLAYWRIGHT_PACKAGE || '/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/desktop/package.json')('playwright');
const {build,preview}=await import(require.resolve('vite'));
const {default:react}=await import(require.resolve('@vitejs/plugin-react'));
const config=JSON.parse(await readFile(process.argv[2],'utf8'));
if(!['sqlite','duckdb'].includes(config.engine))throw new Error('config.engine must identify the experimental SQL engine');
if(config.epochs!==1000000)throw new Error('This benchmark is specifically the one-million fixture');
const apiOrigin=process.argv[3],out=process.argv[4];
const root=process.env.DISCO_BROWSER_BUILD_ROOT;
if(!root)throw new Error('DISCO_BROWSER_BUILD_ROOT must point to a disposable exact-source browser shell');
const sourceManifest=JSON.parse(await readFile(`${root}/source-manifest.json`,'utf8'));
if(!sourceManifest.exact_source_snapshot_verified)throw new Error('Exact frontend source snapshot must be verified before timing');
await build({root,configFile:false,plugins:[react()],build:{outDir:'bench-dist',emptyOutDir:true},logLevel:'error'});
const server=await preview({root,configFile:false,plugins:[{name:'experiment-config',configurePreviewServer(s){s.middlewares.use('/bench-config',(req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(config));});}}],build:{outDir:'bench-dist'},preview:{host:'127.0.0.1',port:0,proxy:{'/api':{target:apiOrigin,changeOrigin:true,headers:{Origin:apiOrigin}}}},logLevel:'error'});
const url=`http://127.0.0.1:${server.httpServer.address().port}`;
const browser=await playwright.chromium.launch({executablePath:process.env.DISCO_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--no-first-run','--no-default-browser-check']});
 const report={measured_at:new Date().toISOString(),source_head:config.source_head,epochs:config.epochs,browser:await browser.version(),machine:{platform:os.platform(),arch:os.arch(),cpu:os.cpus()[0]?.model},engine:config.engine, fixture_scope:config.scope||'', experimental_api_bridge:true, scope:'Exact-source production-built React PagedTree/MetadataPanel mounted in a minimal experiment shell; experimental typed readmodel API bridge over localhost (not current production Flask/MySQL). Includes request, response parsing, React commit and two animation frames. Excludes full App startup, waveform reads, desktop packaging, and physical screen display. '+(config.scope||''),measurements:[],errors:[],correctness:[],api_pages:[]};
try{
 report.source_manifest=sourceManifest;
 const page=await browser.newPage({viewport:{width:1440,height:900}});page.setDefaultTimeout(30000);
 page.on('pageerror',e=>report.errors.push(e.message));
 const responseWork=[];
 page.on('response',r=>{if(!r.url().includes('/api/'))return;responseWork.push((async()=>{if(!r.ok()){report.errors.push(`${r.status()} ${r.url()}`);return;}const payload=await r.json();if(new URL(r.url()).pathname==='/api/tree-pages'){const request=r.request().postDataJSON();report.api_pages.push({request,response:payload});if(!/^[0-9a-f]{64}$/.test(payload.revision))throw new Error('Invalid tree revision');if(payload.total_epochs!==1000000)throw new Error('Million fixture membership changed');const rows=payload.kind==='epochs'?payload.epochs:payload.branches;if(rows.length>60||payload.total<rows.length||payload.has_more!==(payload.offset+payload.limit<payload.total))throw new Error('Invalid bounded page/count contract');if(payload.kind==='epochs'&&new Set(rows.map(x=>x.epoch_uuid)).size!==rows.length)throw new Error('Duplicate leaf IDs');if(JSON.stringify(payload.path)!==JSON.stringify(request.path))throw new Error('Returned path differs from request');report.correctness.push({name:'bounded_tree_response_contract',passed:true,path:payload.path,offset:payload.offset,total:payload.total});}else if(new URL(r.url()).pathname.startsWith('/api/epochs/')){if(payload.epoch_uuid!==new URL(r.url()).pathname.split('/').at(-1))throw new Error('Epoch detail identity mismatch');report.correctness.push({name:'epoch_detail_identity',passed:true,epoch_uuid:payload.epoch_uuid});}})().catch(e=>report.errors.push(e.stack)));});
 const requests=[];page.on('request',r=>{if(r.url().includes('/api/'))requests.push({url:r.url(),method:r.method(),body:r.postData()});});
 async function frames(){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
 async function measure(name,action,ready){const navigating=name.includes('initial_tree_load'),hostBegan=hostPerformance.now(),began=navigating?null:await page.evaluate(()=>performance.now());await action();await ready();await frames();const elapsed=navigating?hostPerformance.now()-hostBegan:await page.evaluate(t=>performance.now()-t,began);const resources=await page.evaluate(t=>performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')&&(t===null||r.startTime>=t)).map(r=>({path:new URL(r.name).pathname,duration_ms:r.duration,response_bytes:r.decodedBodySize})),began);report.measurements.push({name,sample_ms:elapsed,clock:navigating?'host navigation wall clock':'renderer performance clock',resources});console.log(JSON.stringify({epochs:config.epochs,name,sample_ms:elapsed,resources}));}
 await measure('component_initial_tree_load_production_bundle_cold',()=>page.goto(url),()=>page.waitForFunction(()=>document.querySelector('.ht-root > .ht-branch')));
 for(let i=0;i<Number(process.argv[5]||5);i++){
  await page.reload();await page.locator('.ht-root > .ht-branch').first().waitFor();await frames();
  const first=page.locator('.ht-root > .ht-branch').first();
  await measure('expand_cell_first_time',()=>first.locator(':scope > button').click(),()=>page.waitForFunction(()=>document.querySelector('.ht-root > .ht-branch > .ht-children > .ht-branch')));
  const block=first.locator(':scope > .ht-children > .ht-branch').first();
  await measure('expand_block_first_time',()=>block.locator(':scope > button').click(),()=>page.waitForFunction(()=>document.querySelector('.ht-root > .ht-branch > .ht-children > .ht-branch > .ht-children > .ht-leaf')));
  const leaf=block.locator('.ht-leaf > button').first();
  const id=await leaf.getAttribute('data-epoch-uuid');
  await Promise.all(responseWork);
  const leafPage=report.api_pages.filter(x=>x.response.kind==='epochs').at(-1)?.response;
  const renderedIds=await block.locator('.ht-leaf > button').evaluateAll(xs=>xs.map(x=>x.dataset.epochUuid));
  if(!leafPage||JSON.stringify(renderedIds)!==JSON.stringify(leafPage.epochs.map(x=>x.epoch_uuid)))throw new Error('Rendered leaf IDs/order differ from returned page');
  report.correctness.push({name:'rendered_leaf_identity_and_order',passed:true,ids:renderedIds});
  await measure('select_epoch_metadata',()=>leaf.click(),()=>page.waitForFunction(id=>document.querySelector('#detail-ready')?.dataset.epoch===id,id));
  const search=page.getByRole('textbox',{name:'Search focused epoch metadata'});
  await measure('search_selected_epoch_metadata',()=>search.fill('contrast'),()=>page.waitForFunction(()=>[...document.querySelectorAll('.metadata-panel-note')].some(e=>/matching field/.test(e.textContent))));
  await search.fill('');
  await measure('collapse_cell_cached',()=>first.locator(':scope > button').click(),()=>page.waitForFunction(()=>document.querySelector('.ht-root > .ht-branch > button')?.getAttribute('aria-expanded')==='false'));
  await measure('reopen_cell_cached',()=>first.locator(':scope > button').click(),()=>page.waitForFunction(()=>document.querySelector('.ht-root > .ht-branch > .ht-children > .ht-branch')));
  const scroll=page.locator('.ht-scroll');
  await measure('scroll_loaded_tree',()=>scroll.evaluate(el=>{el.scrollTop=el.scrollHeight;}),async()=>{});
  const next=page.getByRole('button',{name:'Next Cell page',exact:true});
  if(await next.isVisible()){
   const before=await first.innerText();
   await measure('next_cell_page_60',()=>next.click(),()=>page.waitForFunction(before=>document.querySelector('.ht-root > .ht-branch')?.innerText!==before,before));
  }
 }
 // Historical actions above reset client state after native API measurements.
 // These additional cells have not been expanded by the native first-cell probe.
 // They expose first use of a different branch, with identical source actions.
 for(let i=0;i<Number(process.argv[5]||5);i++){
  await page.reload();await page.locator('.ht-root > .ht-branch').first().waitFor();await frames();
  const cell=page.locator('.ht-root > .ht-branch').nth(i+1);
  await measure('expand_disjoint_cell_first_use',()=>cell.locator(':scope > button').click(),()=>page.waitForFunction(index=>document.querySelectorAll('.ht-root > .ht-branch')[index]?.querySelector(':scope > .ht-children > .ht-branch'),i+1));
  const block=cell.locator(':scope > .ht-children > .ht-branch').first();
  await measure('expand_disjoint_block_first_use',()=>block.locator(':scope > button').click(),()=>page.waitForFunction(index=>document.querySelectorAll('.ht-root > .ht-branch')[index]?.querySelector(':scope > .ht-children > .ht-branch > .ht-children > .ht-leaf'),i+1));
 }
 await Promise.all(responseWork);
 report.backend_oracle=await (await fetch(`${apiOrigin}/eval/checks`)).json();
 if(!report.backend_oracle.passed||!report.backend_oracle.checks.length)report.errors.push('Independent backend fixture oracle did not pass');
 report.request_count=requests.length;report.requests=requests;
 const required=['select_epoch_metadata','search_selected_epoch_metadata','reopen_cell_cached','scroll_loaded_tree','expand_cell_first_time','expand_block_first_time','next_cell_page_60'];
 report.required_actions=required;
 for(const action of required)if(report.measurements.filter(x=>x.name===action).length!==Number(process.argv[5]||5))report.errors.push(`Missing required repetitions: ${action}`);
 report.passed=report.errors.length===0;
 if(!report.passed)throw new Error('Browser correctness or coverage failed');
 report.summary=Object.entries(Object.groupBy(report.measurements,r=>r.name)).map(([name,rows])=>{const samples=rows.map(r=>r.sample_ms).sort((a,b)=>a-b);const chronological=rows.map(r=>r.sample_ms);const warm=chronological.slice(1).sort((a,b)=>a-b);const median=xs=>xs.length?xs.length%2?xs[Math.floor(xs.length/2)]:(xs[xs.length/2-1]+xs[xs.length/2])/2:null;return {name,n:samples.length,median_ms:median(samples),first_ms:chronological[0],warm_median_ms:median(warm),min_ms:samples[0],max_ms:samples.at(-1),samples_ms:chronological};});
 await page.screenshot({path:out.replace(/\.json$/,'.png'),fullPage:true});
}catch(error){report.errors.push(error.stack);throw error;}finally{await writeFile(out,JSON.stringify(report,null,2)+'\n');await browser.close();await new Promise(resolve=>server.httpServer.close(resolve));}
