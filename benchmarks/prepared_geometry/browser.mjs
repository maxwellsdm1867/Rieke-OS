import {geometryReadiness,geometrySnapshot} from './observer.mjs';
import fs from 'node:fs/promises';import path from 'node:path';import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const [root,serverJson,output,samplesText='3']=process.argv.slice(2),samples=Number(samplesText);if(!root||!serverJson||!output||!Number.isInteger(samples)||samples<1)throw Error('source server-json output samples required');await fs.mkdir(output,{recursive:false});
const timingEnabled=process.env.PREPARED_GEOMETRY_TIMING==='1';
const meta=JSON.parse(await fs.readFile(serverJson,'utf8')),workspace=path.join(root,'workspace-app');
const {fixtureSource,installObserver,installTraceControlReader,installBinaryTraceOracle}=await import(pathToFileURL(path.resolve(import.meta.dirname,'../workflow/fixture-app.mjs')));
const {readiness,snapshotAction,resetPreparation,assertFinalizedRequests,armAction,observationFinished}=await import(pathToFileURL(path.resolve(import.meta.dirname,'../workflow/browser.mjs')));
const require=createRequire(path.join(root,'desktop/package.json')),{chromium}=require('playwright');
let server,browser,context;const results=[];const receipt={status:'running',diagnostic_only:true,native_mysql:false,metadata_epochs:meta.epochs,cohort_epochs:meta.protocol_epochs,trace_samples:1000000,source:root,conditions:meta.diagnostic};
try{
 const {buildOwnedProduction}=await import('./build.mjs');receipt.production_build=await buildOwnedProduction(root,meta,output);
 browser=await chromium.launch({headless:true,...(process.env.PREPARED_GEOMETRY_BROWSER?{executablePath:process.env.PREPARED_GEOMETRY_BROWSER}:{}),args:['--no-first-run','--no-default-browser-check']});receipt.environment={node:process.version,browser:browser.version(),viewport:{width:1500,height:1100},dpr:1,runtime:'production-react-direct-werkzeug',http_server:meta.http_server,vite_proxy:false,timing_mode:timingEnabled?'diagnostic':'ordinary'};
 for(let sample=0;sample<samples;sample++){
  context=await browser.newContext({viewport:{width:1500,height:1100},...(timingEnabled?{extraHTTPHeaders:{'X-Disco-Trace-Timing':'1'}}:{})});const page=await context.newPage();
  const displayTimings=new Map();
  if(timingEnabled)page.on('response',response=>{
   const url=new URL(response.url()),action=response.request().headers()['x-benchmark-action'];
   if(url.origin!==`http://127.0.0.1:${meta.port}`||!url.pathname.endsWith('/display')||!action)return;
   // Diagnostic headers only: observe the existing response without consuming,
   // cloning or fetching its body. Exact action+URL excludes setup/cursor reads.
   displayTimings.set(JSON.stringify([action,url.pathname+url.search]),response.headers()['server-timing']??null);
  });
  await page.addInitScript(installTraceControlReader,{streams:meta.trace_streams});await page.addInitScript(installBinaryTraceOracle);await page.addInitScript(installObserver,{phase:'ordinary',module_timing:false});
  await page.addInitScript(()=>{
   const paths=new WeakMap(),proto=CanvasRenderingContext2D.prototype;
   const begin=proto.beginPath,move=proto.moveTo,line=proto.lineTo,stroke=proto.stroke;
   proto.beginPath=function(...args){if(this.canvas.classList.contains('tv-base'))paths.set(this,[]);return begin.apply(this,args);};
   proto.moveTo=function(x,y){paths.get(this)?.push(['M',x,y]);return move.call(this,x,y);};
   proto.lineTo=function(x,y){paths.get(this)?.push(['L',x,y]);return line.call(this,x,y);};
   proto.stroke=function(...args){const result=stroke.apply(this,args);if(this.canvas.classList.contains('tv-base')&&this.strokeStyle===getComputedStyle(this.canvas).getPropertyValue('--plot-trace').trim())window.__geometryCanvasPath=paths.get(this);return result;};
  });
  await page.goto(`http://127.0.0.1:${meta.port}/__workflow__`);await page.getByRole('button',{name:'Benchmark Workbench',exact:true}).waitFor();const bootstrap=await page.evaluate(()=>window.__diagnosticProductionContext);if(!bootstrap?.production||bootstrap.mode!=='production'||bootstrap.entry!=='src/main.jsx')throw Error('Production bootstrap not attested');const scripts=await page.locator('script[src]').evaluateAll(nodes=>nodes.map(n=>n.src));if(!scripts.length||scripts.some(url=>!url.startsWith(`http://127.0.0.1:${meta.port}/__workflow-assets/`)))throw Error('Nonlocal or development scripts loaded');receipt.production_context=bootstrap;receipt.script_urls=scripts;
  await page.evaluate(async expectedHash=>{const b=await (await fetch('/__diagnostic__/expected-f64le')).arrayBuffer();window.__diagnosticExpected=new Uint8Array(b);const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),v=>v.toString(16).padStart(2,'0')).join('');if(b.byteLength!==8000000||hash!==expectedHash)throw Error('Independent expected payload mismatch');},meta.diagnostic.payload_sha256);
  await page.waitForFunction(()=>window.__workflow.requests.every(r=>r.end!==undefined||r.error));await resetPreparation(meta,{timeoutMs:180000});
  async function clickAndObserve(locator,spec,id){
   await locator.waitFor({state:'visible',timeout:180000});
   // Install and arm the page-owned oracle before intent; driver transport only
   // retrieves a completed result and cannot advance its frame count or clock.
   await page.evaluate(`window.__workflowReadiness = (${(spec.trace?geometryReadiness:readiness).toString()})`);
   await locator.evaluate(armAction,{action_id:id,phase:'ordinary',spec,timeoutMs:180000});
   await page.waitForFunction(observationFinished,id,{polling:'raf',timeout:195000});
   return await page.evaluate(spec.trace?geometrySnapshot:snapshotAction,id);
  }
  const preparation=await clickAndObserve(page.getByRole('button',{name:'Benchmark Workbench',exact:true}),{selector:'button',text:'Select all',enabled:true,requestPath:'/prepare',prepared:true,preparedUuids:meta.incoming_epochs,expectedReused:false,expectedPrepareStatus:201},`setup-${sample}`);
  await page.locator('.incoming-browser .cell-tree-date').first().evaluate(el=>{el.open=true;});await page.locator('.incoming-browser .cell-tree-cell').first().evaluate(el=>{el.open=true;});
  await page.waitForFunction(()=>window.__workflow.requests.every(r=>r.end!==undefined||r.error),null,{timeout:180000});
  const display=await page.evaluate(()=>{const offered=window.__workflow.requests.flatMap(r=>[r.result?.trace_read_context,r.result?.context?.trace_read_context,r.result?.bootstrap?.page?.trace_read_context]).filter(v=>v?.kind==='prepared_display');if(!offered.length)throw Error('Prepared response did not advertise prepared_display');return offered.at(-1);});
  if(display.candidate_revision_uuid!==preparation.correctness.prepared.candidate_revision_uuid||display.project_uuid!==meta.project||display.protocol_uuid!==meta.protocol)throw Error('Prepared display membership owner mismatch');
  const traceRoot='/trace-views/'+display.token;
  const epochNumber=2; // UI labels the ordinal within this incoming cell, not recorded epoch_number.
  const id=`ordinary-${sample}-million`,row=await clickAndObserve(page.getByRole('button',{name:`Inspect ${meta.date_label} · ${meta.incoming_cell_label} epoch ${epochNumber}`,exact:true}),{selector:'.tv-base',trace:meta.million_trace_expected},id);
  if(timingEnabled)for(const request of row.requests){
   const key=JSON.stringify([row.action_id,request.url]);
   if(new URL(request.url,`http://127.0.0.1:${meta.port}`).pathname.endsWith('/display')){
    const timing=displayTimings.get(key);
    if(typeof timing!=='string'||!timing.includes('trace_'))throw Error('Missing diagnostic display Server-Timing');
    request.server_timing=timing;
   }
  }
  // Independent wire, source-index, exact point-byte and whole-statistics oracle.
  row.exact=await page.evaluate(({action_id,display,traceRoot,epoch,stream})=>{
   const fail=message=>{throw Error(message);},requests=window.__workflow.completed[action_id].captured_requests;
   if(requests.length!==1)fail('Expected exactly one geometry request');const r=requests[0],url=new URL(r.url,location.href),b=r.binary,v=new DataView(b),bytes=new Uint8Array(b),expected=window.__diagnosticExpected,source=new DataView(expected.buffer,expected.byteOffset,expected.byteLength),N=1000000;
   if(url.pathname!=='/api'+traceRoot+'/epochs/'+epoch+'/display'||!r.content_type.startsWith('application/vnd.disco.trace-m4le.v1')||new TextDecoder().decode(bytes.slice(0,4))!=='DTM1')fail('Wrong geometry route or representation');
   const length=v.getUint32(4,true);if(length>65536)fail('Header exceeds bound');const h=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes.slice(8,8+length))),indicesOffset=Math.ceil((8+length)/8)*8,K=h.point_count,valuesOffset=Math.ceil((indicesOffset+K*4)/8)*8;
   const canonical=x=>JSON.stringify(Object.fromEntries(Object.entries(x).sort(([a],[b])=>a.localeCompare(b))));if(canonical(h.read_context)!==canonical(display)||h.epoch_uuid!==epoch||h.stream_uuid!==stream.stream_uuid||h.source_sha256!==stream.source_sha256||h.sample_rate!==stream.sample_rate||h.units!==stream.units||h.raw_start!==0||h.raw_count!==N||h.total_samples!==N||h.representation!=='m4_geometry'||h.algorithm!=='first-last-extrema-v1'||'decimated'in h||'values'in h)fail('Identity or representation mismatch');
   const width=Number(url.searchParams.get('physical_width'));if(h.physical_width!==width||!Number.isFinite(width)||width<=0||K>4*Math.ceil(width)||b.byteLength!==valuesOffset+K*8)fail('Geometry bounds mismatch');for(let i=8+length;i<indicesOffset;i++)if(bytes[i])fail('Nonzero header pad');for(let i=indicesOffset+K*4;i<valuesOffset;i++)if(bytes[i])fail('Nonzero point pad');
   let low=Infinity,high=-Infinity,bucket=-1,first=0,last=0,min=0,max=0,selected=[];const emit=()=>{if(bucket>=0)selected.push(...[...new Set([first,last,min,max])].sort((a,b)=>a-b));};
   for(let i=0;i<N;i++){const value=source.getFloat64(i*8,true),column=Math.min(Math.ceil(width)-1,Math.floor(i/(N-1)*width));if(!Number.isFinite(value))fail('Nonfinite source');low=Math.min(low,value);high=Math.max(high,value);if(column!==bucket){emit();bucket=column;first=min=max=i;}last=i;if(value<source.getFloat64(min*8,true))min=i;if(value>source.getFloat64(max*8,true))max=i;}emit();
   if(K!==selected.length)fail('Independent M4 point count mismatch');for(let i=0;i<K;i++){if(v.getUint32(indicesOffset+i*4,true)!==selected[i])fail('M4 source index mismatch');for(let byte=0;byte<8;byte++)if(bytes[valuesOffset+i*8+byte]!==expected[selected[i]*8+byte])fail('Point f64 bit mismatch');}
   if(!Object.is(h.statistics.min,low)||!Object.is(h.statistics.max,high)||h.statistics.finiteCount!==N||h.statistics.missingCount!==0)fail('Whole source statistics mismatch');
   const points=window.__geometryCanvasPath,rect=document.querySelector('.tv-base').getBoundingClientRect(),pad=(high-low)*.08,ymin=low-pad,ymax=high+pad;
   if(!points||points.length!==selected.length)fail('Canvas path count mismatch');
   for(let i=0;i<selected.length;i++){const index=selected[i],x=82+index/(N-1)*Math.max(1,rect.width-103),y=25+(ymax-source.getFloat64(index*8,true))/(ymax-ymin)*Math.max(1,rect.height-82);if(points[i][0]!== (i?'L':'M')||Math.abs(points[i][1]-x)>1e-9||Math.abs(points[i][2]-y)>1e-9)fail('Canvas did not paint the independently expected sample coordinates');}
   return {all_canvas_coordinates_exact:true,all_source_indices_match:true,all_emitted_point_bytes_match:true,whole_statistics_exact:true,prepared_display_context_exact:true,raw_count:N,point_count:K,wire_bytes:b.byteLength,physical_width:width,verification_outside_observation:true};
  },{action_id:id,display,traceRoot,epoch:meta.million_trace_expected.epoch_uuid,stream:meta.million_trace_expected});
  await page.waitForFunction(action_id=>window.__workflow.completed[action_id].captured_requests.every(r=>r.end!==undefined||r.error),id);if(row.requests.some(r=>r.end_ms===null||r.error))throw Error('Unfinished geometry request');
  const cursorStart=await page.evaluate(()=>window.__workflow.requests.length);
  await page.getByLabel('Exact sample index for cursor',{exact:true}).fill('123456');
  await page.waitForFunction(()=>!['—','Loading sample…','Sample unavailable'].some(value=>document.querySelector('[aria-label="Recorded response and scientific units"]')?.textContent.startsWith(value)));
  row.cursor=await page.evaluate(({cursorStart,display,epoch,stream})=>{
   const records=window.__workflow.requests.slice(cursorStart);if(records.length!==1)throw Error('Cursor must demand exactly one raw tile');
   const r=records[0],u=new URL(r.url,location.href),h=r.result;
   if(r.status!==200||r.end===undefined||u.pathname!==`/api/trace-views/${display.token}/epochs/${epoch}/trace`||!h||!Array.isArray(h.values)||h.values.length!==20000||h.start!==120000||h.count!==20000||h.total_samples!==1000000||h.epoch_uuid!==epoch||h.stream_uuid!==stream.stream_uuid||h.source_sha256!==stream.source_sha256||h.units!=='pA'||h.sample_rate!==10000||h.decimated!==false||h.read_context?.token!==display.token)throw Error('Raw cursor identity/bounds mismatch');
   const expected=window.__diagnosticExpected,view=new DataView(expected.buffer),raw=new DataView(new ArrayBuffer(8));
   for(let i=0;i<h.count;i++){raw.setFloat64(0,h.values[i],true);for(let b=0;b<8;b++)if(raw.getUint8(b)!==expected[(h.start+i)*8+b])throw Error('Raw tile source bits differ');}
   if(document.querySelector('[aria-label="Recorded sample index"]').textContent.replaceAll(',','')!=='123456')throw Error('Wrong cursor source index');
   const value=view.getFloat64(123456*8,true),label=document.querySelector('[aria-label="Recorded response and scientific units"]').textContent;
   if(label!==String(value)+' pA')throw Error('Cursor readout is not exact source value');
   return {all_tile_bytes_exact:true,index:123456,count:20000,value,request:r.url};
  },{cursorStart,display,epoch:meta.million_trace_expected.epoch_uuid,stream:meta.million_trace_expected});
  row.authority=await (await fetch(`http://127.0.0.1:${meta.port}/__diagnostic__/status`)).json();
  if(!row.authority.native_contract||!row.authority.prepared_display_canonical||!row.authority.source_verifier_canonical||row.authority.helper_abi!==4||row.authority.native_counts.admitted!==sample+1||row.authority.native_counts.fallback!==0||row.authority.reduce_counts.admitted!==sample+1||row.authority.reduce_counts.fallback!==0)throw Error('Canonical prepared-display ownership did not remain valid');
  const requests=row.requests.filter(r=>r.url.includes('/display?'));row.breakdown={click_to_first_trace_request_ms:requests[0].start_ms,http_window_ms:requests.at(-1).end_ms-requests[0].start_ms,last_body_to_stroke_ms:row.trace.first_visible_ms-requests.at(-1).end_ms,stroke_to_first_raf_ms:row.trace.first_raf_ms-row.trace.first_visible_ms,first_to_second_raf_ms:row.trace.complete_ms-row.trace.first_raf_ms,stroke_to_second_frame_ms:row.trace.complete_ms-row.trace.first_visible_ms};
  row.sample_index=sample;row.sample_class=sample===0?'first_trace_after_setup_warm_OS':'subsequent_trace_fresh_renderer_warm_OS';results.push(row);await fs.appendFile(path.join(output,'samples.jsonl'),JSON.stringify(row)+'\n');console.log(JSON.stringify({sample,complete_ms:row.trace.complete_ms,post_stroke_ms:row.trace.first_visible_ms,requests:requests.length,exact:true,authority:row.authority}));await context.close();context=null;
 }
 receipt.status='passed';receipt.samples=results;receipt.note='Real production components/trace routes; SQL explicitly doubled; source SHA verifier and sealed index canonical. No compositor/nativeMySQL/cold-storage claim.';
}catch(error){receipt.status='failed';receipt.error=String(error);if(context){const page=context.pages()[0];if(page){await fs.writeFile(path.join(output,'failure-body.txt'),await page.locator('body').innerText());await fs.writeFile(path.join(output,'failure-requests.json'),JSON.stringify(await page.evaluate(()=>window.__workflow.requests.map(({result,binary,...r})=>r)),null,2));}}process.exitCode=1;}
finally{await context?.close();await browser?.close();await server?.close();await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2));}
