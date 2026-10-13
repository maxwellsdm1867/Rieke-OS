import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {census,inspectModule,checkInventory} from '../retainedLifecyclePolicy.mjs';

test('the complete App production closure has current lifecycle review receipts',()=>{
 const inventory=JSON.parse(readFileSync(new URL('../../docs/architecture/retained-ui-lifetimes.json',import.meta.url),'utf8'));
 assert.deepEqual(checkInventory(census(),inventory),[], 'Review changed lifetimes and behavioral evidence; do not mechanically refresh fingerprints.');
 for(const receipt of Object.values(inventory.modules))for(const path of receipt.tests)assert.ok(readFileSync(new URL(path,new URL('../',import.meta.url)),'utf8').length,path);
});
test('review catches aliased hooks, namespace hooks and changed callback helpers',()=>{
 const original="import React,{useEffect as connect} from 'react'; function read(){return 1;} export function View(){connect(()=>read(),[]);React.useLayoutEffect(()=>read(),[]);}";
 const first=inspectModule('view.jsx',original);
 assert.deepEqual(first.sites.map(site=>site.kind),['useEffect','useLayoutEffect']);
 const changed=inspectModule('view.jsx',original.replace('return 1','return 2'));
 assert.deepEqual(first.sites,changed.sites);
 assert.notEqual(first.fingerprint,changed.fingerprint,'out-of-callback helpers remain covered');
 assert.equal(first.fingerprint,inspectModule('view.jsx','// formatting only\n'+original).fingerprint);
 assert.notEqual(inspectModule('a.js','export const a=String.raw`\\n`;').fingerprint,inspectModule('a.js','export const a=String.raw`\\r`;').fingerprint,'tagged template raw content is semantic');
 assert.throws(()=>inspectModule('a.js',"import React from 'react'; const effect=React.useEffect;"),/hook alias/);
 assert.throws(()=>inspectModule('a.js',"import {useEffect} from 'react'; const effect=useEffect;"),/hook alias/);
 assert.throws(()=>inspectModule('a.js',"import React from 'react'; const {useEffect: effect}=React;"),/destructured lifecycle/);
});
test('new, missing, changed and stale module receipts fail closed',()=>{
 const a=inspectModule('a.js','export const a=1;'),b=inspectModule('a.js','export const a=2;');
 const receipt={...a,lifetime:'presentation',reason:'explicit identity',tests:['behavior.test.js']};
 delete receipt.dependencies;
 assert.deepEqual(checkInventory({a}, {modules:{a:receipt}}),[]);
 assert.match(checkInventory({a:b},{modules:{a:receipt}}).join('\n'),/source changed/);
 assert.match(checkInventory({a},{modules:{}}).join('\n'),/missing lifecycle/);
 assert.match(checkInventory({},{modules:{a:receipt}}).join('\n'),/stale dependency/);
});
test('closure follows helper and literal lazy imports and rejects computed imports',()=>{
 const base=mkdtempSync(join(tmpdir(),'disco-lifecycle-'));
 try{
  mkdirSync(join(base,'src'));
  writeFileSync(join(base,'src/App.jsx'),"import './helper.js'; export const lazy=()=>import('./lazy.jsx');");
  writeFileSync(join(base,'src/helper.js'),'export const helper=1;');
  writeFileSync(join(base,'src/lazy.jsx'),'export default null;');
  assert.deepEqual(Object.keys(census(base)),['src/App.jsx','src/helper.js','src/lazy.jsx']);
  writeFileSync(join(base,'src/App.jsx'),'export const lazy=name=>import(name);');
  assert.throws(()=>census(base),/Computed module loading/);
  writeFileSync(join(base,'src/App.jsx'),"import '/src/omitted.jsx';");
  assert.throws(()=>census(base),/Unreviewed external or aliased/);
  writeFileSync(join(base,'src/App.jsx'),"import '@/omitted.jsx';");
  assert.throws(()=>census(base),/Unreviewed external or aliased/);
 }finally{rmSync(base,{recursive:true,force:true});}
});
