// Fixture-only browser checks for the real trace component. No native/API service.
// Run only after the serialized numeric/E2E owner releases the UI window.
// PLAYWRIGHT_MODULE may point to an installed Playwright package; no install needed.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../../',import.meta.url));
const app=path.join(root,'workspace-app');
const require=createRequire(path.join(app,'package.json'));
const {createServer,transformWithOxc}=await import(pathToFileURL(require.resolve('vite')));
const {default:react}=await import(pathToFileURL(require.resolve('@vitejs/plugin-react')));
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const output=process.env.TRACE_QA_OUTPUT||'/tmp/rieke-trace-readout-evidence';
const baseline=process.env.TRACE_QA_BASELINE||'6dc6e888e992ea931c8972ead94036bea7091736';
const port=Number(process.env.TRACE_QA_PORT||5187);
const before=file=>execFileSync('git',['show',`${baseline}:workspace-app/src/${file}`],{cwd:root,encoding:'utf8'});
const baselineJs=before('components/TraceViewer.jsx')
 .replace("'../api.js'","'/src/api.js'")
 .replace("'./traceGeometry.js'","'/src/traces/ui/traceGeometry.js'")
 .replace("'./NavigationLoading.jsx'","'/src/components/NavigationLoading.jsx'")
 .replace("'./TraceViewer.css'","'virtual:trace-before.css'");
const entry=`import React,{useState} from 'react';import {createRoot} from 'react-dom/client';
import '/src/styles.css';import '/src/themes.css';import '/src/components/Inspector.css';
import {applyTheme} from '/src/appearanceThemes.js';
const before=new URLSearchParams(location.search).has('before');
const {default:Trace}=await (before?import('virtual:trace-before'):import('/src/traces/ui/TraceViewer.jsx'));
if(before)await import('virtual:scroll-before.css');
window.qaTheme=(theme)=>applyTheme({theme});window.qaTheme('dark');
const epoch=(id,units='pA',sample_rate=10000)=>({epoch_uuid:id,streams:id==='empty'?[]:[{kind:'responses',uuid:id+'-stream',sample_count:80000,sample_rate,units,device:'Recorded amplifier'},{kind:'responses',uuid:id+'-alternate',sample_count:800,sample_rate:10000,units:'nA',device:'Second recorded amplifier'}]});
function Fixture(){const [e,setEpoch]=useState(epoch('first'));window.qaEpoch=(id,units,rate)=>setEpoch(epoch(id,units,rate));return <main className="inspector epoch-inspector-mode qa" style={{width:'800px'}}><section className="inspection-layout without-tree"><div className="inspection-detail"><Trace epoch={e}/><div style={{height:600}}>Scroll verification area</div></div></section></main>}
createRoot(document.getElementById('root')).render(<Fixture/>);`;
const modules={'virtual:trace-entry':entry,'virtual:trace-before':baselineJs,'virtual:trace-before.css':before('components/TraceViewer.css'),'virtual:scroll-before.css':before('scrollbars.css')};
const fixture={name:'trace-readout-fixture',resolveId(id){if(id in modules)return '\0'+id;},load(id){return modules[id.slice(1)];},transform(code,id){if(id==='\0virtual:trace-entry.jsx'||id==='\0virtual:trace-before')return transformWithOxc(code,'trace-fixture.jsx',{lang:'jsx',jsx:{runtime:'automatic'}});},configureServer(server){server.middlewares.use('/trace-check.html',async(req,res)=>{const html=await server.transformIndexHtml('/trace-check.html','<html><head><style>body{padding:12px}.qa{height:860px}.inspection-layout{height:100%}</style></head><body><div id="root"></div><script type="module" src="/@id/__x00__virtual:trace-entry.jsx"></script></body></html>');res.setHeader('Content-Type','text/html');res.end(html);});}};
// Explicit .jsx identity lets the normal React transform handle the fixture entry.
fixture.resolveId=id=>id in modules?'\0'+id+(id==='virtual:trace-entry'?'.jsx':''):undefined;
fixture.load=id=>modules[id.slice(1).replace(/\.jsx$/,'')];
let browser,server;
const receipt={baseline,candidate:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),fixture_only:true,checks:[],screenshots:[]};
await mkdir(output,{recursive:true});
try{
 server=await createServer({root:app,configFile:false,plugins:[fixture,react()],server:{host:'127.0.0.1',port,strictPort:true},logLevel:'error'});await server.listen();
 browser=await chromium.launch({headless:true,...(process.env.TRACE_QA_BROWSER?{executablePath:process.env.TRACE_QA_BROWSER}:{})});
 const context=await browser.newContext({viewport:{width:1000,height:1000}});
 let pendingResolve,hold=false;
 const errors=[];
 const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>{errors.push(String(e));console.error(e)});
 const special=[0,-123.45678901234567,1.2345678901234567e-200,null,1.7976931348623157e+100,-Number.MIN_VALUE];
 await page.route('**/api/epochs/*/trace?**',async route=>{
  const url=new URL(route.request().url()),epochId=url.pathname.split('/')[3],start=Number(url.searchParams.get('start')),count=Number(url.searchParams.get('count'));
  if(hold)await new Promise(resolve=>pendingResolve=resolve);
  const values=Array.from({length:count},(_,i)=>epochId==='gaps'&&i===0?null:epochId==='precision'?special[i%special.length]:i===7?57.6:57.6+6*Math.sin(i/9)+((i>2800&&i<4200)?50*Math.sin(i/3):0));
  await route.fulfill({json:{epoch_uuid:epochId,stream_uuid:url.searchParams.get('stream_uuid'),start,count,sample_rate:epochId==='precision'?3:10000,units:url.searchParams.get('stream_uuid').endsWith('-alternate')?'nA':epochId==='precision'?'mV / recorded amplifier unit':epochId==='gaps'?'nA':'pA',values}});
 });
 const wait=()=>page.getByLabel('Exact sample index for cursor').waitFor({state:'visible'}).then(()=>page.waitForFunction(()=>!document.querySelector('.tv-readout input').disabled));
 const settle=()=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const geometry=()=>page.evaluate(()=>Object.fromEntries(['.tv-plot','.tv-base','.tv-overlay','.tv-readout','.tv-window-navigation','.tv-recording-footer','.trace-viewer'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return [s,{x:r.x,y:r.y,width:r.width,height:r.height}];})));
 const stable=(a,b,name)=>{assert.deepEqual(b,a,name);receipt.checks.push(name);};
 const shot=async name=>{await page.locator('.trace-viewer').screenshot({path:path.join(output,name+'.png')});receipt.screenshots.push(name+'.png');};
 await page.goto(`http://127.0.0.1:${port}/trace-check.html?before`);await wait();
 await page.evaluate(()=>document.querySelector('.qa').style.width='440px');await settle();
 await page.getByLabel('Exact sample index for cursor').fill('7');await settle();await shot('before-dark-narrow');
 const beforeShort=await geometry();await page.getByLabel('Exact sample index for cursor').fill('9999');await settle();receipt.before_change={short:beforeShort,long:await geometry()};
 await page.goto(`http://127.0.0.1:${port}/trace-check.html`);await wait();
 await page.evaluate(()=>document.querySelector('.qa').style.width='440px');await settle();await page.getByLabel('Exact sample index for cursor').fill('7');await settle();await shot('after-dark-narrow');
 for(const width of [800,440,350]){
  await page.evaluate(w=>{document.querySelector('.qa').style.width=w+'px';document.querySelector('.inspection-detail').scrollTop=0;document.activeElement?.blur();},width);await settle();
  for(const theme of ['light','dark','fred','system']){
   await page.evaluate(t=>window.qaTheme(t),theme);await settle();
   const initial=await geometry();
   for(const sample of [7,99,999,9999,19999]){await page.getByLabel('Exact sample index for cursor').fill('');await page.getByLabel('Exact sample index for cursor').fill(String(sample));await settle();stable(initial,await geometry(),`${width}/${theme} digit lengths ${sample}`);}
   assert.equal(await page.locator('.tv-value').first().innerText(),'19,999');
   await shot(`after-${theme}-${width}`);
  }
 }
 await page.evaluate(()=>window.qaEpoch('precision','mV / recorded amplifier unit',3));await wait();
 for(const width of [800,440,350]){
  await page.evaluate(w=>{document.querySelector('.qa').style.width=w+'px';document.querySelector('.inspection-detail').scrollTop=0;document.activeElement?.blur();},width);await settle();const initial=await geometry();
  for(let sample=0;sample<special.length;sample++){
   await page.getByLabel('Exact sample index for cursor').fill('');await page.getByLabel('Exact sample index for cursor').fill(String(sample));await settle();
   assert.equal(await page.locator('.tv-value').nth(1).innerText(),`${String(sample/3)} s`);
   assert.equal(await page.locator('.tv-value').nth(2).innerText(),special[sample]===null?'Missing sample':`${String(special[sample])} mV / recorded amplifier unit`);
   stable(initial,await geometry(),`${width} full precision/sign/exponent/missing ${sample}`);
  }
  await page.locator('.tv-value').nth(2).focus();await page.keyboard.press('ArrowRight');
  assert.ok(await page.locator('.tv-value').nth(2).evaluate(e=>getComputedStyle(e).fontVariantNumeric.includes('tabular-nums')));
 }
 await page.evaluate(()=>document.querySelector('.qa').style.width='440px');await settle();await shot('after-precision-narrow');
 const initial=await geometry();await page.evaluate(()=>window.qaEpoch('empty'));await settle();stable(initial,await geometry(),'epoch without response stream retains viewer geometry');assert.ok(await page.getByLabel('Exact sample index for cursor').isDisabled());hold=true;await page.evaluate(()=>window.qaEpoch('gaps','nA'));await page.waitForFunction(()=>document.querySelector('.tv-readout input').disabled);await settle();stable(initial,await geometry(),'epoch/units selection pending geometry');
 assert.deepEqual(await page.locator('.tv-value').allTextContents(),['—','—','—']);hold=false;pendingResolve?.();await wait();await settle();stable(initial,await geometry(),'epoch/units loaded geometry');
 await page.getByLabel('Response stream').selectOption('gaps-alternate');await wait();await settle();stable(initial,await geometry(),'actual stream selection with units/count changes');await page.getByLabel('Exact sample index for cursor').fill('7');await settle();assert.match(await page.locator('.tv-value').nth(2).innerText(),/ nA$/);await page.getByLabel('Response stream').selectOption('gaps-stream');await wait();
 const plot=page.locator('.tv-plot');await plot.focus();await page.keyboard.press('ArrowRight');await settle();assert.equal(await page.locator('.tv-value').first().innerText(),'1');
 await page.keyboard.press('+');await wait();assert.equal(await page.locator('.tv-window-navigation small').innerText(),'Samples 1–10,000 · zero-based, inclusive');
 await page.keyboard.press('Shift+ArrowRight');await wait();assert.equal(await page.locator('.tv-window-navigation small').innerText(),'Samples 5,001–15,000 · zero-based, inclusive');
 await page.keyboard.press('Home');await wait();
 const bounds=await plot.boundingBox();await page.mouse.move(bounds.x+130,bounds.y+80);await page.mouse.down();await page.mouse.move(bounds.x+210,bounds.y+80);await page.mouse.up();await wait();
 assert.notEqual(await page.locator('.tv-window-navigation small').innerText(),'Samples 0–19,999 · zero-based, inclusive');
 await page.getByRole('button',{name:'Pan',exact:true}).click();const zoomWindow=await page.locator('.tv-window-navigation small').innerText();await page.mouse.move(bounds.x+160,bounds.y+80);await page.mouse.down();await page.mouse.move(bounds.x+190,bounds.y+80);await page.mouse.up();await wait();assert.notEqual(await page.locator('.tv-window-navigation small').innerText(),zoomWindow);receipt.checks.push('actual cursor keyboard zoom/pan/reset and pointer drag zoom/pan');
 const scroll=page.locator('.inspection-detail');await scroll.hover();await page.mouse.wheel(0,350);await settle();assert.ok(await scroll.evaluate(e=>e.scrollTop>0));receipt.checks.push('native wheel scrolling retained');
 for(const theme of ['light','dark','fred','system']){
  await page.evaluate(t=>window.qaTheme(t),theme);await scroll.evaluate(e=>e.scrollTop=0);await page.evaluate(()=>document.activeElement?.blur());await page.mouse.move(995,995);await settle();
  const idle=await scroll.evaluate(e=>getComputedStyle(e,'::-webkit-scrollbar-thumb').backgroundColor);
  await plot.focus();await settle();const focus=await scroll.evaluate(e=>getComputedStyle(e,'::-webkit-scrollbar-thumb').backgroundColor);assert.notEqual(idle,focus);
  const bounds=await scroll.boundingBox();await page.mouse.move(bounds.x+bounds.width-4,bounds.y+50);await settle();await scroll.screenshot({path:path.join(output,`scrollbar-${theme}-hover-focus.png`)});receipt.screenshots.push(`scrollbar-${theme}-hover-focus.png`);receipt.checks.push(`${theme} scrollbar idle/focus themed colors`);
 }
 await page.emulateMedia({forcedColors:'active'});assert.equal(await scroll.evaluate(e=>getComputedStyle(e).scrollbarColor),'auto');receipt.checks.push('forced colors native affordance');
 assert.deepEqual(errors,[]);receipt.status='passed';
}catch(error){receipt.status='failed';receipt.error=String(error);throw error;}
finally{await writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');await browser?.close();await server?.close();}
console.log(JSON.stringify({status:receipt.status,checks:receipt.checks.length,output}));
