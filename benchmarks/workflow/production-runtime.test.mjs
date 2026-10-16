import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {runtimeOption,productionRuntime,productionMiddleware,attestProductionPage} from './production-runtime.mjs';
import {inventory,options} from './browser.mjs';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const required=['--source-root','source','--server-json','fixture.json','--output','output'];

test('ordinary defaults to production; profiling requires explicit development',()=>{
 assert.equal(options(required).runtime,'production');
 assert.equal(options([...required,'--runtime','development','--profile','true']).profile,true);
 assert.throws(()=>options([...required,'--profile','true']),/requires explicit/);
 assert.throws(()=>runtimeOption('unknown'),/runtime must/);
 assert.equal(options([...required,'--module-timing','true']).module_timing,true);
});

test('migration retains fifteen variants, three samples and original comparison policy',async()=>{
 assert.deepEqual(inventory,[['view.open','cold-component'],['view.return','warm-resource'],['tree.open','main-columns'],['tree.expand','main-first-cell'],['tree.next_page','main-cell-epochs'],['tree.split_change','remove-epoch-block'],['tree.selection','incoming-select-all'],['tree.selection','incoming-deselect-all'],['predicate.search','cell-equality'],['workbench.prepare','fresh'],['workbench.prepare','receipt-replay'],['workbench.open','prepared-return'],['trace.inspect','first-owned-waveform'],['trace.inspect','frozen-workbench-300k'],['trace.inspect','frozen-workbench-1m']]);
 const registry=JSON.parse(await fs.readFile(new URL('../registry.json',import.meta.url),'utf8'));
 const config=registry.stress_tracks['workflow-million'];
 assert.ok(config,'workflow configuration required');assert.equal(config.samples,3);assert.deepEqual(config.comparison,{relative:0.25,absolute_ms:5});
});

async function fixture(t){
 const output=await fs.mkdtemp(path.join(os.tmpdir(),'disco-production-assets-'));t.after(()=>fs.rm(output,{recursive:true,force:true}));
 await fs.mkdir(path.join(output,'production-dist/assets'),{recursive:true});
 const files={'index.html':'<script type="module" src="/__workflow-production/assets/entry.js"></script>','assets/entry.js':'production compiled bytes'};
 for(const[n,b]of Object.entries(files))await fs.writeFile(path.join(output,'production-dist',n),b);
 const build={runtime:productionRuntime,asset_base:'/__workflow-production/',fixture_sha256:'a'.repeat(64),react_version:'fixture',files:Object.fromEntries(Object.entries(files).map(([n,b])=>[n,hash(b)]))};
 return {output,build};
}
function request(serve,url,method='GET'){
 const r={statusCode:200,headers:{},next:false,setHeader(k,v){this.headers[k]=v;},end(body){this.body=body;}};
 serve({url,method},r,()=>{r.next=true;});return r;
}
test('production middleware serves only hashed files and preserves API proxy passage',async t=>{
 const {output,build}=await fixture(t),serve=await productionMiddleware(output,build);
 assert.match(String(request(serve,'/__workflow__').body),/script/);
 assert.equal(request(serve,'/__workflow-production/assets/entry.js').headers['Content-Type'],'text/javascript');
 assert.equal(request(serve,'/__workflow-production/assets/entry.js','HEAD').body,undefined);
 assert.equal(request(serve,'/api/tree-pages?x=1','POST').next,true);
 for(const url of ['/src/App.jsx','/@vite/client','/__workflow-production/../secret','/__workflow-production/%2e%2e/secret','/__workflow-production/%2e%2e%2fsecret','/__workflow-production/assets%5csecret','/__workflow-production/%00','/__workflow-production/%','/__workflow-production/assets/missing.js'])assert.equal(request(serve,url).statusCode,404,url);
 assert.equal(request(serve,'/__workflow__','POST').statusCode,404);
});
test('production middleware refuses mutated files and symlink assets',async t=>{
 const {output,build}=await fixture(t),file=path.join(output,'production-dist/assets/entry.js');
 await fs.writeFile(file,'changed');await assert.rejects(productionMiddleware(output,build),/changed/);
 await fs.unlink(file);await fs.symlink('../index.html',file);await assert.rejects(productionMiddleware(output,build),/Invalid production asset/);
});
test('production attestation refuses dev React, wrong fixture and foreign or dev scripts',async()=>{
 const build={react_version:'fixture',fixture_sha256:'a'.repeat(64),files:{'assets/app.js':'b'.repeat(64)}};
 const good={context:{production:true,mode:'production',developmentOwnerCounter:false,react:'fixture',fixture_sha256:build.fixture_sha256},scripts:['http://127.0.0.1:1234/__workflow-production/assets/app.js'],resources:[]};
 assert.deepEqual(await attestProductionPage({evaluate:async()=>good},build,'http://127.0.0.1:1234'),good);
 for(const change of [v=>v.context.developmentOwnerCounter=true,v=>v.context.production=false,v=>v.context.fixture_sha256='changed',v=>v.scripts=[],v=>v.scripts.push('http://127.0.0.1:1234/@vite/client'),v=>v.resources.push('http://foreign/assets.js')]){
  const value=structuredClone(good);change(value);await assert.rejects(attestProductionPage({evaluate:async()=>value},build,'http://127.0.0.1:1234'));
 }
});
