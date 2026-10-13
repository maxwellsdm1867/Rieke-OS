import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const options={};for(let i=2;i<process.argv.length;i+=2)options[process.argv[i].slice(2)]=process.argv[i+1];
const root=path.resolve(options['source-root']),workspace=path.join(root,'workspace-app');
const meta=JSON.parse(await fs.readFile(options['server-json'],'utf8'));
const cached=existsSync(path.join(workspace,'src/protocol-overview/useOverviewResource.js'));
const require=createRequire(path.join(root,'desktop/package.json'));
const {chromium}=require('playwright');
const {createServer}=await import(pathToFileURL(path.join(workspace,'src/test-support/isolatedVite.js')));
const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
const entry=path.join(workspace,'__overview_owned__.jsx');
const source=`import React,{useState} from 'react';import {createRoot} from 'react-dom/client';
import {Protocol} from '/src/App.jsx';import Overview from '/src/protocol-overview/ui/Overview.jsx';
import {AnnotationProfileProvider} from '/src/annotations/annotationProfile.js';
import {TreeBranchReadOwner} from '/src/tree-ancestors/treeBranchReads.jsx';
import {api,useResource} from '/src/api.js';import {useSummaryRevision} from '/src/useWorkspaceChanges.js';
${cached?"import {useOverviewCache,useOverviewResource} from '/src/protocol-overview/useOverviewResource.js';":''}
import '/src/styles.css';import '/src/themes.css';
const meta=${JSON.stringify(meta)};
function Shell(){const[mode,setMode]=useState('idle'),[revision,setRevision]=useState(0),[projectOpened,setProjectOpened]=useState(false);const overviewRevision=useSummaryRevision(revision,mode==='project',0);
${cached?"const overviewCache=useOverviewCache(meta.project,revision,0);const project=useOverviewResource(projectOpened?'/overview':null,overviewRevision,{cache:overviewCache,scope:meta.project});":"const overviewCache=undefined;const project=useResource(projectOpened?'/overview':null,overviewRevision);"}
async function change(){try{const summary=await api('/protocols/'+meta.protocol);const selected=await api('/protocols/'+meta.protocol+'/curation/read',{method:'POST',body:{epoch_uuids:[meta.first_epoch],query_revision:summary.query_revision,expected_binding_version:summary.expected_binding_version,selection_scope:{filters:{},cell_uuid:null}}});await api('/protocols/'+meta.protocol+'/curation',{method:'POST',body:{epoch_uuids:[meta.first_epoch],query_revision:summary.query_revision,expected_binding_version:summary.expected_binding_version,selection_scope:{filters:{},cell_uuid:null},expected_revisions:{[meta.first_epoch]:selected.epochs[0].curation_revision},changes:{included:false}}});setRevision(n=>n+1);window.__overview.changed=true;}catch(error){window.__overview.error=error.message;}}
return <AnnotationProfileProvider projectId={meta.project}><TreeBranchReadOwner projectId={meta.project} revision={revision}><header><button onClick={()=>setMode('protocol')}>Open protocol</button><button onClick={()=>{setProjectOpened(true);setMode('project');}}>Open project overview</button><button onClick={()=>setMode('idle')}>Away</button><button onClick={change}>Change inclusion</button></header>{mode==='protocol'?<Protocol key='protocol' id={meta.protocol} projectId={meta.project} overviewCache={overviewCache} revision={revision} structureRevision={0} onChange={()=>setRevision(n=>n+1)}/>:mode==='project'?project.data?<Overview data={project.data} overviewCache={overviewCache} revision={revision} onProtocol={()=>setMode('protocol')}/>:<p>{project.error||'Loading project'}</p>:<p>Owned fixture</p>}</TreeBranchReadOwner></AnnotationProfileProvider>;}
createRoot(document.getElementById('root')).render(<Shell/>);`;
let server,browser,context;const receipt={cached,epochs:meta.epochs,active_epochs:180,samples:[],errors:[],limitations:['Synthetic SQL and metadata admission; production HTTP and React components.','Development Chromium DOM/two RAF timing, not native Electron paint.','First page includes module loading; backend caches persist between samples.']};
try{
 server=await createServer({root:workspace,configFile:false,logLevel:'error',plugins:[react(),{name:'owned-overview',resolveId(id){if(id==='/__overview_owned__.jsx')return entry;},load(id){if(id===entry)return source;},configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url!=='/__overview__')return next();res.setHeader('Content-Type','text/html');res.end('<div id="root"></div><script type="module" src="/__overview_owned__.jsx"></script>');});}}],server:{host:'127.0.0.1',port:0,hmr:false,proxy:{'/api':{target:`http://127.0.0.1:${meta.port}`,changeOrigin:true,configure(proxy){proxy.on('proxyReq',req=>req.removeHeader('origin'));}}}}});
 await server.listen();
 browser=await chromium.launch({headless:true,executablePath:process.env.WORKFLOW_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});receipt.environment={node:process.version,browser:browser.version(),viewport:{width:1500,height:1100}};
 for(let i=0;i<5;i++){
  context=await browser.newContext({viewport:receipt.environment.viewport});const page=await context.newPage();
  page.on('pageerror',error=>receipt.errors.push(error.message));
  await page.addInitScript(()=>{
   window.__overview={requests:[],changed:false,error:null};const original=window.fetch;
   window.fetch=async(input,options={})=>{const record={url:String(input),start:performance.now(),method:options.method||'GET'};window.__overview.requests.push(record);const response=await original(input,options);record.status=response.status;record.end=performance.now();return response;};
  });
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__overview__`);
  async function measure(action,button,mode,included=i===0?180:179){
   await page.getByRole('button',{name:button,exact:true}).evaluate(el=>{window.__overview.start=performance.now();window.__overview.begin=window.__overview.requests.length;el.click();});
   await page.waitForFunction(({mode,included})=>{
    const w=window.__overview;if(w.error)throw Error(w.error);if(w.requests.some(r=>r.status>=400))throw Error('Fixture HTTP request failed');
    const node=document.querySelector(mode==='protocol'?'.protocol-infographic .pi-metrics':'.ov-metric-ribbon');
    if(!node)return false;
    const count=[...node.children].find(el=>[...el.querySelectorAll('span')].some(n=>n.textContent.trim()===(mode==='protocol'?'Epochs':'Recorded epochs')))?.querySelector('strong')?.textContent.replaceAll(',','');
    if(count!==(mode==='protocol'?'180':String(window.__overview.projectEpochs)))return false;
    if(mode==='protocol'&&!node.textContent.includes(included+' included'))return false;
    if(!w.ready){w.ready=performance.now();w.frames=0;}
    if(++w.frames<2)return false;
    w.elapsed=performance.now()-w.start;return true;
   },{mode,included},{polling:'raf',timeout:180000});
   const sample=await page.evaluate(()=>({ms:window.__overview.elapsed,requests:window.__overview.requests.slice(window.__overview.begin).map(({url,method,status})=>({url,method,status}))}));
   sample.action=action;sample.sample=i;receipt.samples.push(sample);console.log(JSON.stringify(sample));
   await page.waitForLoadState('networkidle');
   await page.evaluate(()=>{window.__overview.ready=null;window.__overview.frames=0;});
  }
  await page.evaluate(epochs=>window.__overview.projectEpochs=epochs,meta.epochs);
  await measure('protocol.cold','Open protocol','protocol');
  await page.getByRole('button',{name:'Away',exact:true}).click();
  await measure('protocol.cached_return','Open protocol','protocol');
  await page.getByRole('button',{name:'Away',exact:true}).click();
  await measure('project.cold','Open project overview','project');
  await page.getByRole('button',{name:'Away',exact:true}).click();
  await measure('project.cached_return','Open project overview','project');
  // The source fixture is not reset between browser samples. Only sample zero
  // measures a real inclusion edit; subsequent cold/return counts reflect it.
  if(i===0){
   await page.getByRole('button',{name:'Away',exact:true}).click();
   await page.getByRole('button',{name:'Change inclusion',exact:true}).click();
   await page.waitForFunction(()=>{if(window.__overview.error)throw Error(window.__overview.error);return window.__overview.changed;},{},{timeout:180000});
   await measure('protocol.after_change','Open protocol','protocol',179);
  }
  await context.close();context=null;
 }
 if(receipt.errors.length)throw Error(receipt.errors.join('\n'));
 receipt.medians=Object.fromEntries([...new Set(receipt.samples.map(s=>s.action))].map(action=>{const values=receipt.samples.filter(s=>s.action===action).map(s=>s.ms).sort((a,b)=>a-b);return [action,values[Math.floor(values.length/2)]];}));
 receipt.status='passed';
}finally{
 await context?.close();await browser?.close();await server?.close();await fs.writeFile(options.output,JSON.stringify(receipt,null,2));
}
