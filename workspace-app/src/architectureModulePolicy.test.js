import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,copyFileSync,rmSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {analyze} from '../architectureImports.mjs';

function fixture(){
 const root=mkdtempSync(join(tmpdir(),'disco-module-policy-'));
 const write=(name,value)=>{mkdirSync(join(root,name,'..'),{recursive:true});writeFileSync(join(root,name),typeof value==='string'?value:JSON.stringify(value));};
 const s='workspace-app/src/';
 const policy={additional_sources:[],tool_external_imports:[],virtual_import_edges:[],source_root:s.slice(0,-1),test_support_roots:[s+'test-support'],test_tool_files:[],package_manifest:'workspace-app/package.json',package_lock:'workspace-app/package-lock.json',resolver_config:{path:'workspace-app/vite.config.js',sha256:createHash('sha256').update('export default {};').digest('hex')},dom_override_test_files:[],modules:[{contract_id:'presentation',root:s+'presentation',public_entry:s+'presentation/public.js',public_exports:['factory'],private_test_edges:[{from:s+'presentation/internal/helper.test.js',to:s+'presentation/internal/helper.js'}]}]};
 const catalog={format:'disco-adopted-port-checks',version:2,discovery:[{from:'AGENTS.md',to:'docs/contract.md'}],shared_paths:['docs/**'],javascript_module_policy:policy,contracts:[{id:'presentation',contract:{path:'docs/contract.md',heading:'Presentation'},affected_paths:['workspace-app/**'],rules:[{language:'javascript',file:s+'presentation/public.js',allow:[s+'presentation/internal/helper.js']},{language:'javascript',file:s+'presentation/internal/helper.js',allow:[]}],tests:{python:[],javascript:[s+'presentation/public.test.js']}}]};
 write('AGENTS.md','[Contract](docs/contract.md)');write('docs/contract.md','# Presentation');
 write('workspace-app/package.json',{type:'module',dependencies:{react:'19.3.0'},devDependencies:{jsdom:'26.1.0'}});write('workspace-app/package-lock.json',{});write('workspace-app/vite.config.js','export default {};');
 write(s+'test-support/preload.js','export {};');write(s+'presentation/public.js',"import {value} from './internal/helper.js';export function factory(){return value;}");write(s+'presentation/internal/helper.js','export const value=1;');
 write(s+'presentation/public.test.js',"import {factory} from './public.js';");write(s+'presentation/internal/helper.test.js',"import {value} from './helper.js';");write(s+'consumer.js',"import {factory} from './presentation/public.js';");
 for(const name of ['architectureImports.mjs','runTests.mjs'])copyFileSync(fileURLToPath(new URL('../'+name,import.meta.url)),join(root,'workspace-app',name));
 mkdirSync(join(root,'tools'));copyFileSync(fileURLToPath(new URL('../../tools/architecture_module_policy.py',import.meta.url)),join(root,'tools/architecture_module_policy.py'));
 symlinkSync(fileURLToPath(new URL('../node_modules',import.meta.url)),join(root,'workspace-app/node_modules'),'dir');
 const check=(options={})=>{
  write('docs/architecture/adopted-port-checks.json',catalog);
  const env={...process.env,...options.env};
  const run=spawnSync('python3',['-B',fileURLToPath(new URL('../../tools/architecture_guard.py',import.meta.url)),'check','--root',root,'--language',options.language??'javascript','--node',process.execPath],{encoding:'utf8',env});
  assert.ifError(run.error);let result;try{result=JSON.parse(run.stdout);}catch{throw Error(run.stdout+run.stderr);}return {exit:run.status,result};
 };
 return {root,s,write,policy,catalog,check,close:()=>rmSync(root,{recursive:true,force:true})};
}
function fails(f,pattern){const r=f.check();assert.equal(r.exit,1,JSON.stringify(r));assert.match(r.result.error,pattern);}

test('new outside consumers cannot bypass private imports with normalization, extensions, exports or loaders',()=>{
 const f=fixture();try{
  assert.equal(f.check().exit,0);
  for(const source of ["import './presentation/internal/helper.js'", "import './presentation/../presentation/internal/helper'", "export {value as leaked} from './presentation/internal/helper.js'", "export * from './presentation/internal/helper.js'", "async function f(){return import('./presentation/internal/helper.js')}" ,"require('./presentation/internal/helper')", "module.require('./presentation/internal/helper.js')"]){
   f.write(f.s+'new-consumer.js',source);fails(f,/forbidden private/);
  }
  f.write(f.s+'bridge.js',"export * from './presentation/internal/helper.js'");f.write(f.s+'new-consumer.js',"export * from './bridge.js'");fails(f,/forbidden private/);
 }finally{f.close();}
});
test('absolute, URL, aliases, suffixes, symlinks and changed resolver configuration fail closed',()=>{
 const f=fixture();try{
  for(const path of ['/src/presentation/internal/helper.js','file:///src/presentation/internal/helper.js','@local/presentation','./presentation/internal/helper.js?raw','./presentation/internal/helper.js#x']){
   f.write(f.s+'new.js',`import ${JSON.stringify(path)}`);fails(f,/unreviewed|undeclared/);
  }
  f.write(f.s+'new.js','export {};');symlinkSync(join(f.root,f.s,'presentation/internal/helper.js'),join(f.root,f.s,'alias.js'));fails(f,/symlink/);rmSync(join(f.root,f.s,'alias.js'));
  f.write('workspace-app/vite.config.js','export default {resolve:{alias:{bad:"/src"}}};');fails(f,/Resolver config changed/);
  f.write('workspace-app/vite.config.js','export default {};');f.write('workspace-app/jsconfig.json','{}');fails(f,/Unreviewed resolver config/);
 }finally{f.close();}
});
test('private test exceptions cannot grant outside tests or production access and cannot be broadened or unused',()=>{
 const f=fixture();try{
  assert.equal(f.check().exit,0);
  f.write(f.s+'outside.test.js',"import './presentation/internal/helper.js'");fails(f,/forbidden private/);
  f.write(f.s+'outside.test.js','export {};');f.write(f.s+'consumer.js',"import './presentation/internal/helper.test.js'");fails(f,/production cannot import test/);
  f.write(f.s+'consumer.js',"import './presentation/public.js'");
  const edges=f.policy.modules[0].private_test_edges,old=edges[0];edges[0]={from:f.s+'consumer.js',to:old.to};fails(f,/Private test edge/);edges[0]=old;
  edges.push(old);fails(f,/Duplicate/);edges.pop();
  f.write(old.from,'export {};');fails(f,/Unused private test/);
 }finally{f.close();}
});
test('all new module production files need ownership rules and public re-exports are rejected',()=>{
 const f=fixture();try{
  f.write(f.s+'presentation/new.js','export {};');fails(f,/needs an ownership allow rule/);rmSync(join(f.root,f.s+'presentation/new.js'));
  for(const source of ["export * from './internal/helper.js'","export {value as factory} from './internal/helper.js'","export function factory(){};export const leaked=1;","export default function factory(){}"]){
   f.write(f.s+'presentation/public.js',source);fails(f,/public export surface/);
  }
 }finally{f.close();}
});
test('computed loaders, import.meta.glob and parser failure remain closed; object policy keys are not loaders',()=>{
 assert.deepEqual(analyze('fixture.js','const policy={require:["public.js"]};').dependencies,[]);
 for(const source of ['const load=require;load(name)','import(name)',"module['re'+'quire']('./presentation/internal/helper.js')","module[key]('./presentation/internal/helper.js')","import.meta['g'+'lob']('./**/*.js')",'import.meta.glob("./**/*.js")','import.meta["glob"]("./**/*.js")'])assert.throws(()=>analyze('fixture.js',source),/loader|Computed/);
 const f=fixture();try{
  f.write(f.s+'new.js','const files=import.meta.glob("./presentation/**/*.js")');fails(f,/glob loader/);
  f.write(f.s+'new.js','export {};');f.write('workspace-app/architectureImports.mjs',"import 'unavailable-parser'");fails(f,/parser unavailable or failed/);
 }finally{f.close();}
});
test('DOM exception is exact, test-only and rejects even empty environment overrides',()=>{
 const f=fixture();try{
  const name=f.s+'dom.test.js';f.policy.dom_override_test_files.push(name);const source="const {JSDOM}=await import(process.env.RIEKE_TEST_DOM_MODULE||'jsdom');";f.write(name,source);
  assert.equal(f.check().exit,0);
  for(const value of ['', 'jsdom']){const r=f.check({env:{RIEKE_TEST_DOM_MODULE:value}});assert.equal(r.exit,1);assert.match(r.result.error,/must be unset/);}
  f.write(name,source+source.replace('const {JSDOM}','const other'));fails(f,/exactly one/);
  f.write(name,"import(process.env.OTHER||'jsdom')");fails(f,/Computed/);
 }finally{f.close();}
});
test('catalog versions cannot silently omit or activate module policy',()=>{
 const f=fixture();try{
  f.catalog.version=1;fails(f,/version 1 forbids/);
  delete f.catalog.javascript_module_policy;assert.equal(f.check().exit,0);
  f.catalog.version=2;fails(f,/version 2 requires/);
 }finally{f.close();}
});

test('an unscanned outside bridge, noncanonical policy root and symlinked resolver cannot weaken policy',()=>{
 const f=fixture();try{
  f.write('workspace-app/bridge.js',"export * from './src/presentation/internal/helper.js'");
  f.write(f.s+'consumer.js',"import '../bridge.js'");fails(f,/outside scanned sources/);
  f.write(f.s+'consumer.js',"import './presentation/public.js'");
  const root=f.policy.modules[0].root;f.policy.modules[0].root='workspace-app/src/./presentation';fails(f,/Invalid module policy path/);f.policy.modules[0].root=root;
  f.write('unowned-config.json','{}');symlinkSync(join(f.root,'unowned-config.json'),join(f.root,'workspace-app/jsconfig.json'));fails(f,/config symlink/);
 }finally{f.close();}
});

test('listed outside tooling is analyzed, cannot expose private code, and cannot be imported by production',()=>{
 const f=fixture();try{
  const tool='workspace-app/tool.mjs';f.policy.additional_sources.push(tool);f.policy.test_tool_files.push(tool);f.write(tool,'export const tool=1;');
  f.write(f.s+'tool.test.js',"import '../tool.mjs'");assert.equal(f.check().exit,0);
  f.write(tool,"export * from './src/presentation/internal/helper.js'");fails(f,/forbidden private/);
  f.write(tool,'export const tool=1;');f.write(f.s+'consumer.js',"import '../tool.mjs'");fails(f,/production cannot import test/);
 }finally{f.close();}
});
test('tool external import is exact, registry-pinned, used, and never grants general transitive access',()=>{
 const f=fixture();try{
  const tool='workspace-app/tool.mjs';f.policy.additional_sources.push(tool);f.policy.test_tool_files.push(tool);f.write(tool,"import 'rolldown/utils'");
  const locked=JSON.parse(readFileSync(fileURLToPath(new URL('../package-lock.json',import.meta.url)),'utf8')).packages['node_modules/rolldown'];
  f.write('workspace-app/package-lock.json',{packages:{'node_modules/rolldown':locked}});
  const edge={from:tool,specifier:'rolldown/utils',lock_package:'node_modules/rolldown'};f.policy.tool_external_imports.push(edge);
  assert.equal(f.check().exit,0);
  f.write(f.s+'transitive.test.js',"import 'rolldown/utils'");fails(f,/undeclared package/);f.write(f.s+'transitive.test.js','export {};');
  f.write(tool,"import 'rolldown/other'");fails(f,/undeclared package/);f.write(tool,'export {};');fails(f,/Unused tool external/);
  f.write(tool,"import 'rolldown/utils'");f.policy.tool_external_imports.push(edge);fails(f,/Duplicate/);f.policy.tool_external_imports.pop();
  f.write('workspace-app/package-lock.json',{packages:{'node_modules/rolldown':{...locked,link:true}}});fails(f,/pinned registry/);
 }finally{f.close();}
});
test('virtual fixture mapping resolves exact edges but preserves private checks and resolver source binding',()=>{
 const f=fixture();try{
  const from=f.s+'test-support/fixture.js',resolver=f.s+'test-support/resolver.js',target=f.s+'api.js';
  f.write(from,"import './virtual-api.js'");f.write(resolver,'export const fixtureResolver=1;');f.write(target,'export {};');
  const edge={from,specifier:'./virtual-api.js',to:target,resolver_path:resolver,resolver_sha256:createHash('sha256').update('export const fixtureResolver=1;').digest('hex')};
  f.policy.virtual_import_edges.push(edge);assert.equal(f.check().exit,0);
  edge.to=f.s+'presentation/internal/helper.js';fails(f,/forbidden private/);edge.to=target;
  f.write(resolver,'export const fixtureResolver=2;');fails(f,/Virtual resolver hash changed/);f.write(resolver,'export const fixtureResolver=1;');
  f.policy.virtual_import_edges.push({...edge});fails(f,/Duplicate virtual/);f.policy.virtual_import_edges.pop();
  f.write(from,'export {};');fails(f,/Unused virtual/);f.write(from,"import './unmapped.js'");fails(f,/unresolved/);
  f.write(from,"import './virtual-api.js'");edge.from=f.s+'consumer.js';fails(f,/scanned test support/);
 }finally{f.close();}
});
