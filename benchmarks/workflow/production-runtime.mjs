/** Owned production bundle of the exact workflow shell; no product bootstrap substitution. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {fixtureSource} from './fixture-app.mjs';

export const productionRuntime='vite-proxy-react-production-v1';
export const assetBase='/__workflow-production/';
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
export function runtimeOption(runtime='production',profile=false){
 if(!['production','development'].includes(runtime))throw Error('runtime must be production or development');
 if(profile&&runtime!=='development')throw Error('--profile requires explicit --runtime development; production React does not collect Profiler callbacks');
 return runtime;
}

export async function buildWorkflowProduction(source,meta,output,entrySource=fixtureSource(meta)){
 const workspace=path.join(source,'workspace-app'),require=createRequire(path.join(workspace,'package.json'));
 const {build}=await import(pathToFileURL(require.resolve('vite')));
 const {default:react}=await import(pathToFileURL(path.join(workspace,'node_modules/@vitejs/plugin-react/dist/index.js')));
 const root=path.join(output,'production-entry'),outDir=path.join(output,'production-dist');
 await fs.mkdir(root,{recursive:false});
 try{
 await fs.symlink(path.join(workspace,'src'),path.join(root,'src'),'dir');
 await fs.symlink(await fs.realpath(path.join(workspace,'node_modules')),path.join(root,'node_modules'),'dir');
 const fixture=entrySource,fixtureHash=sha(fixture);
 await fs.writeFile(path.join(root,'fixture.jsx'),fixture);
 const reactVersion=JSON.parse(await fs.readFile(path.join(workspace,'node_modules/react/package.json'),'utf8')).version;
 await fs.writeFile(path.join(root,'attestation.js'),`import React from 'react';\nwindow.__workflowProduction={mode:import.meta.env.MODE,production:import.meta.env.PROD,react:React.version,developmentOwnerCounter:'recentlyCreatedOwnerStacks' in React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE,fixture_sha256:${JSON.stringify(fixtureHash)}};\n`);
 await fs.writeFile(path.join(root,'entry.jsx'),"import './attestation.js';\nimport './fixture.jsx';\n");
 await fs.writeFile(path.join(root,'index.html'),'<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="root"></div><script type="module" src="/entry.jsx"></script></body></html>');
 await build({root,configFile:false,mode:'production',base:assetBase,logLevel:'error',plugins:[react()],define:{'process.env.NODE_ENV':JSON.stringify('production')},build:{outDir,emptyOutDir:false,minify:true,sourcemap:false,manifest:'build-manifest.json'}});
 const files={};async function visit(dir){for(const item of await fs.readdir(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory())await visit(file);else if(item.isFile())files[path.relative(outDir,file).split(path.sep).join('/')]=sha(await fs.readFile(file));else throw Error('Non-regular production asset');}}
 await visit(outDir);
 const record={runtime:productionRuntime,asset_base:assetBase,fixture_sha256:fixtureHash,react_version:reactVersion,files};
 await fs.writeFile(path.join(output,'production-build.json'),JSON.stringify(record,null,2)+'\n');
 return record;
 }finally{
  // These are owned build-time links, never evidence or artifact contents.
  for(const name of ['src','node_modules'])try{await fs.unlink(path.join(root,name));}catch(error){if(error.code!=='ENOENT')throw error;}
 }
}

// Only files from the immutable build manifest are served. Neither /src nor
// arbitrary filesystem paths can fall through to development transformation.
export async function productionMiddleware(output,build){
 const assets=new Map();
 for(const [name,hash] of Object.entries(build.files)){
  if(!name||name.includes('\\')||name.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Invalid production asset name');
  const file=path.join(output,'production-dist',name),stat=await fs.lstat(file);
  if(!stat.isFile()||stat.isSymbolicLink())throw Error('Invalid production asset');
  const bytes=await fs.readFile(file);if(sha(bytes)!==hash)throw Error('Production asset changed');
  assets.set(name,bytes);
 }
 if(!assets.has('index.html'))throw Error('Production index missing');
 return (req,res,next)=>{
  const raw=(req.url||'').split('?')[0];
  if(raw.startsWith('/api/')||raw==='/api')return next();
  let name;
  try{
   const decoded=decodeURIComponent(raw);
   if(decoded.includes('\\')||decoded.includes('\0')||decoded.split('/').some(p=>p==='.'||p==='..'))throw Error('Invalid path');
   name=decoded==='/__workflow__'?'index.html':decoded.startsWith(assetBase)?decoded.slice(assetBase.length):null;
  }catch{}
  if(!['GET','HEAD'].includes(req.method)||!name||!assets.has(name)){res.statusCode=404;res.end('Not found');return;}
  const type=name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':name.endsWith('.svg')?'image/svg+xml':name.endsWith('.json')?'application/json':'application/octet-stream';
  res.setHeader('Content-Type',type);res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Cache-Control','no-cache');
  res.end(req.method==='HEAD'?undefined:assets.get(name));
 };
}

export async function attestProductionPage(page,build,origin){
 const observed=await page.evaluate(()=>({context:window.__workflowProduction,scripts:[...document.querySelectorAll('script[src]')].map(n=>n.src),resources:performance.getEntriesByType('resource').filter(e=>['script','link','css'].includes(e.initiatorType)).map(e=>e.name)}));
 const c=observed.context;
 if(!c||c.mode!=='production'||c.production!==true||c.developmentOwnerCounter!==false||c.react!==build.react_version||c.fixture_sha256!==build.fixture_sha256)throw Error('Production workflow attestation failed');
 if(!observed.scripts.length)throw Error('Production workflow scripts missing');
 for(const url of [...observed.scripts,...observed.resources]){
  const parsed=new URL(url);if(parsed.origin!==origin||!parsed.pathname.startsWith(assetBase)||!Object.hasOwn(build.files,parsed.pathname.slice(assetBase.length)))throw Error('Unattested workflow asset: '+url);
 }
 return observed;
}
