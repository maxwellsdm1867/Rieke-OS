// One deterministic discovery path for frontend tests; no shell glob expansion.
import {readdirSync,lstatSync,realpathSync} from 'node:fs';
import {dirname,join,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

export function discoverTests(root){
 const tests=[];
 if(lstatSync(join(root,'src')).isSymbolicLink())throw Error('Test discovery rejects symlink: src');
 function walk(directory){
  for(const entry of readdirSync(directory,{withFileTypes:true})){
   const path=join(directory,entry.name);
   if(entry.isSymbolicLink())throw Error(`Test discovery rejects symlink: ${path}`);
   if(entry.isDirectory()){walk(path);continue;}
   if(/\.test\.(jsx|mjs|cjs)$/.test(entry.name))throw Error(`Unsupported test suffix: ${path}`);
   if(entry.isFile()&&entry.name.endsWith('.test.js')&&!relative(join(root,'src'),path).split(sep).join('/').startsWith('test-support/'))tests.push(relative(root,path));
  }
 }
 walk(join(root,'src'));
 if(!tests.length)throw Error('No frontend tests discovered');
 return tests.sort();
}
export function runTests(root){
 if('RIEKE_TEST_DOM_MODULE' in process.env)throw Error('RIEKE_TEST_DOM_MODULE must be unset for frontend test evidence');
 const run=spawnSync(process.execPath,['--import','./src/test-support/reactTestEnvironment.js','--test',...discoverTests(root)],{cwd:root,stdio:'inherit',env:process.env});
 if(run.error)throw run.error;
 if(run.signal){process.kill(process.pid,run.signal);return 1;}
 return run.status??1;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===realpathSync(process.argv[1])){
 try{process.exitCode=runTests(dirname(fileURLToPath(import.meta.url)));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
