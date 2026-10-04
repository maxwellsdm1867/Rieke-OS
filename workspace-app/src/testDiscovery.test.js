import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,copyFileSync,rmSync,symlinkSync,existsSync,renameSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {discoverTests} from '../runTests.mjs';

function fixture(){
 const root=mkdtempSync(join(tmpdir(),'disco-test-discovery-'));
 const write=(name,body)=>{mkdirSync(join(root,name,'..'),{recursive:true});writeFileSync(join(root,name),body);};
 write('package.json','{"type":"module"}');
 write('src/test-support/reactTestEnvironment.js','globalThis.preloadWitness="present";');
 copyFileSync(fileURLToPath(new URL('../runTests.mjs',import.meta.url)),join(root,'runTests.mjs'));
 return {root,write,close:()=>rmSync(root,{recursive:true,force:true}),run:(extra={})=>{
  const env={...process.env,...extra};delete env.NODE_TEST_CONTEXT;
  const run=spawnSync(process.execPath,[join(root,'runTests.mjs')],{encoding:'utf8',env});assert.ifError(run.error);return run;
 }};
}
const passing=`import test from 'node:test';import assert from 'node:assert/strict';test('preload sentinel',()=>assert.equal(globalThis.preloadWitness,'present'));`;
test('recursive discovery sorts unique root and two-level tests, excludes support and non-tests, and preserves preload',()=>{
 const f=fixture();try{
  f.write('src/z.test.js',passing);f.write('src/module/internal/a.test.js',passing);
  f.write('src/not-a-test.js','throw Error("non-test executed")');
  f.write('src/test-support/hidden.test.js','throw Error("support executed")');
  assert.deepEqual(discoverTests(f.root),['src/module/internal/a.test.js','src/z.test.js']);
  const run=f.run();assert.equal(run.status,0,run.stdout+run.stderr);assert.match(run.stdout,/tests 2/);
 }finally{f.close();}
});
test('a deliberately failing nested test propagates failure while the root test still executes',()=>{
 const f=fixture();try{
  f.write('src/root.test.js',passing);
  f.write('src/module/internal/fault.test.js',`import test from 'node:test';import assert from 'node:assert/strict';test('nested deliberate fault',()=>assert.equal('fault','expected'));`);
  const run=f.run();assert.notEqual(run.status,0);assert.match(run.stdout,/nested deliberate fault/);assert.match(run.stdout,/preload sentinel/);
 }finally{f.close();}
});
test('empty discovery and unsupported test suffixes fail before launch',()=>{
 const f=fixture();try{
  assert.match(f.run().stderr,/No frontend tests/);
  f.write('src/new.test.jsx',passing);assert.match(f.run().stderr,/Unsupported test suffix/);
 }finally{f.close();}
});
test('discovery rejects symlinks without traversing or executing their tests',()=>{
 const f=fixture();try{
  f.write('outside/escape.test.js',`import {writeFileSync} from 'node:fs';writeFileSync(${JSON.stringify(join(f.root,'executed'))},'bad');`);
  symlinkSync(join(f.root,'outside'),join(f.root,'src','link'),'dir');
  assert.match(f.run().stderr,/rejects symlink/);assert.equal(existsSync(join(f.root,'executed')),false);
 }finally{f.close();}
});
test('DOM overrides including empty values cannot produce frontend test evidence',()=>{
 const f=fixture();try{
  f.write('src/root.test.js',passing);
  for(const value of ['', 'jsdom','/unowned/module.js']){
   const run=f.run({RIEKE_TEST_DOM_MODULE:value});assert.notEqual(run.status,0);assert.match(run.stderr,/must be unset/);
  }
 }finally{f.close();}
});

test('nested module test-support names are not silently excluded, and a symlinked source root fails',()=>{
 const f=fixture();try{
  f.write('src/module/test-support/local.test.js',passing);
  assert.deepEqual(discoverTests(f.root),['src/module/test-support/local.test.js']);
  renameSync(join(f.root,'src'),join(f.root,'real-src'));symlinkSync(join(f.root,'real-src'),join(f.root,'src'),'dir');
  assert.match(f.run().stderr,/rejects symlink/);
 }finally{f.close();}
});
