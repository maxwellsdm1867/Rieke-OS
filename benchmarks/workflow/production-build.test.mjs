/** Real production compilation and owned browser, with no scientific fixture. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {buildWorkflowProduction,productionMiddleware,attestProductionPage} from './production-runtime.mjs';
import {fixtureSource,installObserver} from './fixture-app.mjs';

test('exact workflow shell builds and loads production React through the unchanged Vite API proxy',async()=>{
 const source=path.resolve(import.meta.dirname,'../..'),output=await fs.mkdtemp(path.join(os.tmpdir(),'disco-workflow-production-build-'));
 const meta={project:'owned-build-test',protocol:'protocol',first_cell:'cell'};
 let vite,browser,backend;const received=[];
 try{
  const build=await buildWorkflowProduction(source,meta,output);
  assert.equal(await fs.readFile(path.join(output,'production-entry/fixture.jsx'),'utf8'),fixtureSource(meta));
  for(const name of ['src','node_modules'])await assert.rejects(fs.lstat(path.join(output,'production-entry',name)),{code:'ENOENT'});
  assert.ok(build.files['build-manifest.json']);
  assert.equal(build.files['index.html'].length,64);assert.ok(Object.keys(build.files).some(n=>n.endsWith('.js')));
  backend=http.createServer((req,res)=>{received.push({url:req.url,origin:req.headers.origin});res.setHeader('Content-Type','application/json');res.end(JSON.stringify({owned:true}));});
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));
  const {createServer}=await import(pathToFileURL(path.join(source,'workspace-app/src/test-support/isolatedVite.js')));
  const middleware=await productionMiddleware(output,build);
  vite=await createServer({root:path.join(source,'workspace-app'),configFile:false,logLevel:'error',optimizeDeps:{noDiscovery:true,include:[]},plugins:[{name:'test-owned-production',configureServer(s){s.middlewares.use(middleware);}}],server:{host:'127.0.0.1',port:0,hmr:false,proxy:{'/api':{target:`http://127.0.0.1:${backend.address().port}`,changeOrigin:true,configure(proxy){proxy.on('proxyReq',req=>req.removeHeader('origin'));}}}}});
  await vite.listen();const origin=`http://127.0.0.1:${vite.httpServer.address().port}`;
  const require=createRequire(path.join(source,'desktop/package.json')),{chromium}=require('playwright');
  browser=await chromium.launch({headless:true,...(process.env.WORKFLOW_BROWSER_EXECUTABLE?{executablePath:process.env.WORKFLOW_BROWSER_EXECUTABLE}:{}),args:['--no-first-run','--no-default-browser-check']});
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(installObserver,{phase:'ordinary',module_timing:false});
  await page.goto(origin+'/__workflow__');await page.getByRole('button',{name:'Benchmark Main',exact:true}).waitFor();
  const attestation=await attestProductionPage(page,build,origin);
  assert.equal(attestation.context.production,true);assert.equal(attestation.context.developmentOwnerCounter,false);
  assert.deepEqual(errors,[]);
  const response=await fetch(origin+'/api/proxy-probe',{headers:{Origin:'http://unrelated-origin'}});
  assert.deepEqual(await response.json(),{owned:true});assert.equal(received.find(r=>r.url==='/api/proxy-probe').origin,undefined);
  for(const url of ['/@vite/client','/src/App.jsx','/__workflow-production/%2e%2e%2fpackage.json'])assert.equal((await fetch(origin+url)).status,404);
  await page.evaluate(()=>window.__workflowProduction.production=false);
  await assert.rejects(attestProductionPage(page,build,origin),/attestation failed/);
 }finally{
  await browser?.close();await vite?.close();if(backend)await new Promise((resolve,reject)=>backend.close(e=>e?reject(e):resolve()));
  await fs.rm(output,{recursive:true,force:true});
 }
});


test('failed production build removes owned source/dependency symlinks',async()=>{
 const actual=path.resolve(import.meta.dirname,'../..'),directory=await fs.mkdtemp(path.join(os.tmpdir(),'disco-workflow-build-refusal-'));
 try{
  const source=path.join(directory,'source'),output=path.join(directory,'output');
  await fs.mkdir(path.join(source,'workspace-app/src'),{recursive:true});await fs.mkdir(output);
  await fs.symlink(await fs.realpath(path.join(actual,'workspace-app/node_modules')),path.join(source,'workspace-app/node_modules'),'dir');
  await assert.rejects(buildWorkflowProduction(source,{project:'missing-product-modules'},output));
  for(const name of ['src','node_modules'])await assert.rejects(fs.lstat(path.join(output,'production-entry',name)),{code:'ENOENT'});
  assert.equal(await fs.readFile(path.join(output,'production-entry/fixture.jsx'),'utf8'),fixtureSource({project:'missing-product-modules'}));
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});
