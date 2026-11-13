'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {RuntimeGenerations}=require('../runtime-generations.cjs');
test('admission and retirement public decisions preserve live processes and expire dead leases',async()=>{
  const run=require('node:util').promisify(require('node:child_process').execFile);
  const result=await run(process.env.DISCO_TEST_PYTHON||'python3',['-B',path.join(__dirname,'test_runtime_store.py')]);
  assert.match(result.stderr,/Ran 17 tests/);assert.match(result.stderr,/OK/);
});
// Actual private filesystem and kernel transactions; inert bundle validation and
// copying only. No installed app, scientific data, native launch or host GC.
async function fixture(t){
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'disco-generation-test-')));
  t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const verify=async bundle=>{
    const bytes=await fs.readFile(path.join(bundle,'payload.json'));
    const manifest=JSON.parse(bytes),id=crypto.createHash('sha256').update(bytes).digest('hex');
    return {manifest,id,manifestHash:id};
  };
  const store=new RuntimeGenerations({root:path.join(directory,'store'),python:process.env.DISCO_TEST_PYTHON||'python3',verify,
    copy:(source,destination)=>fs.cp(source,destination,{recursive:true}),readQuarantine:async()=>null});
  async function source(version,extra={}){
    const bundle=path.join(directory,'download-'+crypto.randomUUID(),'Disco.app');
    await fs.mkdir(bundle,{recursive:true});
    await fs.writeFile(path.join(bundle,'payload.json'),JSON.stringify({format:'rieke-desktop-runtime',version:1,platform:'darwin',architecture:'arm64',
      mysql_version:'8.4.0',database_compatibility:1,workspace_formats:[1],application_version:version,...extra}));
    return bundle;
  }
  return {directory,store,source,verify};
}
test('activating new bytes leaves the old physical runtime readable and selects the newest future launch',async t=>{
  const {store,source}=await fixture(t);
  const old=await store.stage(await source('0.2.4'));
  await store.activate(old);
  const bytes=await fs.readFile(path.join(old.bundle,'payload.json'));
  const next=await store.stage(await source('0.2.5'));
  await store.activate(next);
  assert.equal(store.current().id,next.id);
  assert.equal(store.current().previous,old.id);
  assert.deepEqual(await fs.readFile(path.join(old.bundle,'payload.json')),bytes);
});
test('concurrent activations cannot replace a newer pointer with an older caller version',async t=>{
  const {store,source}=await fixture(t);
  const candidates=await Promise.all(['0.2.4','0.2.6','0.2.5'].map(async version=>store.stage(await source(version))));
  await Promise.all(candidates.map(candidate=>store.activate(candidate)));
  assert.equal(store.current().generation.manifest.application_version,'0.2.6');
});
test('a changed but internally valid download cannot substitute for the verified archive candidate',async t=>{
  const {store,source,verify}=await fixture(t);
  const original=await source('0.2.4'),identity=await verify(original);
  const changed=await source('0.2.4',{source_commit:'changed'});
  await assert.rejects(store.stage(changed,{bundle_sha256:identity.id,runtime_manifest_sha256:identity.manifestHash,version:'0.2.4'}),/downloaded update/);
  assert.throws(()=>store.current(),{code:'ENOENT'});
});
test('different contents claiming one version cannot silently replace current',async t=>{
  const {store,source}=await fixture(t);
  const original=await store.stage(await source('0.2.4'));
  await store.activate(original);
  const changed=await store.stage(await source('0.2.4',{source_commit:'different'}));
  await assert.rejects(store.activate(changed),/same application version/);
  assert.equal(store.current().id,original.id);
});
test('rollback is revision bound and cannot undo a later activation',async t=>{
  const {store,source}=await fixture(t);
  const old=await store.stage(await source('0.2.4')),next=await store.stage(await source('0.2.5')),newest=await store.stage(await source('0.2.6'));
  await store.activate(old);const activation=await store.activate(next);
  await store.activate(newest);
  const prepared=await store.stage(old.bundle);
  await assert.rejects(store.activate(prepared,{rollbackRevision:activation.revision}),/superseded/);
  const rolledBack=await store.activate(prepared,{rollbackRevision:store.current().revision});
  assert.equal(rolledBack.id,old.id);
});
for(const corrupt of ['interrupted bytes','null','[]','42','{"format":"disco-current-runtime","version":1,"revision":false}'])test(`an invalid pointer ${corrupt} is preserved while a verified generation restores the entry point`,async t=>{
  const {store,source}=await fixture(t);
  const candidate=await store.stage(await source('0.2.4'));
  await fs.writeFile(path.join(store.root,'current.json'),corrupt);
  await store.activate(candidate);
  const evidence=(await fs.readdir(store.root)).find(name=>name.startsWith('invalid-current-'));
  assert.equal(await fs.readFile(path.join(store.root,evidence),'utf8'),corrupt);
  assert.equal(store.current().id,candidate.id);
});
test('concurrent staging publishes one immutable generation and removes disposable staging copies',async t=>{
  const {store,source}=await fixture(t),download=await source('0.2.4');
  const values=await Promise.all([store.stage(download),store.stage(download)]);
  assert.equal(values[0].id,values[1].id);
  assert.equal((await fs.readdir(store.root)).filter(name=>name.startsWith('staging-')).length,0);
});

test('invalid preparation is refused before runtime store mutations',async t=>{
  async function snapshot(root){
    const result={};
    async function walk(folder){
      for(const entry of (await fs.readdir(folder,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
        const file=path.join(folder,entry.name),relative=path.relative(root,file);
        if(entry.isDirectory()){result[relative]='/';await walk(file);}
        else result[relative]=(await fs.readFile(file)).toString('base64');
      }
    }
    await walk(root);return result;
  }
  for(const operation of ['activate','reserve','restart-handoff'])for(const fault of ['foreign','wrong-target','missing','malformed','wrong-type','foreign-invalid-pointer']){
    await t.test(`${operation}/${fault}`,async t=>{
      const {store,source,directory}=await fixture(t);
      const old=await store.stage(await source('0.2.6'));await store.activate(old);
      const next=await store.stage(await source('0.2.7'));
      let preparation=next.preparation;
      const file=path.join(store.root,'preparations',preparation+'.json');
      if(fault.startsWith('foreign')||fault==='wrong-target'){
        const record=JSON.parse(await fs.readFile(file,'utf8'));
        if(fault==='wrong-target')record.id=old.id;else record.pid=process.pid+1000000;
        await fs.writeFile(file,JSON.stringify(record));
      }else if(fault==='missing')preparation=crypto.randomUUID();
      else if(fault==='malformed')preparation='not-a-token';
      else preparation={invalid:true};
      if(fault==='foreign-invalid-pointer')await fs.writeFile(path.join(store.root,'current.json'),'invalid current evidence');
      const before=await snapshot(store.root);
      await assert.rejects(store.transaction({operation,id:next.id,preparation,
        profile:path.join(directory,'profile'),identity:{pid:process.pid,executable:process.execPath}}));
      assert.deepEqual(await snapshot(store.root),before,'Rejected preparation must leave pointers, pins, admissions and handoffs unchanged');
    });
  }
});
