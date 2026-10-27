'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {selectSessionProfile, runtimeLeaseFree} = require('../session-profiles.cjs');
function fixture(t) {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'disco-profile-test-'))), held=new Set();
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  function launch(requested=root,extra={}) {
    const paths={userData:requested},owned=new Set();
    const app={isPackaged:true,getPath:key=>paths[key],setPath:(key,value)=>{paths[key]=value;},
      requestSingleInstanceLock(){const key=paths.userData;if(held.has(key))return false;held.add(key);owned.add(key);return true;},
      releaseSingleInstanceLock(){for(const key of owned)held.delete(key);owned.clear();}};
    const selected=selectSessionProfile({app,runtime:'/unused',processAlive:()=>false,probe:()=>true,argv:[],...extra});
    return {...selected,paths,stop(){selected.release();app.releaseSingleInstanceLock();},crash(){app.releaseSingleInstanceLock();}};
  }
  function write(relative,value){const file=path.join(root,relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(value));}
  return {root,launch,write};
}
test('same requested profile admits independent live sessions and reuses clean slots',t=>{
  const f=fixture(t),first=f.launch(),second=f.launch();
  assert.equal(first.profile,f.root);assert.notEqual(second.profile,first.profile);
  assert.equal(second.paths.sessionData,second.profile);assert.equal(second.startAtChooser,true);
  second.stop();const third=f.launch();assert.equal(third.profile,second.profile);third.stop();first.stop();
});
test('exact slot restart preserves restoration without nesting; new session opens chooser',t=>{
  const f=fixture(t),first=f.launch(),second=f.launch();second.stop();
  const restart=f.launch(second.profile);assert.equal(restart.profile,second.profile);assert.equal(restart.base,f.root);assert.equal(restart.startAtChooser,false);
  restart.stop();first.stop();const fresh=f.launch(f.root,{argv:['--disco-new-session']});assert.equal(fresh.profile,second.profile);assert.equal(fresh.startAtChooser,true);fresh.stop();
});
test('uncertain crashed session is preserved and explicit recovery returns to exact profile',t=>{
  const f=fixture(t),first=f.launch();first.crash();const next=f.launch();assert.notEqual(next.profile,first.profile);
  assert.ok(next.recoverable().includes(first.profile));const recovered=f.launch(first.profile,{argv:['--disco-recover-session']});assert.equal(recovered.profile,first.profile);
  const occupied=f.launch(first.profile,{argv:['--disco-recover-session']});assert.equal(occupied.acquired,false);recovered.stop();next.stop();
});
test('explicit recovery with damaged slot identity fails without switching or changing records',t=>{
  const f=fixture(t),first=f.launch(),second=f.launch();second.crash();
  const identity=path.join(second.profile,'disco-profile.json');fs.writeFileSync(identity,'broken');
  assert.throws(()=>f.launch(second.profile,{argv:['--disco-recover-session']}),/invalid profile identity/);assert.equal(fs.readFileSync(identity,'utf8'),'broken');first.stop();
});
test('unsafe sessions container does not prevent healthy base startup',t=>{
  const f=fixture(t);fs.symlinkSync('/unused',path.join(f.root,'sessions'));
  const first=f.launch();assert.equal(first.profile,f.root);first.stop();
});
test('malformed ownership, live roots, retained children and held backend leases are skipped',t=>{
  for(const [file,value,extra] of [
    ['disco-session-owner.json',{format:'disco-session-owner',version:1,state:'released'},{}],
    ['desktop-service.json',{pid:12,port:1234,executable:'/exe',entry:'/entry',session_id:'x'},{processAlive:()=>true}],
    ['backend/desktop-services.json',{version:1,services:[{pid:12}]},{}],
    ['backend/desktop-services.json',{version:1,services:[]},{probe:profile=>profile!==f.root}],
  ]) {
    var f=fixture(t);f.write(file,value);const selected=f.launch(f.root,extra);assert.notEqual(selected.profile,f.root);selected.stop();
  }
});
test('only validated discovery preferences copy to a new slot',t=>{
  const f=fixture(t);f.write('backend/preferences/workspace-selection.json',{version:1,managed_root:'/owned/projects',secret:'discard'});
  f.write('backend/preferences/project-index.json',{version:1,projects:[]});f.write('startup-session.json',{secret:'never copy'});f.write('drafts/private.json',{secret:'never copy'});
  const first=f.launch(),second=f.launch(f.root,{run:()=>JSON.stringify({version:1,projects:[]})});
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(second.profile,'backend/preferences/workspace-selection.json'))),{version:1,managed_root:'/owned/projects'});
  for(const name of ['startup-session.json','drafts/private.json'])assert.equal(fs.existsSync(path.join(second.profile,name)),false);
  first.stop();second.stop();
});
test('backend lease probe rejects linked backend directory and linked lock without invoking runtime',t=>{
  const f=fixture(t);fs.symlinkSync('/unused',path.join(f.root,'backend'));
  assert.equal(runtimeLeaseFree(f.root,{run:()=>assert.fail('linked directory')}),false);
  fs.unlinkSync(path.join(f.root,'backend'));fs.mkdirSync(path.join(f.root,'backend'));fs.symlinkSync('/unused',path.join(f.root,'backend/desktop-session.lock'));
  assert.equal(runtimeLeaseFree(f.root,{run:()=>assert.fail('linked lock')}),false);
});

test('explicit recovery rejects a linked backend namespace',t=>{
  const f=fixture(t),first=f.launch();first.crash();
  fs.symlinkSync('/unused',path.join(f.root,'backend'));
  assert.throws(()=>f.launch(f.root,{argv:['--disco-recover-session']}),/invalid profile identity/);
});

test('replacement preflight scopes other processes to the same bundle and excludes own descendants',async()=>{
  const {otherDiscoProcessRunning}=require('../bootstrap.cjs');
  const bundle='/owned/Disco.app';
  const own=`${process.pid} 1 ${bundle}/Contents/MacOS/Disco\n900001 ${process.pid} ${bundle}/Contents/Helpers/child\n`;
  assert.equal(await otherDiscoProcessRunning(async()=>({stdout:own+'900002 1 /another/Disco.app/Contents/MacOS/Disco\n'}),bundle),false);
  assert.equal(await otherDiscoProcessRunning(async()=>({stdout:own+`900003 1 ${bundle}/Contents/MacOS/Disco\n`}),bundle),true);
});
