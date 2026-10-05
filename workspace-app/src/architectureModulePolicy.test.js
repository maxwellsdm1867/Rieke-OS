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

function migrateV3(f){
 f.catalog.version=3;
 f.policy.modules=f.policy.modules.map(({public_entry,public_exports,...module})=>({...module,public_entries:[{path:public_entry,exports:public_exports}]}));
}
function twoEntryFixture(){
 const f=fixture();migrateV3(f);
 const module=f.policy.modules[0],first=module.public_entries[0].path,second=module.root+'/hook.js';
 module.public_entries.push({path:second,exports:['default']});
 f.catalog.contracts[0].rules.push({language:'javascript',file:second,allow:[first]});
 f.write(second,"import {factory} from './public.js';export default function hook(){return factory();}");
 f.write(f.s+'consumer.js',"import {factory} from './presentation/public.js';import hook from './presentation/hook.js';");
 f.write(f.s+'consumer.test.js',"import {factory} from './presentation/public.js';import hook from './presentation/hook.js';");
 return f;
}

test('v4 requires Python policy and preserves v3 multi-entry JavaScript checks',()=>{
 const f=twoEntryFixture();try{
  f.catalog.version=4;
  fails(f,/requires Python module policy/);
  f.write('python/disco/__init__.py','');
  f.write('python/disco/recovery/__init__.py','from .implementation import callback\n__all__ = ("callback",)\n');
  f.write('python/disco/recovery/implementation.py','def callback(): pass\n');
  f.write('python/disco/recovery/tests/__init__.py','');
  f.write('python/disco/recovery/tests/test_public.py','from disco.recovery import callback\n');
  f.write('python/tests/__init__.py','');
  copyFileSync(fileURLToPath(new URL('../../tools/architecture_guard.py',import.meta.url)),join(f.root,'tools/architecture_guard.py'));
  f.catalog.contracts.push({id:'recovery',contract:{path:'docs/contract.md',heading:'Presentation'},affected_paths:['python/**'],
   rules:[{language:'python',file:'python/disco/recovery/__init__.py',allow:['disco.recovery.implementation']},
          {language:'python',file:'python/disco/recovery/implementation.py',allow:[]}],
   tests:{python:['python/disco/recovery/tests/test_public.py'],javascript:[]}});
  f.catalog.python_module_policy={source_root:'python',test_roots:['python/tests','python/disco/recovery/tests'],fixture_pythonpath:['python/tests'],reviewed_loader_sites:[],
   modules:[{contract_id:'recovery',root:'python/disco/recovery',public_module:'disco.recovery',public_entry:'python/disco/recovery/__init__.py',
    public_exports:[{name:'callback',from:'python/disco/recovery/implementation.py'}],private_test_edges:[]}]};
  assert.equal(f.check().exit,0);
  assert.equal(f.check({language:'python'}).exit,0);
  const entry=f.policy.modules[0].public_entries[1];
  f.write(entry.path,'export const wrong=1;');fails(f,/export/);
  f.write(entry.path,'export default function hook(){}');
  f.write(f.s+'consumer.js',"import './presentation/internal/helper.js';");fails(f,/forbidden private/);
  f.catalog.version=3;fails(f,/Invalid catalog fields/);
 }finally{f.close();}
});

test('v3 two-entry modules preserve per-file named/default surfaces and public consumers',()=>{
 const f=twoEntryFixture();try{
  assert.equal(f.check().exit,0);
  const module=f.policy.modules[0];
  module.public_entries[0].exports=['default'];
  f.write(module.public_entries[0].path,'export default function factory(){}');
  f.write(module.public_entries[1].path,"import factory from './public.js';export default function hook(){return factory();}");
  assert.equal(f.check().exit,0,'default is scoped to each entry, not globally unique');
  for(const entry of module.public_entries){entry.exports=['default','named'];f.write(entry.path,'export default function value(){};export const named=1;');}
  assert.equal(f.check().exit,0,'both default and named must be declared per file');
  f.write(f.s+'bridge.js',"export {named} from './presentation/public.js';");
  assert.equal(f.check().exit,0,'outside re-export of public entry retains existing behavior');
 }finally{f.close();}
});

test('v3 export faults cannot hide behind another entry or an unchanged union',()=>{
 const f=twoEntryFixture();try{
  const [first,second]=f.policy.modules[0].public_entries;
  for(const entry of [first,second]){
   const original=readFileSync(join(f.root,entry.path),'utf8');
   const wrong=entry===first?'default':'factory';
   const permitted=entry===first?'./internal/helper.js':'./public.js';
   const variants=['export {};',original+'\nexport const extra=1;',
    wrong==='default'?'export default 1;':'export const factory=1;',
    `export * from '${permitted}';`, `export {value as default} from '${permitted}';`];
   if(entry===first)variants.push(original+'\nexport default 1;');
   for(const source of variants){
    f.write(entry.path,source);const result=f.check();
    assert.equal(result.exit,1);assert.match(result.result.error,/public export surface/);assert.ok(result.result.error.includes(entry.path));
   }
   f.write(entry.path,original);
  }
  f.write(first.path,'export default 1;');f.write(second.path,'export const factory=1;');
  fails(f,/public export surface/);
 }finally{f.close();}
});

test('versioned schemas retain v1/v2 and reject mixed, missing and future policies',()=>{
 const f=fixture();try{
  assert.equal(f.check().exit,0,'original v2 fixture remains valid');
  const legacy=structuredClone(f.policy.modules[0]);migrateV3(f);
  assert.equal(f.check().exit,0,'single-entry v3 migration is equivalent');
  const modern=structuredClone(f.policy.modules[0]);
  f.catalog.version=2;fails(f,/Invalid module policy fields/);
  f.catalog.version=3;f.policy.modules[0]=legacy;fails(f,/Invalid module policy fields/);
  f.policy.modules[0]={...modern,public_entry:legacy.public_entry};fails(f,/Invalid module policy fields/);
  f.policy.modules[0]={...modern,public_exports:legacy.public_exports};fails(f,/Invalid module policy fields/);
  f.policy.modules[0]=modern;
  delete f.catalog.javascript_module_policy;fails(f,/version 3 requires/);
  f.catalog.version=2;fails(f,/version 2 requires/);
  f.catalog.version=1;assert.equal(f.check().exit,0);
  f.catalog.javascript_module_policy=f.policy;fails(f,/version 1 forbids/);
  for(const version of [0,5,99]){f.catalog.version=version;fails(f,/Unsupported adopted-port/);}
  for(const version of [1,2,3]){
   f.catalog.version=version;f.catalog.python_module_policy={};fails(f,/Invalid catalog fields/);delete f.catalog.python_module_policy;
  }
 }finally{f.close();}
});

test('v3 rejects malformed entry declarations, assets and nonproduction paths',()=>{
 const f=twoEntryFixture();try{
  const module=f.policy.modules[0],original=structuredClone(module.public_entries);
  const variants=[null,{},'entry',[],[null],[{}],
   [{...original[0],unknown:true}],
   [{...original[0],path:''}],[{...original[0],path:[]}],
   [{...original[0],exports:[]}],[{...original[0],exports:null}],
   [{...original[0],exports:['']}],[{...original[0],exports:[1]}],
   [{...original[0],exports:['factory','factory']}],[{...original[0],exports:['*']}],
   [original[0],{...original[0],exports:['different']}]];
  for(const entries of variants){module.public_entries=entries;fails(f,/Invalid module policy|Public entr|Public export|unique nonempty|Duplicate public/);}
  module.public_entries=original;
  for(const [name,content] of [['asset.css','body{}'],['asset.txt','text'],['inside.test.js','export {};']])f.write(module.root+'/'+name,content);
  for(const name of [module.root+'/missing.js',f.s+'consumer.js',module.root,module.root+'/asset.css',module.root+'/asset.txt',module.root+'/inside.test.js',module.root+'/./public.js',module.root+'/../presentation/public.js']){
   module.public_entries=[{path:name,exports:['factory']}];fails(f,/Missing or escaping|module production|scanned executable|Invalid module policy path/);
  }
  module.public_entries=original;
  const support=module.root+'/support';f.write(support+'/probe.js','export const probe=1;');f.policy.test_support_roots.push(support);
  module.public_entries=[{path:support+'/probe.js',exports:['probe']}];fails(f,/module production/);
  module.public_entries=original;
  const tool=module.root+'/tool.js';f.write(tool,'export const tool=1;');f.policy.test_tool_files.push(tool);
  module.public_entries=[{path:tool,exports:['tool']}];fails(f,/module production/);
  module.public_entries=original;
  f.write(module.root+'/unsupported.ts','export const typed=1;');
  module.public_entries=[{path:module.root+'/unsupported.ts',exports:['typed']}];fails(f,/Unsupported source/);
  rmSync(join(f.root,module.root+'/unsupported.ts'));module.public_entries=original;
  symlinkSync(join(f.root,original[0].path),join(f.root,module.root+'/alias.js'));
  module.public_entries=[{path:module.root+'/alias.js',exports:['factory']}];fails(f,/symlink/);
 }finally{f.close();}
});

test('v3 retains disjoint roots, unique contracts and strict module fields',()=>{
 const f=twoEntryFixture();try{
  const module=f.policy.modules[0];module.extra=true;fails(f,/Invalid module policy fields/);delete module.extra;
  f.policy.modules.push(structuredClone(module));fails(f,/Contract must exist and be unique|contract must exist and be unique/);f.policy.modules.pop();
  const duplicate=structuredClone(f.catalog.contracts[0]);duplicate.id='second';f.catalog.contracts.push(duplicate);
  f.policy.modules.push({...structuredClone(module),contract_id:'second'});fails(f,/disjoint source descendants/);
  f.policy.modules[1].root=module.root+'/internal';fails(f,/disjoint source descendants/);
 }finally{f.close();}
});

test('v3 entries still need ownership rules and do not grant private or test access',()=>{
 const f=twoEntryFixture();try{
  const module=f.policy.modules[0],rules=f.catalog.contracts[0].rules;
  const secondRule=rules.pop();fails(f,/needs an ownership allow rule/);rules.push(secondRule);
  const allowed=secondRule.allow;secondRule.allow=[];fails(f,/forbidden dependency/);secondRule.allow=allowed;
  const third=module.root+'/third.js';f.write(third,'export const third=1;');fails(f,/needs an ownership allow rule/);
  rules.push({language:'javascript',file:third,allow:[]});assert.equal(f.check().exit,0);
  const attempts=["import './presentation/third.js'","import './presentation/../presentation/third'",
   "export {third} from './presentation/third.js'","export * from './presentation/third.js'",
   "async function load(){return import('./presentation/third.js')}","require('./presentation/third')"];
  for(const consumer of ['outside.js','outside.test.js']){
   for(const source of attempts){f.write(f.s+consumer,source);fails(f,/forbidden private/);}
   f.write(f.s+consumer,'export {};');
  }
  for(const entry of module.public_entries){
   const edge={from:module.root+'/inside.test.js',to:entry.path};f.write(edge.from,'export {};');
   module.private_test_edges.push(edge);fails(f,/Private test edge/);module.private_test_edges.pop();
  }
  f.write(f.s+'outside.js',"import './consumer.test.js';");fails(f,/production cannot import test/);
  f.write(f.s+'outside.js','export {};');
  const edge=module.private_test_edges[0];module.private_test_edges.push({...edge});fails(f,/Duplicate private test/);module.private_test_edges.pop();
  f.write(edge.from,'export {};');fails(f,/Unused private test/);
 }finally{f.close();}
});

test('v2 metadata keeps its legacy entry validation while v3 requires scanned executable entries',()=>{
 const f=fixture();try{
  const module=f.policy.modules[0];f.write(module.root+'/entry.css','body{}');
  module.public_entry=module.root+'/entry.css';
  assert.equal(f.check({language:'metadata'}).exit,0,'historical v2 metadata semantics are preserved');
  migrateV3(f);const result=f.check({language:'metadata'});
  assert.equal(result.exit,1);assert.match(result.result.error,/scanned executable/);
 }finally{f.close();}
});

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

test('reviewed virtual fixture CSS crosses a module only on its exact hash-bound asset edge',()=>{
 const f=twoEntryFixture();try{
  const from=f.s+'test-support/fixture.js',resolver=f.s+'test-support/resolver.js',target=f.s+'presentation/theme.css';
  const source="import './virtual-theme.css';",resolverSource='export const fixtureResolver=1;';
  f.write(from,source);f.write(resolver,resolverSource);f.write(target,'body{color:black}');
  const edge={from,specifier:'./virtual-theme.css',to:target,resolver_path:resolver,resolver_sha256:createHash('sha256').update(resolverSource).digest('hex')};
  f.policy.virtual_import_edges.push(edge);assert.equal(f.check().exit,0);
  // A reviewed asset mapping cannot authorize executable module internals.
  edge.to=f.s+'presentation/internal/helper.js';fails(f,/forbidden private/);edge.to=target;
  f.write(resolver,'export const fixtureResolver=2;');fails(f,/Virtual resolver hash changed/);f.write(resolver,resolverSource);
  // Neither another importer nor an unmapped specifier can borrow the CSS edge.
  f.write(f.s+'test-support/other.js',"import '../presentation/theme.css';");fails(f,/forbidden private/);f.write(f.s+'test-support/other.js','export {};');
  f.write(from,"import '../presentation/theme.css';");fails(f,/forbidden private/);f.write(from,source);
  f.write(f.s+'consumer.js',"import './presentation/theme.css';");fails(f,/forbidden private/);f.write(f.s+'consumer.js',"import {factory} from './presentation/public.js';");
  f.write(from,'export {};');fails(f,/Unused virtual/);f.write(from,source);
  const link=f.s+'presentation/linked.css';symlinkSync(join(f.root,target),join(f.root,link));edge.to=link;fails(f,/symlink/);edge.to=target;rmSync(join(f.root,link));
  assert.equal(f.check().exit,0);
 }finally{f.close();}
});

for (const id of ['p03-selection-reader', 'p04-group-save-session']) {
 test(`${id} folder enforces its declared public surface and rejects private/test imports`, () => {
  const actual = JSON.parse(readFileSync(new URL('../../docs/architecture/adopted-port-checks.json', import.meta.url), 'utf8'));
  const declared = actual.javascript_module_policy.modules.find(module => module.contract_id === id);
  assert.ok(declared, `${id} must have a folder policy`);
  assert.deepEqual(declared.private_test_edges, []);
  const f = fixture();
  migrateV3(f);
  assert.equal(declared.public_entries.length, 1);
  const entry = declared.public_entries[0];
  try {
   // Exercise the catalog's real root/entry/export names in an isolated source tree.
   // The injected helper is a future private file, not a new runtime abstraction.
   const helper = `${declared.root}/internal/helper.js`;
   const publicTest = entry.path.replace(/\.js$/, '.test.js');
   const publicSource = `import {value} from './internal/helper.js';\n${entry.exports.map(name => `export const ${name}=value;`).join('\n')}`;
   f.policy.modules.push({...declared, private_test_edges: []});
   f.catalog.contracts.push({id, contract: {path:'docs/contract.md',heading:'Presentation'}, affected_paths:['workspace-app/**'], rules:[
    {language:'javascript',file:entry.path,allow:[helper]},
    {language:'javascript',file:helper,allow:[]},
   ], tests:{python:[],javascript:[publicTest]}});
   f.write(helper, 'export const value=1;');
   f.write(entry.path, publicSource);
   f.write(publicTest, `import {${entry.exports.join(',')}} from './${entry.path.split('/').at(-1)}';`);
   assert.equal(f.check().exit, 0);
   const relative = helper.slice(f.s.length);
   for (const consumer of ['outside.js','outside.test.js']) {
    f.write(f.s+consumer, `import './${relative}';`);
    fails(f, /forbidden private/);
    f.write(f.s+consumer, 'export {};');
   }
   f.write(entry.path, publicSource+'\nexport const accidentalPublicName=1;');
   fails(f, /public export surface/);
   f.write(entry.path, publicSource);
   f.write(f.s+'outside.js', `import './${publicTest.slice(f.s.length)}';`);
   fails(f, /production cannot import test/);
  } finally { f.close(); }
 });
}
