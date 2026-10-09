const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {StartupSession,viewNamespace}=require('../startup-session.cjs');
const uuid='00000000-0000-0000-0000-000000000001';
test('durable location is versioned, claimed once, and chooser preference persists',async()=>{const dir=await fs.mkdtemp(path.join(os.tmpdir(),'disco-session-'));try{const a=new StartupSession(dir,'0.1.7:view-v1');await a.remember(uuid,'/owned/a','cell-qc');const b=new StartupSession(dir,a.compatibility);await b.load();assert.equal(b.claim().projectPath,'/owned/a');assert.equal(b.claim(),null);await b.choose();const c=new StartupSession(dir,a.compatibility);await c.load();assert.equal(c.claim(),null);await c.resume();const d=new StartupSession(dir,a.compatibility);await d.load();assert.equal(d.claim().projectId,uuid);const e=new StartupSession(dir,'next:view-v1');await e.load();assert.equal(e.claim(),null);}finally{await fs.rm(dir,{recursive:true});}});
test('corrupt/partial preference is preserved and does not restore',async()=>{const dir=await fs.mkdtemp(path.join(os.tmpdir(),'disco-session-'));try{const p=path.join(dir,'startup-session.json');await fs.writeFile(p,'{"partial":');const s=new StartupSession(dir,'v');await s.load();assert.equal(s.claim(),null);assert.equal(await fs.readFile(p,'utf8'),'{"partial":');}finally{await fs.rm(dir,{recursive:true});}});
test('same UUID copied to another path and incompatible view versions have different namespaces',()=>{assert.notEqual(viewNamespace(uuid,'/a','v1'),viewNamespace(uuid,'/b','v1'));assert.notEqual(viewNamespace(uuid,'/a','v1'),viewNamespace(uuid,'/a','v2'));});

test('transient quit cancellation does not change the next-launch preference',async()=>{const dir=await fs.mkdtemp(path.join(os.tmpdir(),'disco-session-'));try{const s=new StartupSession(dir,'v');await s.remember(uuid,'/owned/a','cell-qc');s.cancelled=true;await s.remember(uuid,'/owned/a','cell-qc');const next=new StartupSession(dir,'v');await next.load();assert.equal(next.claim().projectId,uuid);await next.choose();await next.remember(uuid,'/owned/a','cell-qc');assert.equal(next.value.mode,'chooser');}finally{await fs.rm(dir,{recursive:true});}});


test('schema-compatible upgrade preserves resume or chooser without rewriting the saved bytes',async t=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'disco-session-upgrade-'));t.after(()=>fs.rm(dir,{recursive:true}));
 for(const version of ['0.1.8:view-v1','0.1.9:view-v1'])for(const mode of ['resume','chooser']){
  const old=new StartupSession(dir,version);await old.remember(uuid,'/owned/a','protocol');if(mode==='chooser')await old.choose();
  const before=await fs.readFile(old.file,'utf8');
  const next=new StartupSession(dir,'view-v1');await next.load();
  assert.equal(next.value.mode,mode);assert.equal(next.value.compatibility,'view-v1');
  assert.equal(next.claim()?.view??null,mode==='resume'?'protocol':null);
  assert.equal(await fs.readFile(old.file,'utf8'),before);
 }
 const future=new StartupSession(dir,'view-v2');await future.remember(uuid,'/owned/a','protocol');
 const current=new StartupSession(dir,'view-v1');await current.load();assert.equal(current.claim(),null);
});
