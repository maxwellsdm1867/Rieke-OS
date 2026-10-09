'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),{randomUUID,randomBytes}=require('node:crypto'),{EventEmitter}=require('node:events'),{Writable,PassThrough}=require('node:stream');
const {FORMAT,MAX_RECORD_BYTES,readProgressRecord,displayFrame,launchProgressReporter}=require('../testing-install-progress.cjs');
async function fixture(t){
 const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'disco-progress-test-'))),cache=path.join(root,'updates/unsigned-testing');await fs.mkdir(cache,{recursive:true,mode:0o700});
 const operationId='install-'+randomUUID(),capability=randomBytes(32).toString('hex'),progressPath=path.join(cache,operationId+'.json.progress.json');
 const options={operationId,capability,progressPath};const base={format:FORMAT,version:1,operation_id:operationId,capability,helper_pid:process.pid,updated_at:new Date().toISOString(),state:'Running',phase:'verify-staging',progress:37,message:'PRIVATE /Users/example/details must never appear'};
 async function write(fields={}){const temporary=progressPath+'.tmp';await fs.writeFile(temporary,JSON.stringify({...base,...fields}),{mode:0o600});await fs.rename(temporary,progressPath);}
 await write();t.after(()=>fs.rm(root,{recursive:true,force:true}));return {root,cache,options,base,write};
}
function controlled(){const calls=[],frames=[];let child;return{calls,frames,get child(){return child;},spawnReporter(executable,args,options){calls.push({executable,args,options});child=new EventEmitter();child.pid=987654;child.unref=()=>{};child.kill=()=>{throw new Error('Reporter must not signal any process');};child.stderr=new PassThrough();child.stdin=new Writable({write(data,_encoding,done){for(const line of data.toString().trim().split('\n'))frames.push(JSON.parse(line));done();}});child.stdin.on('finish',()=>queueMicrotask(()=>child.emit('exit',0)));return child;}};}
async function until(predicate){const deadline=Date.now()+2000;while(!predicate()){if(Date.now()>deadline)throw new Error('Controlled observer timed out');await new Promise(r=>setTimeout(r,5));}}
test('owned bounded record becomes fixed human phase text without exposing message or capability',async t=>{
 const f=await fixture(t),before=await fs.readFile(f.options.progressPath),r=await readProgressRecord(f.options),frame=displayFrame(r);assert.equal(r.progress,37);assert.equal(frame.label,'Verifying the copied app…');assert.equal(frame.state,'Running');assert.equal(JSON.stringify(frame).includes('PRIVATE'),false);assert.equal(JSON.stringify(frame).includes(f.options.capability),false);assert.deepEqual(await fs.readFile(f.options.progressPath),before);
});
test('rejects capability/operation mismatch, malformed percentages, stale and future records',async t=>{
 const f=await fixture(t);for(const fields of [{capability:'0'.repeat(64)},{operation_id:'install-'+randomUUID()},{progress:101},{progress:-1},{progress:'50'},{helper_pid:0},{message:'x'.repeat(513)},{updated_at:new Date(Date.now()-130000).toISOString()},{updated_at:new Date(Date.now()+10000).toISOString()}]){await f.write(fields);await assert.rejects(readProgressRecord(f.options));}
});
test('rejects redirected, shared, oversized, and non-private files',async t=>{
 const f=await fixture(t);await fs.chmod(f.options.progressPath,0o644);await assert.rejects(readProgressRecord(f.options));await f.write();
 const link=path.join(f.root,'hardlink');await fs.link(f.options.progressPath,link);await assert.rejects(readProgressRecord(f.options));await fs.rm(link);
 await fs.writeFile(f.options.progressPath,'x'.repeat(MAX_RECORD_BYTES+1));await assert.rejects(readProgressRecord(f.options));await fs.rm(f.options.progressPath);
 const target=path.join(f.root,'unrelated.json');await fs.writeFile(target,JSON.stringify(f.base),{mode:0o600});await fs.symlink(target,f.options.progressPath);await assert.rejects(readProgressRecord(f.options));
 await fs.rm(f.options.progressPath);await f.write();await fs.rename(f.cache,f.cache+'-real');await fs.symlink(f.cache+'-real',f.cache);await assert.rejects(readProgressRecord(f.options));
});
test('operation filename and private cache location are mandatory',async t=>{
 const f=await fixture(t);await assert.rejects(readProgressRecord({...f.options,progressPath:path.join(f.root,path.basename(f.options.progressPath))}));await assert.rejects(readProgressRecord({...f.options,operationId:'../other'}));
});
test('nonblocking view lifecycle sends only sanitized frames and flushes terminal state on close',async t=>{
 const f=await fixture(t),fake=controlled(),errors=[];const handle=launchProgressReporter({...f.options,...fake,onError:e=>errors.push(e),pollMs:10});
 await until(()=>fake.frames.length>0);assert.equal(fake.calls[0].executable,'/usr/bin/osascript');assert.equal(fake.calls[0].args.join(' ').includes(f.options.capability),false);assert.equal(fake.calls[0].args.join(' ').includes(f.options.progressPath),false);assert.equal(fake.frames[0].progress,37);
 await f.write({state:'Installed',phase:'request-launch',progress:null,updated_at:new Date().toISOString()});await handle.close();assert.equal((await handle.closed).reason,'closed');assert.equal(fake.frames.at(-1).state,'Installed');assert.deepEqual(errors,[]);assert.equal(JSON.stringify(fake.frames).includes('PRIVATE'),false);
});
test('changed helper identity fails the observer only and closes its view',async t=>{
 const f=await fixture(t),fake=controlled(),errors=[];const handle=launchProgressReporter({...f.options,...fake,onError:e=>errors.push(e),pollMs:10});await until(()=>fake.frames.length>0);
 await f.write({helper_pid:process.pid+1,updated_at:new Date().toISOString()});await handle.closed;assert.equal(errors.length,1);assert.equal(fake.frames.at(-1).label,'Update progress is unavailable');assert.equal(fake.frames.at(-1).state,'Deferred');
});
test('stale helper and maximum observer lifetime are bounded without process signals',async t=>{
 const f=await fixture(t),fake=controlled();let clock=Date.now();const handle=launchProgressReporter({...f.options,...fake,now:()=>clock,pollMs:10,staleMs:100,maxLifetimeMs:200});await until(()=>fake.frames.length>0);clock+=300;await handle.closed;assert.equal(handle.error.code,'PROGRESS_UNAVAILABLE');
});
test('unavailable platform and failed spawn never throw into the installer',async t=>{
 const f=await fixture(t);let calls=0;const unsupported=launchProgressReporter({...f.options,platform:'other',spawnReporter(){calls++;throw new Error('must not spawn');}});assert.equal((await unsupported.closed).reason,'unavailable');assert.equal(calls,0);
 const failed=launchProgressReporter({...f.options,spawnReporter(){throw new Error('private OS error details');}});assert.equal((await failed.closed).reason,'unavailable');assert.doesNotMatch(failed.error.message,/private OS/);
 const fake=controlled(),asynchronous=launchProgressReporter({...f.options,spawnReporter(...args){const child=fake.spawnReporter(...args);queueMicrotask(()=>child.emit('error',new Error('cannot execute')));return child;}});assert.equal((await asynchronous.closed).reason,'unavailable');
});
test('closing before startup cannot launch a late window',async t=>{
 const f=await fixture(t);let calls=0;const handle=launchProgressReporter({...f.options,spawnReporter(){calls++;throw new Error('late launch');}});await handle.close();await handle.closed;await new Promise(r=>setTimeout(r,20));assert.equal(calls,0);
});

test('atomic replacement may unlink an already-open authenticated private record',async t=>{
 const f=await fixture(t),physical=require('../physical-fs.cjs').promises,original=physical.open;let replaced=false;
 const replacement=f.options.progressPath+'.replacement';await fs.writeFile(replacement,JSON.stringify({...f.base,state:'Installed',phase:'request-launch',progress:null}),{mode:0o600});
 physical.open=async function(file,...args){const handle=await original.call(this,file,...args);if(file===f.options.progressPath&&!replaced){replaced=true;await fs.rename(replacement,f.options.progressPath);assert.equal((await handle.stat()).nlink,0);}return handle;};
 try{assert.equal((await readProgressRecord(f.options)).state,'Running');assert.equal((await readProgressRecord(f.options)).state,'Installed');}finally{physical.open=original;}
});
