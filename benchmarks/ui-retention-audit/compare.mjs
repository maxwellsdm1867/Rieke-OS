/** Compose captured screenshots and compare recorded geometry; no app clicks. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const args={};for(let i=2;i<process.argv.length;i+=2)args[process.argv[i].slice(2).replaceAll('-','_')]=process.argv[i+1];
for(const key of ['baseline','candidate','source_root','output'])if(!args[key])throw Error(`Missing ${key}`);
const output=path.resolve(args.output);await fs.mkdir(output,{recursive:true});
const paths={baseline:path.resolve(args.baseline),candidate:path.resolve(args.candidate)},receipts={};
for(const name of Object.keys(paths))receipts[name]=JSON.parse(await fs.readFile(paths[name],'utf8'));
const key=row=>`${row.profile}.${row.id}`,maps=Object.fromEntries(Object.entries(receipts).map(([name,value])=>[name,new Map(value.checks.map(row=>[key(row),row]))]));
const escape=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const compare={format:'disco-ui-retention-visual-comparison-v1',status:'captured-for-review',baseline:paths.baseline,candidate:paths.candidate,visual_review_required:true,comparisons:[],sheets:[],limitations:['Geometry and screenshot differences require human interpretation; no pixel score substitutes for visual review.','Fixture paths, UUIDs and times may differ. No screenshot masks or DOM rewriting hide those differences.']};
const ordered=[...new Set([...maps.baseline.keys(),...maps.candidate.keys()])];
async function screenshot(name,row){if(!row?.screenshot)return null;const filename=path.join(path.dirname(paths[name]),row.screenshot);return `data:image/png;base64,${(await fs.readFile(filename)).toString('base64')}`;}
for(const id of ordered){const baseline=maps.baseline.get(id),candidate=maps.candidate.get(id),changes=[];
 const a=baseline?.snapshot?.geometry||{},b=candidate?.snapshot?.geometry||{};
 for(const selector of new Set([...Object.keys(a),...Object.keys(b)])){const left=a[selector]||[],right=b[selector]||[];if(left.length!==right.length)changes.push({selector,type:'visible-count',baseline:left.length,candidate:right.length});for(let i=0;i<Math.min(left.length,right.length);i++){const deltas={};for(const property of ['x','y','width','height','scrollTop','scrollLeft']){const delta=right[i][property]-left[i][property];if(Math.abs(delta)>.5)deltas[property]={baseline:left[i][property],candidate:right[i][property],delta};}if(Object.keys(deltas).length)changes.push({selector,index:i,type:'geometry',deltas});}}
 compare.comparisons.push({id,baseline_status:baseline?.status??'missing',candidate_status:candidate?.status??'missing',baseline_error:baseline?.error,candidate_error:candidate?.error,geometry_changes:changes,baseline_alerts:baseline?.snapshot?.alerts||[],candidate_alerts:candidate?.snapshot?.alerts||[],baseline_request_count:baseline?.requests?.length,candidate_request_count:candidate?.requests?.length,baseline_retention:baseline?.snapshot?.retention,candidate_retention:candidate?.snapshot?.retention,images:{baseline:await screenshot('baseline',baseline),candidate:await screenshot('candidate',candidate)}});
}
const require=createRequire(path.join(path.resolve(args.source_root),'desktop/package.json')),{chromium}=require('playwright');let browser;
const css=`*{box-sizing:border-box}body{margin:0;font:15px system-ui;background:#e9edf1;color:#17202c}header{padding:12px 20px;background:#fff;border-bottom:1px solid #a6b0ba}h1{font-size:20px;margin:0 0 5px}p{margin:3px 0;font-size:13px}.pair{margin:12px;background:white;border:1px solid #9aa7b6;break-inside:avoid}.pair h2{font-size:15px;margin:0;padding:10px 12px}.images{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#a6b0ba}.side{background:#fff;min-width:0}.label{padding:6px 10px;font-weight:650;border-top:1px solid #a6b0ba;font-size:12px}.side img{display:block;width:100%;height:auto}.missing{height:180px;padding:20px}.finding{color:#a42323}.note{padding:8px 12px;font-size:12px}`;
const pairHTML=row=>`<section class="pair"><h2>${escape(row.id)}</h2><div class="images">${['baseline','candidate'].map(name=>`<div class="side"><div class="label ${row[`${name}_status`]==='failed'?'finding':''}">${name.toUpperCase()} · ${escape(row[`${name}_status`])}</div>${row.images[name]?`<img src="${row.images[name]}" alt="${name} ${escape(row.id)}">`:'<div class="missing">No screenshot available</div>'}</div>`).join('')}</div><div class="note">${row.geometry_changes.length} measured geometry changes. ${escape(row.candidate_error||row.baseline_error||'Review both images at full size; differences are not automatically defects.')}</div></section>`;
try{browser=await chromium.launch({headless:true,...(args.browser_executable?{executablePath:args.browser_executable}:{})});const page=await browser.newPage({viewport:{width:1500,height:1100},deviceScaleFactor:1});
 const rows=compare.comparisons.filter(row=>row.images.baseline||row.images.candidate);
 for(let i=0;i<rows.length;i+=4){const batch=rows.slice(i,i+4),name=`sheet-${String(i/4+1).padStart(2,'0')}`;const html=`<!doctype html><style>${css}</style><header><h1>Disco retained UI · baseline / candidate</h1><p>Actual-control screenshots, owned 1,000-epoch fixture · sheet ${i/4+1}</p></header>${batch.map(pairHTML).join('')}`;
  const file=path.join(output,`${name}.html`);await fs.writeFile(file,html);await page.goto(pathToFileURL(file).href);await page.evaluate(()=>Promise.all([...document.images].map(img=>img.decode())));await page.screenshot({path:path.join(output,`${name}.png`),fullPage:true});compare.sheets.push({html:`${name}.html`,image:`${name}.png`,checks:batch.map(row=>row.id)});
 }
 // One browsable report retains every full image and links each observation.
 const report=`<!doctype html><style>${css}</style><header><h1>Disco UI comparison</h1><p>${rows.length} paired checkpoints. Baseline: ${escape(receipts.baseline.label)}. Candidate: ${escape(receipts.candidate.label)}.</p><p>This is evidence for review, not a claim that every screen is identical or release-qualified.</p></header>${rows.map(pairHTML).join('')}`;await fs.writeFile(path.join(output,'comparison.html'),report);
 await page.close();
}finally{await browser?.close();}
for(const row of compare.comparisons)delete row.images;
await fs.writeFile(path.join(output,'comparison.json'),JSON.stringify(compare,null,2));console.log(path.join(output,'comparison.html'));
