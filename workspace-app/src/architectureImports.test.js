import test from 'node:test';
import assert from 'node:assert/strict';
import {dependencies} from '../architectureImports.mjs';
import {mkdtempSync,mkdirSync,writeFileSync,copyFileSync,symlinkSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

test('dependency parser sees aliased imports, re-exports and nested literal loading in JSX',()=>{
  assert.deepEqual(dependencies('view.jsx',`
    import {api as send} from './api.js';
    export {value} from './other.js';
    function f(){ require('./legacy.cjs'); return import('./lazy.js'); }
    const node=<div/>;
  `),['./api.js','./other.js','./legacy.cjs','./lazy.js']);
});

test('dependency parser fails closed on parse errors and computed loaders',()=>{
  for(const source of ['import(', 'const f=()=>import(target)', 'require(prefix+name)']){
    assert.throws(()=>dependencies('view.jsx',source),/parse|computed/i);
  }
});

test('dependency parser sees module.require and rejects aliased require loading',()=>{
  assert.deepEqual(dependencies('view.js',`module.require('./api.js')`),['./api.js']);
  assert.throws(()=>dependencies('view.js','const load=require; load(name)'),/computed|loader/i);
});

test('dependency parser ignores comments and strings that mention imports',()=>{
  assert.deepEqual(dependencies('view.js',`// import x from 'bad';\nconst text="require('bad')";`),[]);
});

test('CLI recognizes prefix-only Node builtins without admitting invented node modules',()=>{
  const parser=fileURLToPath(new URL('../architectureImports.mjs',import.meta.url));
  const result=spawnSync(process.execPath,[parser],{encoding:'utf8',input:JSON.stringify([{filename:'fixture.test.js',source:"import 'node:test'; import 'node:test/reporters'; import 'node:not-a-real-builtin';"}])});
  assert.equal(result.status,0,result.stderr);
  const [file]=JSON.parse(result.stdout);
  assert.ok(file.builtins.includes('node:test'));
  assert.ok(file.builtins.includes('node:test/reporters'));
  assert.ok(!file.builtins.includes('node:not-a-real-builtin'));
});

test('public guard rejects normalized forbidden edges, required-edge removal and unavailable parser',()=>{
  const root=mkdtempSync(join(tmpdir(),'disco-js-architecture-'));
  const write=(name,value)=>{mkdirSync(join(root,name,'..'),{recursive:true});writeFileSync(join(root,name),typeof value==='string'?value:JSON.stringify(value));};
  const policy={format:'disco-adopted-port-checks',version:1,
    discovery:[{from:'AGENTS.md',to:'docs/contract.md'}],shared_paths:['docs/**'],
    contracts:[{id:'reader',contract:{path:'docs/contract.md',heading:'Reader'},affected_paths:['workspace-app/**'],
      rules:[{language:'javascript',file:'workspace-app/src/view.jsx',deny:['workspace-app/src/api.js'],require:['workspace-app/src/reader.js']}],
      tests:{python:[],javascript:['workspace-app/src/contract.test.js']}}]};
  const guard=fileURLToPath(new URL('../../tools/architecture_guard.py',import.meta.url));
  const check=()=>{
    const run=spawnSync('python3',['-B',guard,'check','--root',root,'--language','javascript','--node',process.execPath],{encoding:'utf8'});
    assert.ifError(run.error);return {exit:run.status,result:JSON.parse(run.stdout)};
  };
  try{
    write('AGENTS.md','[Contract](docs/contract.md)');write('docs/contract.md','# Reader\n');
    write('docs/architecture/adopted-port-checks.json',policy);
    for(const name of ['reader.js','api.js','contract.test.js'])write('workspace-app/src/'+name,'export {};');
    copyFileSync(fileURLToPath(new URL('../architectureImports.mjs',import.meta.url)),join(root,'workspace-app/architectureImports.mjs'));
    // The parser only reads this already-installed dependency tree; no npm/cache writes.
    symlinkSync(fileURLToPath(new URL('../node_modules',import.meta.url)),join(root,'workspace-app/node_modules'),'dir');
    write('workspace-app/src/view.jsx',"import './reader.js'; const view=<div/>;");
    assert.equal(check().exit,0);
    for(const statement of ["import {api as send} from './api.js'", "export * from './api.js'", "function f(){return import('./api.js')}", "require('./api')", "module.require('./api.js')"]){
      write('workspace-app/src/view.jsx',"import './reader.js';"+statement);
      const result=check();assert.equal(result.exit,1);assert.match(result.result.error,/forbidden dependency workspace-app\/src\/api.js/);
    }
    for(const specifier of ['/src/api.js','file:///src/api.js']){
      write('workspace-app/src/view.jsx',`import './reader.js'; import '${specifier}';`);
      const result=check();assert.equal(result.exit,1);assert.match(result.result.error,/Absolute or URL module specifier/);
    }
    write('workspace-app/src/view.jsx','export {};');
    assert.match(check().result.error,/missing required dependency/);
    write('workspace-app/src/view.jsx',"import './reader.js'");
    write('workspace-app/architectureImports.mjs',"import 'missing-architecture-parser';");
    assert.match(check().result.error,/parser unavailable or failed/);
  }finally{rmSync(root,{recursive:true,force:true});}
});
