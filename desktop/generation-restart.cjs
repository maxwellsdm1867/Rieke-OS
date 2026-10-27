'use strict';
// Exact-session restart only. No application replacement and no process signals.
const fs=require('./physical-fs.cjs').promises;
const path=require('node:path');
const {enclosingApp}=require('./bootstrap.cjs');
const {processCreationIdentity}=require('./testing-install.cjs');
const {RuntimeGenerations,runtimeStore}=require('./runtime-generations.cjs');
async function restart(file) {
  const root=runtimeStore(),stat=await fs.lstat(file);
  if(path.dirname(file)!==path.join(root,'handoffs')||stat.isSymbolicLink()||!stat.isFile()||stat.uid!==process.getuid()||(stat.mode&0o077)||stat.size>16384)
    throw Error('Invalid generation restart receipt');
  const receipt=JSON.parse(await fs.readFile(file,'utf8'));
  const ownBundle=enclosingApp(process.execPath);
  if(receipt.format!=='disco-generation-restart'||receipt.version!==1||receipt.root!==root||receipt.identity?.pid!==process.ppid||
    receipt.identity.executable!==process.execPath||!__filename.startsWith(ownBundle+path.sep)||!path.isAbsolute(receipt.profile||''))
    throw Error('Generation restart belongs to another process');
  const identity=await processCreationIdentity(receipt.identity.pid,process.execPath);
  if(!identity.alive||identity.created_at!==receipt.identity.created_at||identity.executable!==receipt.identity.executable)
    throw Error('Generation restart parent changed');
  const store=new RuntimeGenerations({root,python:path.join(ownBundle,'Contents/Resources/runtime/python/bin/python3.11')});
  await store.transaction({operation:'claim-handoff',token:receipt.nonce});
  process.stdout.write(`DISCO_GENERATION_READY=${receipt.nonce}\n`);
  const deadline=Date.now()+120000;
  while(Date.now()<deadline) {
    const current=await processCreationIdentity(receipt.identity.pid,process.execPath);
    if(!current.alive||current.created_at!==identity.created_at) {
      await store.launch({profile:receipt.profile,recover:true,generation:{id:receipt.id},handoff:receipt.nonce});
      return;
    }
    await new Promise(resolve=>setTimeout(resolve,250));
  }
  throw Error('Session did not exit; the new runtime remains available for new sessions');
}
if(require.main===module)restart(process.argv[2]).catch(()=>{process.exitCode=1;});
module.exports={restart};
