/** Full product App navigation against the owned workflow service.
 * This is a separate diagnostic, not a replacement for the fixed workflow suite.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {attachLedger} from '../navigation-probe.mjs';

export function options(argv){
  const result={samples:3,expect_retained:false};
  for(let i=0;i<argv.length;i+=2){
    if(!argv[i]?.startsWith('--')||argv[i+1]===undefined)throw Error('Expected --key value');
    result[argv[i].slice(2).replaceAll('-','_')]=argv[i+1];
  }
  for(const key of ['source_root','server_json','output'])if(!result[key])throw Error(`Missing ${key}`);
  result.samples=Number(result.samples);
  assert.ok(Number.isInteger(result.samples)&&result.samples>=1&&result.samples<=5);
  result.expect_retained=result.expect_retained===true||result.expect_retained==='true';
  return result;
}

function installProbe(){
  localStorage.setItem('rieke.undo.enabled','false');
  const original=window.fetch.bind(window);
  window.__retention={requests:[],action:null,nodes:{}};
  window.fetch=async(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(!url.pathname.startsWith('/api/'))return original(input,options);
    const w=window.__retention,row={action:w.action,path:url.pathname+url.search,
      method:options.method||'GET',started:performance.now()};
    w.requests.push(row);
    const headers=new Headers(options.headers);
    if(w.action)headers.set('X-Benchmark-Action',w.action);
    try{
      const response=await original(input,{...options,headers});
      row.status=response.status;row.request_id=response.headers.get('X-Benchmark-Request-Id');
      const json=response.json.bind(response);
      response.json=async()=>{try{return row.result=await json();}finally{row.ended=performance.now();}};
      return response;
    }catch(error){row.error=String(error);row.ended=performance.now();throw error;}
  };
  window.riekeDesktop={loadDraft:projectId=>window.__loadDraft(projectId),
    saveDraft:payload=>window.__saveDraft(payload),onPrepareClose:()=>()=>{},
    applyAppIcon:async()=>({applied:true}),status:async()=>({state:'Running'}),
    onStatus:()=>()=>{},projectVisibility:async()=>({visible:true}),onProjectVisibility:()=>()=>{}};
}

async function quiet(page){
  await page.waitForFunction(()=>window.__retention.requests.every(r=>r.ended!==undefined),null,{timeout:15000});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
}

export async function run(config){
  const root=path.resolve(config.source_root),workspace=path.join(root,'workspace-app');
  const output=path.resolve(config.output);await fs.mkdir(output,{recursive:true});
  const meta=JSON.parse(await fs.readFile(config.server_json,'utf8'));
  assert.ok(Number.isInteger(meta.port)&&meta.port>0&&meta.epochs===1000);
  const require=createRequire(path.join(root,'desktop/package.json'));
  const {chromium}=require('playwright');
  const {DraftStore}=require(path.join(root,'desktop/drafts/draft-store.cjs'));
  const {createServer}=await import(pathToFileURL(path.join(workspace,'src/test-support/isolatedVite.js')));
  const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
  const receipt={format:'disco-full-app-retention-browser-v1',status:'running',actions:[],failures:[],cleanup:{}};
  let server,browser,context,page,ledger;
  try{
    const entry=path.join(workspace,'__retention_owned__.jsx');
    server=await createServer({root:workspace,configFile:false,logLevel:'error',plugins:[react(),{
      name:'owned-full-app-retention',resolveId(id){if(id==='/__retention_owned__.jsx')return entry;},
      load(id){if(id===entry)return "import React from 'react';import{createRoot}from'react-dom/client';import App from'/src/App.jsx';import'/src/styles.css';import'/src/themes.css';createRoot(document.getElementById('root')).render(<App/>);";},
      configureServer(s){s.middlewares.use((req,res,next)=>{
        if(req.url==='/__retention__'){res.setHeader('Content-Type','text/html');res.end('<div id="root"></div><script type="module" src="/__retention_owned__.jsx"></script>');return;}
        next();
      });},
    }],server:{host:'127.0.0.1',port:0,hmr:false,proxy:{'/api':{target:`http://127.0.0.1:${meta.port}`,changeOrigin:true,configure(proxy){proxy.on('proxyReq',req=>req.removeHeader('origin'));}}}}});
    await server.listen();
    browser=await chromium.launch({headless:true,...(config.browser_executable?{executablePath:config.browser_executable}:{}),args:['--no-first-run','--no-default-browser-check']});
    receipt.environment={node:process.version,browser:browser.version(),viewport:{width:1500,height:1100},runtime:'vite-react-development',headless:true};
    for(let sample=0;sample<config.samples;sample++){
      context=await browser.newContext({viewport:receipt.environment.viewport});page=await context.newPage();
      const drafts=new DraftStore(path.join(output,`drafts-${sample}`));
      await page.exposeFunction('__loadDraft',id=>{assert.equal(id,meta.project);return drafts.load(id);});
      await page.exposeFunction('__saveDraft',payload=>{assert.equal(payload.projectId,meta.project);return drafts.save(payload);});
      await page.addInitScript(installProbe);
      const errors=[];page.on('pageerror',error=>{errors.push(error.message);console.error('Browser error:',error.message);});
      let holdActivation=false,releaseActivation;
      const registry=()=>({current_project_uuid:meta.project,projects:[{uuid:meta.project,name:'Owned retention fixture',path:meta.project_path,current:true,available:true}],project_data:{status:holdActivation?'unloaded':'ready'}});
      await page.route('**/api/projects',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(registry())}));
      await page.route('**/api/project/activate',async route=>{await new Promise(resolve=>{releaseActivation=resolve;});await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'ready'})});});
      ledger=attachLedger(page,`retention-${sample}`);
      await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__retention__`);
      await page.getByRole('region',{name:'Project infographic',exact:true}).waitFor({timeout:30000});
      await page.locator(`[data-protocol-shortcut="${meta.protocol}"]`).getByRole('button').first().click();
      await page.getByRole('tab',{name:'Inspect',exact:true}).click();
      await page.getByRole('button',{name:'Edit Tree',exact:true}).waitFor({timeout:15000});
      await page.locator('.cell-tree-date').first().evaluate(el=>{el.open=true;});
      await page.locator('.cell-tree-cell').first().evaluate(el=>{el.open=true;});
      const epochName=`Inspect ${meta.date_label} · ${meta.cell_label} epoch 1`;
      await page.getByRole('button',{name:epochName,exact:true}).waitFor();await quiet(page);
      await page.getByRole('button',{name:epochName,exact:true}).click();
      await page.waitForFunction(expected=>{
        const response=[...window.__retention.requests].reverse().find(r=>r.result?.epoch_uuid===expected.epoch_uuid&&r.result?.stream_uuid===expected.stream_uuid&&Array.isArray(r.result?.values))?.result;
        return response?.start===0&&response.count===10000&&response.values[0]===0&&response.values.at(-1)===9999&&document.querySelector('.tv-base')&&!document.querySelector('.tv-status');
      },meta.trace_expected,{timeout:15000});
      await page.getByRole('button',{name:'Sample',exact:true}).click();
      await page.getByRole('spinbutton',{name:'Start sample',exact:true}).fill('100');
      await page.getByRole('spinbutton',{name:'Sample count',exact:true}).fill('1000');
      await page.locator('.tv-window-fields').getByRole('button',{name:'Apply',exact:true}).click();
      // Current trace presentation may crop the already loaded Whole response
      // locally. Do not manufacture a requirement for a bounded HTTP reread.
      await page.getByRole('spinbutton',{name:'Exact sample index for cursor',exact:true}).fill('150');
      await page.waitForFunction(()=>document.querySelector('[aria-label="Recorded sample index"]')?.textContent==='150'&&document.querySelector('[aria-label="Recorded response and scientific units"]')?.textContent.includes('150')&&!document.querySelector('.tv-status,.tv-previous-trace'),null,{timeout:15000});await quiet(page);
      const expectedScroll=await page.locator('.epoch-inspector-mode .tree-scroll').evaluate(el=>{el.scrollTop=120;el.dispatchEvent(new Event('scroll'));return el.scrollTop;});
      assert.ok(expectedScroll>0,'Owned fixture must exercise nonzero list scroll');await quiet(page);
      await page.evaluate(()=>{window.__retention.nodes.inspect=document.querySelector('.epoch-inspector-mode');window.__retention.nodes.trace=document.querySelector('.tv-base');});
      async function measure(id,locator){
        await locator.evaluate((el,action)=>{window.__retention.action=action;window.__retention.intent=performance.now();el.click();},`${sample}-${id}`);
        await page.waitForFunction(name=>{
          const visible=el=>!!el&&el.getClientRects().length>0&&!el.closest('[hidden],[inert]');
          const view=[...document.querySelectorAll('.epoch-inspector-mode')].find(visible);
          const button=[...document.querySelectorAll('button')].find(el=>el.getAttribute('aria-label')===name&&visible(el));
          return !!view&&!!button&&!button.disabled&&view.querySelector('[aria-label="Start sample"]')?.value==='100'&&view.querySelector('[aria-label="Sample count"]')?.value==='1000'&&view.querySelector('.tv-base')&&!view.querySelector('.tv-status');
        },epochName,{timeout:15000});
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const observed=await page.evaluate(()=>{
          const w=window.__retention,view=[...document.querySelectorAll('.epoch-inspector-mode')].find(el=>el.getClientRects().length&&!el.closest('[hidden],[inert]'));
          return {total_ms:performance.now()-w.intent,node_retained:view===w.nodes.inspect,
            trace_node_retained:view.querySelector('.tv-base')===w.nodes.trace,
            trace_window:{start:Number(view.querySelector('[aria-label="Start sample"]').value),count:Number(view.querySelector('[aria-label="Sample count"]').value)},
            trace_cursor:view.querySelector('[aria-label="Recorded sample index"]')?.textContent,
            list_scroll_top:view.querySelector('.tree-scroll')?.scrollTop,
            expanded_dates:[...view.querySelectorAll('.cell-tree-date')].filter(el=>el.open).length,
            expanded_cells:[...view.querySelectorAll('.cell-tree-cell')].filter(el=>el.open).length};
        });
        await quiet(page);
        const requests=await page.evaluate(()=>window.__retention.requests.filter(r=>r.action===window.__retention.action).map(({result,...row})=>row));
        const result={sample,id,...observed,requests,passed:false};receipt.actions.push(result);
        console.log(JSON.stringify({...result,passed:undefined,status:'observed'}));
        assert.ok(observed.expanded_dates>0&&observed.expanded_cells>0,'Expanded fixture branch must restore');
        assert.ok(requests.every(r=>r.status>=200&&r.status<300),'Return request must succeed');
        if(config.expect_retained){
          assert.equal(observed.node_retained,true,'Live Inspector DOM must survive leaving its view');
          assert.equal(observed.trace_node_retained,true,'Live trace canvas must survive leaving its view');
          assert.ok(Math.abs(observed.list_scroll_top-expectedScroll)<=1,'Retained list scroll must not jump');
          assert.equal(requests.some(r=>/^\/api\/epochs\/[^/]+\/trace(?:\?|$)/.test(r.path)),false,'Unchanged retained trace must not reread raw samples');
          assert.equal(requests.some(r=>r.path==='/api/overview'||/^\/api\/protocols\/[^/]+\/overview(?:\?|$)/.test(r.path)),false,'Unchanged retained return must not rebuild canonical summaries');
          assert.equal(requests.some(r=>r.path==='/api/metadata/fields'),false,'Completed field catalog must survive leaving its view');
        }
        result.passed=true;
        console.log(JSON.stringify({sample,id,status:'passed'}));
        await page.evaluate(()=>{window.__retention.action=null;});
      }
      await page.getByRole('button',{name:'Project overview',exact:true}).click();
      await page.getByRole('region',{name:'Project infographic',exact:true}).waitFor();await quiet(page);
      await measure('protocol.return-via-history',page.getByRole('button',{name:'Back to previous workspace',exact:true}));
      // Baseline may remount; capture this visit before the independent tab case.
      await page.evaluate(()=>{window.__retention.nodes.inspect=document.querySelector('.epoch-inspector-mode');window.__retention.nodes.trace=document.querySelector('.tv-base');});
      await page.getByRole('tab',{name:'Overview',exact:true}).click();await quiet(page);
      await measure('inspector.return-via-tab',page.getByRole('tab',{name:'Inspect',exact:true}));
      await page.evaluate(async()=>{const {flushDesktopDrafts}=await import('/src/desktopLifecycle.js');await flushDesktopDrafts();});
      const saved=await drafts.load(meta.project);assert.equal(saved.projectId,meta.project);assert.equal(saved.value.route.protocol,meta.protocol);
      receipt.actions.push({sample,id:'disk.snapshot',project_id:saved.projectId,route:saved.value.route,bytes:Buffer.byteLength(JSON.stringify(saved))});
      // Finish all identical warm samples before the separate cold check. A
      // known baseline restore failure must remain an overall failed receipt.
      if(sample===config.samples-1){
      for(const id of ['protocol.return-via-history','inspector.return-via-tab']){
        const actions=receipt.actions.filter(action=>action.id===id);
        assert.equal(actions.length,config.samples);assert.ok(actions.every(action=>action.passed));
      }
      receipt.warm_navigation={status:'passed',samples_per_action:config.samples};
      receipt.restoration={status:'running',after_all_warm_samples:true,checks:[]};
      // A new document has no live React/cache objects and no route in history.
      // The production draft bridge must restore the exact saved owner/window.
      await page.evaluate(()=>{history.replaceState(null,'');});
      await page.reload();
      await page.getByRole('button',{name:epochName,exact:true}).waitFor({timeout:15000});await quiet(page);
      const restored=await page.evaluate(()=>({route:history.state.riekeWorkspace.route,start:document.querySelector('[aria-label="Start sample"]')?.value,count:document.querySelector('[aria-label="Sample count"]')?.value}));
      assert.equal(restored.route.protocol,meta.protocol);assert.equal(restored.start,'100');assert.equal(restored.count,'1000');
      receipt.restoration.checks.push({sample,id:'disk.document-restore',passed:true,...restored});
      if(config.expect_retained){
        // The actual canonical overview endpoint wrote this disk snapshot. The
        // only simulated part is held shell activation, not cache contents.
        const display=await page.evaluate(()=>fetch('/api/project/presentation').then(r=>r.json()));
        assert.equal(display.available,true);assert.equal(display.presentation_only,true);
        assert.equal(display.project_uuid,meta.project);assert.equal(display.project_path,meta.project_path);
        await page.getByRole('button',{name:'Project overview',exact:true}).click();await quiet(page);
        await page.evaluate(async()=>{const {flushDesktopDrafts}=await import('/src/desktopLifecycle.js');await flushDesktopDrafts();history.replaceState(null,'');});
        holdActivation=true;
        const began=performance.now();await page.reload();
        await page.locator('[data-workspace-active="true"] .infographic-overview[inert]').waitFor({timeout:15000});
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const cachedAt=performance.now()-began;
        const beforeReady=await page.evaluate(()=>{
          window.__retention.nodes.overview=document.querySelector('[data-workspace-active="true"] .infographic-overview');
          return {inert:window.__retention.nodes.overview.inert,text:window.__retention.nodes.overview.innerText,
            requests:window.__retention.requests.map(({result,...row})=>row)};
        });
        assert.equal(beforeReady.inert,true);assert.ok(beforeReady.text.includes('Recorded epochs'));
        assert.equal(beforeReady.requests.some(r=>/^\/api\/(overview|data-stores|protocols)(?:[/?]|$)/.test(r.path)),false,'Saved display must not start scientific reads before activation');
        assert.equal(typeof releaseActivation,'function','Owned activation must remain pending');
        holdActivation=false;releaseActivation();
        await page.locator('[data-workspace-active="true"] .infographic-overview:not([inert])').waitFor({timeout:15000});await quiet(page);
        const current=await page.evaluate(()=>({same_node:document.querySelector('[data-workspace-active="true"] .infographic-overview')===window.__retention.nodes.overview,requests:window.__retention.requests.map(({result,...row})=>row)}));
        assert.equal(current.same_node,true,'Canonical summary must update the displayed overview in place');
        receipt.restoration.checks.push({sample,id:'disk.early-overview',passed:true,cache_visible_ms:cachedAt,canonical_ready_ms:performance.now()-began,
          cache_identity:{project_uuid:display.project_uuid,project_path:display.project_path,observed_at:display.observed_at},before_ready:beforeReady,canonical:current,
          observation:'New document, actual SQLite presentation snapshot, held shell activation; not process/native startup timing.'});
      }
      receipt.restoration.status='passed';
      }
      assert.deepEqual(errors,[]);
      await fs.writeFile(path.join(output,`requests-${sample}.json`),JSON.stringify(ledger.entries,null,2));ledger.detach();ledger=null;
      await context.close();context=null;
    }
    receipt.status='passed';
  }catch(error){receipt.status='failed';if(receipt.restoration?.status==='running')Object.assign(receipt.restoration,{status:'failed',error:String(error)});receipt.failures.push(String(error));if(page){await fs.writeFile(path.join(output,'failure.txt'),await page.locator('body').innerText().catch(()=>''));await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});}throw error;}
  finally{
    if(ledger){await fs.writeFile(path.join(output,'failed-requests.json'),JSON.stringify(ledger.entries,null,2));ledger.detach();}
    for(const [name,value]of[['context',context],['browser',browser],['vite',server]]){try{await value?.close();receipt.cleanup[name]=true;}catch(error){receipt.cleanup[name]=false;receipt.failures.push(String(error));receipt.status='failed';}}
    await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  }
}

if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)run(options(process.argv.slice(2))).catch(error=>{console.error(error);process.exitCode=1;});
