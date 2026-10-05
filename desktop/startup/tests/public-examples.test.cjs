'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {StartupSession, viewNamespace, valid} = require('../startup-session.cjs');
const projectId='00000000-0000-0000-0000-000000000001', compatibility='fixture:view-v1';
async function fixture(t) {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'disco-startup-example-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  return root;
}

test('public startup usage offers one compatible location and persists chooser or resume',async t=>{
  const root=await fixture(t), projectPath=path.join(root,'synthetic-project');
  await new StartupSession(root,compatibility).remember(projectId,projectPath,'overview');
  const next=new StartupSession(root,compatibility);await next.load();
  const offered=next.claim();assert.equal(offered.projectId,projectId);assert.equal(offered.projectPath,projectPath);
  assert.equal(valid(offered,compatibility),true);assert.equal(valid(offered,'other:view-v1'),false);
  assert.equal(next.claim(),null);
  await next.choose();
  const chooser=new StartupSession(root,compatibility);await chooser.load();assert.equal(chooser.claim(),null);
  await chooser.resume();
  const resumed=new StartupSession(root,compatibility);await resumed.load();assert.equal(resumed.claim().projectId,projectId);
  assert.notEqual(viewNamespace(projectId,projectPath,compatibility),viewNamespace(projectId,projectPath+'-copy',compatibility));
  assert.notEqual(viewNamespace(projectId,projectPath,compatibility),viewNamespace(projectId,projectPath,'other:view-v1'));
});

test('an unreadable startup preference is preserved without a restoration offer',async t=>{
  const root=await fixture(t), filename=path.join(root,'startup-session.json');
  const corrupt='{"owned-example":';await fs.writeFile(filename,corrupt);
  const session=new StartupSession(root,compatibility);await session.load();
  assert.equal(session.claim(),null);assert.equal(await fs.readFile(filename,'utf8'),corrupt);
});
