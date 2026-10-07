import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {fixtureSource,installObserver} from './fixture-app.mjs';
import {attachLedger} from '../navigation-probe.mjs';

export function options(argv){const value={samples:3};for(let i=0;i<argv.length;i+=2){if(!argv[i].startsWith('--')||argv[i+1]===undefined)throw Error('Expected --key value');value[argv[i].slice(2).replaceAll('-','_')]=argv[i+1];}for(const key of ['source_root','server_json','output'])if(!value[key])throw Error(`Missing --${key.replaceAll('_','-')}`);value.samples=Number(value.samples);if(!Number.isInteger(value.samples)||value.samples<1)throw Error('samples must be positive');return value;}

// Fixed core inventory; variants not executed are retained as explicit gaps.
export const inventory=[['view.open','cold-component'],['view.return','warm-resource'],['tree.open','main-columns'],['tree.expand','main-first-cell'],['tree.next_page','main-cell-epochs'],['tree.split_change','remove-epoch-block'],['tree.selection','incoming-select-all'],['tree.selection','incoming-deselect-all'],['predicate.search','cell-equality'],['workbench.prepare','current-queue'],['workbench.open','prepared-return'],['trace.inspect','first-owned-waveform']];
const limits=['Owned shell mounts production components; full App navigation/session restoration unmeasured.','DOM/RAF and canvas calls are observations, not compositor presentation.','Development Vite/React runtime; not installed desktop performance.','Split add/reorder/recorded-field variants, hierarchy, queued/range selections, predicate selectivity/continuation, preparation invalidation, and trace supersession/scroll remain unmeasured.'];

/** Browser-side gate uses only independently specified fixture expectations and
 * rendered state. Network payload validation adds identity/count evidence, never
 * replaces the visible readiness boundary. */
export function readiness(spec){
  const w=window.__workflow, a=w.active;
  const pending=()=>{a.frames=0;a.signature=null;return false;};
  const visible=el=>!!el&&el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0&&getComputedStyle(el).visibility!=='hidden';
  const requests=w.requests.filter(r=>r.action_id===a.action_id);
  if(requests.some(r=>r.error||r.status>=400))throw Error('Action API request failed');
  const elements=[...document.querySelectorAll(spec.selector)];
  const current=elements.filter(visible).filter(el=>!spec.text||el.textContent.includes(spec.text));
  if(!current.length)return pending();
  if(spec.text&&!current.some(el=>el.textContent.includes(spec.text)))return pending();
  if(spec.totalText&&!document.body.textContent.includes(spec.totalText))return pending();
  if(spec.splitLabels){const labels=[...document.querySelectorAll('.tb-steps [aria-label^="Reorder "]')].map(el=>el.getAttribute('aria-label'));if(JSON.stringify(labels)!==JSON.stringify(spec.splitLabels))return pending();}
  if(spec.enabled&&!current.some(el=>!el.disabled))return pending();
  if(document.querySelector('.column-tree[aria-busy="true"]'))return pending();
  let evidence={selector:spec.selector,text:spec.text||null};
  if(spec.membership){if(!document.querySelector('.inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const r=[...w.requests].reverse().find(r=>r.result?.total===spec.membership&&Array.isArray(r.result?.epochs)&&Array.isArray(r.result?.cells));if(!r)return pending();evidence.total=spec.membership;evidence.query_revision=r.result.query_revision;}
  if(spec.searchUuids){if(!document.querySelector('.matching-epochs .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const r=[...requests].reverse().find(r=>r.url.includes('/explore/epochs')&&Array.isArray(r.result?.epochs));if(!r)return pending();const got=r.result.epochs.map(e=>e.epoch_uuid);if(JSON.stringify(got)!==JSON.stringify(spec.searchUuids.slice(0,got.length))||r.result.total!==spec.searchUuids.length||got.length!==Math.min(60,spec.searchUuids.length))return pending();evidence.result_uuids=got;evidence.total=r.result.total;}
  if(spec.savedPrepared){const saved=w.incomingSession?.prepared;for(const key of ['candidate_revision_uuid','queue_revision','candidate_scope_revision'])if(saved?.[key]!==spec.savedPrepared[key])return pending();if(!document.querySelector('.incoming-browser .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();const p=[...requests].reverse().find(r=>r.result?.query_revision===saved.candidate_scope_revision&&Array.isArray(r.result?.epochs));if(!p||p.result.total!==spec.preparedUuids.length||JSON.stringify(p.result.epochs.map(e=>e.epoch_uuid))!==JSON.stringify(spec.preparedUuids.slice(0,60)))return pending();evidence.prepared=spec.savedPrepared;}
  if(spec.selected){const session=w.incomingSession;const draft=session?.drafts?.[session?.prepared?.candidate_revision_uuid];if(JSON.stringify(draft?.selected)!==JSON.stringify(spec.selected))return pending();evidence.selected_uuids=draft.selected;}
  if(spec.uuids){const got=current.map(el=>el.getAttribute('data-epoch-uuid'));if(JSON.stringify(got)!==JSON.stringify(spec.uuids))return pending();evidence.uuids=got;}
  if(spec.trace){const expected=spec.trace;a.trace_expected={...expected,end:expected.start+expected.count};const r=[...requests].reverse().find(r=>r.result?.epoch_uuid===expected.epoch_uuid&&r.result?.stream_uuid===expected.stream_uuid&&Array.isArray(r.result?.values));if(!r)return pending();const d=r.result;for(const key of ['start','count','sample_rate','units'])if(expected[key]!==undefined&&d[key]!==expected[key])throw Error('Trace mismatch '+key);if(d.values.length!==d.count)throw Error('Incomplete trace values');if(expected.values_first!==undefined&&d.values[0]!==expected.values_first)throw Error('Incorrect first waveform sample');if(expected.values_last!==undefined&&d.values.at(-1)!==expected.values_last)throw Error('Incorrect last waveform sample');if(!w.draws.some(v=>v.at>=r.end&&v.stream_uuid===expected.stream_uuid))return pending();if(document.querySelector('[aria-label="Response stream"]')?.value!==expected.stream_uuid)return pending();if(document.querySelector('.tv-status'))return pending();a.first_trace_at??=performance.now();evidence.trace={epoch_uuid:d.epoch_uuid,stream_uuid:d.stream_uuid,start:d.start,count:d.count,sample_rate:d.sample_rate,units:d.units,values_count:d.values.length};}
  if(spec.requestPath){const r=[...requests].reverse().find(r=>r.url.includes(spec.requestPath)&&r.result);if(!r)return pending();evidence.response=r.result;if(spec.prepared){const session=w.incomingSession,prepared=session?.prepared;if(!prepared?.candidate_revision_uuid)return pending();if(prepared.candidate_revision_uuid!==r.result.candidate_revision_uuid||prepared.queue_revision!==r.result.queue_revision||prepared.candidate_scope_revision!==r.result.candidate_scope_revision)return pending();if(prepared.context?.counts?.incoming_epochs!==spec.preparedUuids.length||prepared.context?.publication_blocked)return pending();const draft=session.drafts?.[prepared.candidate_revision_uuid];if(draft?.selected?.length||draft?.receipt)throw Error('Preparation silently selected or merged');const page=[...requests].reverse().find(v=>v.result?.query_revision===prepared.candidate_scope_revision&&Array.isArray(v.result?.epochs));if(!page||page.result.total!==spec.preparedUuids.length||page.result.epochs.length!==Math.min(60,spec.preparedUuids.length))return pending();if(JSON.stringify(page.result.epochs.map(e=>e.epoch_uuid))!==JSON.stringify(spec.preparedUuids.slice(0,page.result.epochs.length)))throw Error('Wrong prepared membership');if(!document.querySelector('.incoming-browser .inspection-cell-tree[data-inspection-membership-ready="true"]'))return pending();evidence.prepared={candidate_revision_uuid:prepared.candidate_revision_uuid,queue_revision:prepared.queue_revision,candidate_scope_revision:prepared.candidate_scope_revision,total:page.result.total,epoch_uuids:page.result.epochs.map(e=>e.epoch_uuid),reused:r.result.reused};}if(spec.expectedCount!==undefined){const count=r.result.matched_count??r.result.count??r.result.total_epochs??r.result.pending_epoch_count;if(count!==spec.expectedCount)throw Error('Incorrect result count '+count+' expected '+spec.expectedCount);}}
  // Two successive RAF observations of the same correct result, in page clock.
  const signature=JSON.stringify(evidence);if(a.signature!==signature){a.signature=signature;a.frames=0;}a.frames++;
  if(a.frames<2)return false;
  a.ready=performance.now();a.evidence=evidence;return true;
}

export async function run(config){
  const root=path.resolve(config.source_root), workspace=path.join(root,'workspace-app'), output=path.resolve(config.output);
  await fs.mkdir(output,{recursive:true});const meta=JSON.parse(await fs.readFile(config.server_json,'utf8'));
  if(!Number.isInteger(meta.port)||meta.port<1||meta.port>65535)throw Error('Invalid owned backend port');
  const receipt={format:'disco-workflow-browser-v1',status:'incomplete',epochs:meta.epochs,actions:inventory.map(([id,variant])=>({id,variant,samples:[]})),failures:[],gaps:[],limitations:limits.slice(0,3),unmeasured_variants:[limits[3]],cleanup:{},observation:'click handler capture to correct DOM/two RAF; no compositor claim'};
  let server,browser,context;
  const require=createRequire(path.join(workspace,'package.json'));
  let chromium;try{({chromium}=require('playwright'));}catch{({chromium}=createRequire(path.join(root,'desktop/package.json'))('playwright'));}
  try{
    const {createServer}=await import(pathToFileURL(path.join(workspace,'src/test-support/isolatedVite.js')));
    const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
    const entry=path.join(workspace,'__workflow_owned__.jsx');
    server=await createServer({root:workspace,configFile:false,logLevel:'error',plugins:[react(),{name:'owned-workflow-fixture',resolveId(id){if(id==='/__workflow_owned__.jsx')return entry;},load(id){if(id===entry)return fixtureSource(meta);},configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__workflow__')return next();res.setHeader('Content-Type','text/html');res.end('<div id="root"></div><script type="module" src="/__workflow_owned__.jsx"></script>');});}}],server:{host:'127.0.0.1',port:0,hmr:false,proxy:{'/api':{target:`http://127.0.0.1:${meta.port}`,changeOrigin:true,configure(proxy){proxy.on('proxyReq',req=>req.removeHeader('origin'));}}}}});
    await server.listen();receipt.frontend_port=server.httpServer.address().port;
    browser=await chromium.launch({headless:true,...((config.browser_executable||process.env.WORKFLOW_BROWSER_EXECUTABLE)?{executablePath:config.browser_executable||process.env.WORKFLOW_BROWSER_EXECUTABLE}:{}),args:['--no-first-run','--no-default-browser-check']});
    receipt.environment={node:process.version,browser:browser.version(),viewport:{width:1500,height:1100},device_scale_factor:1,headless:true,runtime:'vite-react-development'};
    for(const phase of ['ordinary','profile'])for(let sample=0;sample<(phase==='profile'?Number(config.profile_samples||1):config.samples);sample++){
      context=await browser.newContext({viewport:{width:1500,height:1100}});const page=await context.newPage();await page.addInitScript(installObserver,{phase});const ledger=attachLedger(page,'workflow');
      page.on('pageerror',e=>receipt.failures.push({phase,sample,error:e.message}));
      await page.goto(`http://127.0.0.1:${receipt.frontend_port}/__workflow__`);await page.getByRole('button',{name:'Benchmark Main',exact:true}).waitFor();
      const button=name=>page.getByRole('button',{name,exact:true});
      async function measure(id,variant,locator,spec){
        const action_id=`${phase}-${sample}-${id}-${variant}`;
        await locator.waitFor({state:'visible',timeout:15000});
        await locator.evaluate((el,data)=>new Promise((resolve,reject)=>{const until=performance.now()+15000;function attempt(){if(!el.isConnected)return reject(Error('Action target detached'));if(el.disabled){if(performance.now()>until)return reject(Error('Action target stayed disabled'));return requestAnimationFrame(attempt);}window.__workflow.active={...data,intent:performance.now(),frames:0};el.click();resolve();}attempt();}),{action_id,phase});
        try{await page.waitForFunction(readiness,spec,{polling:'raf',timeout:Number(config.action_timeout_ms||180000)});
          await page.waitForFunction(()=>{const w=window.__workflow;return w.requests.filter(r=>r.action_id===w.active.action_id&&r.start<=w.active.ready).every(r=>r.end!==undefined||r.error);},null,{timeout:30000});
          const result=await page.evaluate(()=>{const w=window.__workflow,a=w.active,requests=w.requests.filter(r=>r.action_id===a.action_id);return {action_id:a.action_id,total_ms:a.ready-a.intent,phase:a.phase,correctness:{passed:true,...a.evidence},...(a.first_trace_at?{trace:{expected:a.trace_expected,first:{...a.evidence.trace,end:a.evidence.trace.start+a.evidence.trace.count},complete:{...a.evidence.trace,end:a.evidence.trace.start+a.evidence.trace.count},first_visible_ms:a.first_trace_at-a.intent,complete_ms:a.ready-a.intent,observation:'correct response plus canvas stroke plus DOM/RAF; no compositor claim'}}:{}),requests:requests.map(({start,headers,end,result,decode_start,...r})=>({...r,start_ms:start-a.intent,headers_ms:headers===undefined?null:headers-a.intent,end_ms:end===undefined?null:end-a.intent})),frontend_spans:requests.filter(r=>r.start<a.ready).flatMap((r,i)=>{const parent={id:'request-'+i,module:'api-transport',name:'request-through-consumption',request_id:r.request_id,start_ms:r.start-a.intent,end_ms:Math.min(r.end??a.ready,a.ready)-a.intent,clipped_at_ready:r.end===undefined||r.end>a.ready,clock:'browser',inclusive:true,interpretation:'HTTP wait plus response consumption; backend work is nested, not exclusive CPU'};return [parent,...(r.decode_start!==undefined&&r.decode_start<a.ready?[{id:'body-'+i,parent_id:parent.id,module:'api-response-consumption',name:'response-json-consumption',request_id:r.request_id,start_ms:r.decode_start-a.intent,end_ms:parent.end_ms,clipped_at_ready:parent.clipped_at_ready,clock:'browser',inclusive:true,interpretation:'Includes body wait and JSON decode, not exclusive CPU'}]:[])];}),react_renders:w.renders.filter(r=>r.action_id===a.action_id),cache_classification:requests.length?'requests-observed':'no-request-observed'};});
          // React actualDuration is CPU accounting, deliberately not a wall span.
          receipt.actions.find(a=>a.id===id&&a.variant===variant).samples.push(result);await page.evaluate(()=>{window.__workflow.active=null;});return result;
        }catch(error){receipt.failures.push({action_id,error:String(error)});await fs.writeFile(path.join(output,`${action_id}.txt`),await page.locator('body').innerText());await page.screenshot({path:path.join(output,`${action_id}.png`)});await page.evaluate(()=>{window.__workflow.active=null;});throw error;}
      }
      try{
        const edit={selector:'button',text:'Edit Tree',enabled:true,membership:meta.main_count};
        await measure('view.open','cold-component',button('Benchmark Main'),edit);
        await button('Benchmark Away').click();await measure('view.return','warm-resource',button('Benchmark Main'),edit);
        await measure('tree.open','main-columns',button('Edit Tree'),{selector:'.tp-column .tp-branch',enabled:true});
        // Removal must preserve all fixture membership, then navigate date/cell.
        await measure('tree.split_change','remove-epoch-block',button('Remove Epoch block grouping'),{selector:'.tb-steps',splitLabels:['Reorder Recording date, level 1','Reorder Cell, level 2'],totalText:`Current view · ${meta.main_count.toLocaleString('en-US')} epochs`});
        const branches=page.locator('.tp-column .tp-branch');await branches.first().click();
        await page.locator('.tp-column').nth(1).locator('.tp-branch').first().waitFor();
        const expected=meta.first_cell_epochs;
        if(!Array.isArray(expected))throw Error('Independent first_cell_epochs oracle missing');
        await measure('tree.expand','main-first-cell',page.locator('.tp-column').nth(1).locator('.tp-branch').first(),{selector:'.tp-terminal [data-epoch-uuid]',uuids:expected.slice(0,60)});
        if(expected.length>60)await measure('tree.next_page','main-cell-epochs',button('Next page in column 3'),{selector:'.tp-terminal [data-epoch-uuid]',uuids:expected.slice(60,120)});else receipt.gaps.push('tree.next_page fixture too small');
        if(expected.length>60)await button('Previous page in column 3').click();
        await page.locator(`[data-epoch-uuid="${meta.first_epoch}"]`).waitFor();
        await button('Back to epochs').click();
        await page.locator('.cell-tree-date').first().evaluate(el=>{el.open=true;});
        await page.locator('.cell-tree-cell').first().evaluate(el=>{el.open=true;});
        try{await measure('trace.inspect','first-owned-waveform',page.getByRole('button',{name:`Inspect ${meta.date_label} · ${meta.cell_label} epoch 1`,exact:true}),{selector:'.tv-base',trace:meta.trace_expected});}catch{} // Retain failed trace evidence while exercising independent workflows.
        await button('Benchmark Predicate').click();try{await measure('predicate.search','cell-equality',button('View matching epochs'),{selector:'.mx-results-workflow',requestPath:'/explore/run',expectedCount:expected.length,searchUuids:expected});}catch{}
        const preparation=await measure('workbench.prepare','current-queue',button('Benchmark Workbench'),{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:meta.incoming_epochs});
        await measure('tree.selection','incoming-select-all',button('Select all'),{selector:'button',text:`Merge (${meta.incoming_count} epochs)`,selected:meta.incoming_epochs});
        await measure('tree.selection','incoming-deselect-all',button('Deselect all'),{selector:'button',text:'Merge (0 epochs)',selected:[]});
        await button('Benchmark Away').click();await measure('workbench.open','prepared-return',button('Benchmark Workbench'),{selector:'button',text:'Select all',enabled:true,savedPrepared:preparation.correctness.prepared,preparedUuids:meta.incoming_epochs});
      }catch(error){receipt.failures.push({phase,sample,error:String(error)});}finally{ledger.detach();await fs.writeFile(path.join(output,`ledger-${phase}-${sample}.json`),JSON.stringify(ledger.entries,null,2));await context.close();context=null;}
    }
    for(const action of receipt.actions)if(action.samples.filter(s=>s.phase==='ordinary').length!==config.samples)receipt.gaps.push(`Missing ordinary samples: ${action.id}/${action.variant}`);
    receipt.status=receipt.failures.length?'failed':receipt.gaps.length?'incomplete':'passed';
  }catch(error){receipt.failures.push({error:String(error)});receipt.status='failed';}
  finally{for(const [name,value] of [['context',context],['browser',browser],['vite',server]]){try{if(value)await value.close();receipt.cleanup[name+'_closed']=true;}catch(error){receipt.cleanup[name+'_closed']=false;receipt.failures.push({cleanup:name,error:String(error)});receipt.status='failed';}}await fs.writeFile(path.join(output,'browser.json'),JSON.stringify(receipt,null,2));}
  return receipt;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){run(options(process.argv.slice(2))).then(r=>{console.log(JSON.stringify({status:r.status,failures:r.failures.length,output:'browser.json'}));if(r.status==='failed')process.exitCode=1;}).catch(e=>{console.error(e);process.exitCode=1;});}
