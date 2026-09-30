'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');
const {ServiceSupervisor,availablePort}=require('../supervisor.cjs');
test('restart capability stays in memory and requires exact same-user process, session, creation time and owned loopback listener',async t=>{
 const python=process.env.RIEKE_TEST_PYTHON;
 if(!python){t.skip('Set RIEKE_TEST_PYTHON to a local bundled Python with psutil for the isolated process test');return;}
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'rieke-owned-reconcile-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const port=await availablePort(),session='isolated-test-session',capability='isolated-test-capability-'.repeat(3);
 const program=`import socket,sys,json,os,pathlib,psutil
s=socket.socket();s.bind(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])));s.listen()
p=psutil.Process()
print(json.dumps({'pid':os.getpid(),'created_at':p.create_time(),'executable':str(pathlib.Path(p.exe()).resolve())}),flush=True)
sys.stdin.read()`;
 const child=spawn(python,['-B','-u','-c',program,'--session-id',session,'--port',String(port),'--user-state',path.join(root,'backend')],{env:{HOME:process.env.HOME,LANG:'en_US.UTF-8',RIEKE_DESKTOP_CAPABILITY:capability},stdio:['pipe','pipe','pipe']});
 t.after(()=>{child.stdin.end();});
 const packet=await new Promise((resolve,reject)=>{let output='';child.stdout.on('data',chunk=>{output+=chunk;if(output.includes('\n'))resolve(JSON.parse(output.split('\n')[0]));});child.once('error',reject);child.once('exit',code=>{if(!output.includes('\n'))reject(new Error(`Isolated helper exited before listener receipt (${code})`));});});
 const supervisor=new ServiceSupervisor({resourcesPath:root,userData:root,appVersion:'test'});supervisor.executable=python;
 const record={...packet,session_id:session,port,bound:true};
 assert.equal(await supervisor.ownedPreviousCapability({...record,session_id:'foreign-session'}),null);
 assert.equal(await supervisor.ownedPreviousCapability({...record,created_at:packet.created_at+1}),null);
 assert.equal(await supervisor.ownedPreviousCapability({...record,port:port+1}),null);
 assert.equal(await supervisor.ownedPreviousCapability({...record,entry:'/different/workspace_desktop.py'}),null);
 const originalProfile=supervisor.userData;supervisor.userData=path.join(root,'foreign-profile');
 assert.equal(await supervisor.ownedPreviousCapability(record),null);supervisor.userData=originalProfile;
 const recovered=await supervisor.ownedPreviousCapability(record);
 if(recovered===null){t.skip('This platform denies same-user process environment or listener inspection; recovery remains safely deferred');return;}
 assert.equal(recovered,capability);
 // A process that bound after an interrupted startup can be recovered from
 // current OS proof, without the old renderer or an old pipe listener.
 assert.equal(await supervisor.ownedPreviousCapability({...record,bound:false}),capability);
 assert.deepEqual(await fs.readdir(root),[]);
});
