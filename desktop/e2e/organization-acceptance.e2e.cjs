'use strict';
// Actual packaged UI/native correctness only. See ORGANIZATION-ACCEPTANCE.md.
// Loading this module is inert: Playwright/scientific execution starts in main.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash,randomUUID} = require('node:crypto');
const {OwnedProcesses,within,run} = require('./organization-ownership.cjs');
const {OwnedApplication,safeMessage} = require('./organization-owned-launcher.cjs');
const ROOT = path.resolve(__dirname,'../..');
const SOURCE_FILES = ['desktop/e2e/organization-acceptance.e2e.cjs',
  'desktop/e2e/organization-ownership.cjs','desktop/e2e/organization-owned-launcher.cjs','tools/organization_e2e_fixture.py',
  'tools/organization_e2e_readback.py','desktop/e2e/ORGANIZATION-ACCEPTANCE.md'];
const LAUNCHER_DEPENDENCIES={
  'lib/coreBundle.js':'549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171',
  'types/types.d.ts':'2806f6d7810fba0306066d500cd716a6d1128d90af2c3cf71723e3ea0a8904c4',
};
const STEPS = ['preflight','clone','launch','project','import','pages','tree-selection',
  'trace','group-save','export','readback','first-quit','reopen','reopened-readback','final-quit','immutability'];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const fileSha = async name => sha(await fs.readFile(name));
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));

async function inventory(root) {
  root = await fs.realpath(root);
  const entries = [];
  async function visit(directory) {
    for (const name of (await fs.readdir(directory)).sort()) {
      const file = path.join(directory,name), stat = await fs.lstat(file);
      const item = {path:path.relative(root,file),mode:stat.mode & 0o777};
      if (stat.isSymbolicLink()) {
        item.link = await fs.readlink(file);
        assert.ok(!path.isAbsolute(item.link) && within(root,await fs.realpath(file)),'Escaping/broken bundle link');
      } else if (stat.isDirectory()) {item.directory=true; await visit(file);}
      else {assert.ok(stat.isFile(),'Unexpected bundle object'); item.size=stat.size; item.sha256=await fileSha(file);}
      entries.push(item);
    }
  }
  await visit(root);
  entries.sort((a,b)=>a.path.localeCompare(b.path,'en'));
  return {entries,sha256:sha(JSON.stringify(entries))};
}

function argumentsFrom(argv) {
  const allowed = new Set(['gate','candidate-bundle','fixture-directory','output']);
  const values = {};
  for (let i=0;i<argv.length;i+=2) {
    const key=argv[i]?.replace(/^--/,'');
    assert.ok(argv[i]?.startsWith('--')&&allowed.has(key)&&argv[i+1]&&!values[key], 'Explicit unique path arguments required');
    assert.ok(path.isAbsolute(argv[i+1]),'Use absolute paths'); values[key]=argv[i+1];
  }
  for(const key of allowed) assert.ok(values[key],`Missing --${key}`);
  return values;
}

class Acceptance {
  constructor(args) {
    this.args=args; this.page=null; this.app=null; this.process=null; this.owner=null;
    this.abort=false; this.responses=[]; this.pending=[]; this.quitRequested=false;
    this.controllerReads=new Set();this.requestSequence=0;
    this.receipt={format:'disco-organization-acceptance',version:1,status:'unrun',
      started_at:new Date().toISOString(),checks:STEPS.map(name=>({name,status:'unrun'})),
      failures:[],limits:['Synthetic correctness only; no performance or release qualification.',
      'Only owned native project-folder chooser return is substituted; no HTTP or scientific mocks.',
      'No paused legacy/Ovation/newH5port/nativeexport experiment.']};
  }
  async write() {
    await fs.writeFile(path.join(this.args.output,'receipt.json'),JSON.stringify(this.receipt,(_key,value)=>typeof value==='string'&&/(?:wss?:|Debugger listening|DevTools listening)/i.test(value)?'[debug endpoint text withheld]':value,2)+'\n',{mode:0o600});
  }
  assertActive() {
    this.app?.assertHealthy();
    assert.deepEqual(this.owner?.errors||[],[],'Ownership observation incomplete; no new mutations');
    assert.ok(!this.abort&&Date.now()<this.deadline,'Work deadline reached; no new mutations permitted');
    if(this.gate)assert.ok(Date.parse(this.gate.valid_until)>Date.now(),'Reviewed execution window expired');
    this.page?.setDefaultTimeout(Math.max(1,Math.min(20000,this.deadline-Date.now())));
  }
  budget(cap) {this.assertActive();return Math.max(1,Math.min(cap,this.deadline-Date.now()));}
  async verifyLauncherDependencies() {
    assert.equal(require('playwright/package.json').version,'1.63.0');
    assert.equal(require('playwright-core/package.json').version,'1.63.0');
    assert.equal(process.version,'v24.13.0','Reviewed Node WebSocket/runtime required');
    assert.deepEqual(this.gate.launcher_dependencies,LAUNCHER_DEPENDENCIES);
    const root=path.dirname(require.resolve('playwright-core/package.json'));
    for(const [relative,expected] of Object.entries(LAUNCHER_DEPENDENCIES)) {
      const filename=await fs.realpath(path.join(root,relative));
      assert.ok(within(await fs.realpath(root),filename));assert.equal(await fileSha(filename),expected);
    }
    this.receipt.launcher_dependency_hashes=LAUNCHER_DEPENDENCIES;
  }
  async recheckBindings() {
    await this.verifyLauncherDependencies();
    assert.equal(await fileSha(this.args.gate),this.receipt.gate_sha256);
    assert.equal(await fileSha(path.join(this.args['fixture-directory'],'fixture-receipt.json')),this.receipt.fixture_receipt_sha256);
    assert.equal(await fileSha(this.oraclePath),this.fixtureReceipt.oracle_sha256);
    for(const relative of SOURCE_FILES)assert.equal(await fileSha(path.join(ROOT,relative)),this.gate.harness_files[relative]);
    assert.equal((await run('git',['rev-parse','HEAD'],{cwd:ROOT,timeout:this.budget(10000)})).stdout.trim(),this.gate.candidate_commit);
    assert.equal((await run('git',['status','--porcelain'],{cwd:ROOT,timeout:this.budget(10000)})).stdout.trim(),'');
  }
  async step(name,fn) {
    this.assertActive(); const item=this.receipt.checks.find(row=>row.name===name); item.status='running'; await this.write();
    try {item.evidence=await fn(); this.assertActive(); item.status='passed';}
    catch(error) {item.status='failed'; item.message=error.message; throw error;}
    finally {await this.write();}
  }
  async poll(fn,{timeout=30000}={}) {
    const end=Math.min(this.deadline,Date.now()+timeout);
    do {this.assertActive(); const value=await fn(); if(value)return value; await delay(200);}while(Date.now()<end);
    throw Error('Bounded workflow observation timed out');
  }
  async api(endpoint,body) {
    this.assertActive();
    assert.ok(endpoint.startsWith('/api/')&&!endpoint.includes('://'));
    assert.ok(body===undefined||endpoint==='/api/annotations/read','Only allowlisted read POST is permitted');
    this.controllerReads.add(endpoint);
    try {return await this.page.evaluate(async ({endpoint,body,timeout})=>{
      const response=await fetch(endpoint,{method:body===undefined?'GET':'POST',
        headers:{'Content-Type':'application/json','X-Workspace-Request':'1'},
        ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(timeout)});
      const value=await response.json();if(!response.ok)throw Error(value.error||`Read failed ${response.status}`);return value;
    },{endpoint,body,timeout:this.budget(20000)});}finally{this.controllerReads.delete(endpoint);}
  }
  async screenshot(name) {await this.page.screenshot({path:path.join(this.args.output,name+'.png')});}
  async preflight() {
    // Execution requires the exact parent-approved package/runtime/fixture gate below.
    const gate=JSON.parse(await fs.readFile(this.args.gate,'utf8')); this.gate=gate;
    assert.equal(gate.format,'disco-organization-execution-gate'); assert.equal(gate.version,1);
    await this.verifyLauncherDependencies();
    assert.equal(gate.parent_review,'approved'); assert.equal(gate.status,'passed');
    assert.ok(gate.quiet_window_reference&&Date.parse(gate.valid_until)>Date.now(),'Current reviewed quiet window required');
    assert.equal(gate.candidate_bundle,await fs.realpath(this.args['candidate-bundle']));
    const {stdout:head}=await run('git',['rev-parse','HEAD'],{cwd:ROOT});
    const {stdout:dirty}=await run('git',['status','--porcelain'],{cwd:ROOT});
    assert.equal(dirty.trim(),'','Harness source must be committed and clean'); assert.equal(head.trim(),gate.candidate_commit);
    for(const relative of SOURCE_FILES) assert.equal(await fileSha(path.join(ROOT,relative)),gate.harness_files[relative]);
    for(const name of ['mapped_checks','source_closure','assembled_closure','native_audit','relocated_imports']) {
      const evidence=gate.evidence[name]; assert.equal(evidence.status,'passed'); assert.equal(evidence.candidate_commit,gate.candidate_commit);
      assert.equal(await fileSha(evidence.path),evidence.sha256,`Evidence changed: ${name}`);
    }
    this.initial=await inventory(gate.candidate_bundle); assert.equal(this.initial.sha256,gate.bundle_inventory_sha256);
    this.manifest=JSON.parse(await fs.readFile(path.join(gate.candidate_bundle,'Contents/Resources/runtime/runtime-manifest.json'),'utf8'));
    assert.equal(this.manifest.source_commit,gate.candidate_commit); assert.equal(this.manifest.source_dirty,false);
    assert.equal(this.manifest.parser_commit,'5dc9018ff754e1a01f60d929ceaf4e7f40815e70');
    const parserPath=path.join(gate.candidate_bundle,gate.packaged_parser_relative);
    assert.ok(within(gate.candidate_bundle,await fs.realpath(parserPath)));
    assert.equal(await fileSha(parserPath),'0d63fa4df6e087cda60fd85305ea3c4a7d287949abab325b9f1dd2e5f12779d2');
    const dir=await fs.realpath(this.args['fixture-directory']);
    this.fixtureReceipt=JSON.parse(await fs.readFile(path.join(dir,'fixture-receipt.json'),'utf8'));
    assert.equal(this.fixtureReceipt.status,'passed'); assert.equal(this.fixtureReceipt.parser_preflight.status,'passed');
    assert.equal(this.fixtureReceipt.generator_sha256,gate.harness_files['tools/organization_e2e_fixture.py']);
    assert.equal(await fileSha(path.join(dir,'fixture-receipt.json')),gate.fixture_receipt_sha256);
    this.input=path.join(dir,'synthetic.h5'); this.oraclePath=path.join(dir,'oracle.json');
    assert.equal(await fileSha(this.input),this.fixtureReceipt.h5_sha256);
    assert.equal(await fileSha(this.oraclePath),this.fixtureReceipt.oracle_sha256);
    this.oracle=JSON.parse(await fs.readFile(this.oraclePath,'utf8'));
    assert.equal(this.oracle.format,'disco-organization-oracle'); assert.equal(this.oracle.epochs.length,63);
    assert.equal(gate.local_author,'select-existing-default');
    assert.deepEqual(gate.extra_environment_keys,[],'No inherited app credentials or custom environment');
    this.receipt.candidate_commit=gate.candidate_commit; this.receipt.gate_sha256=await fileSha(this.args.gate);
    this.receipt.bundle_inventory_sha256=this.initial.sha256; this.receipt.fixture_receipt_sha256=gate.fixture_receipt_sha256;
    return {source_clean:true,source_package_fixture_bound:true,prerequisite_evidence_verified:true};
  }
  async clone() {
    this.root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'disco-organization-acceptance-')));
    await fs.chmod(this.root,0o700);
    this.home=path.join(this.root,'home'); this.bundle=path.join(this.home,'Applications/Disco.app');
    this.userData=path.join(this.home,'state'); this.preferences=path.join(this.home,'.rieke-os');
    this.projects=path.join(this.home,'projects'); this.downloads=path.join(this.home,'downloads');
    for(const folder of [path.dirname(this.bundle),this.userData,this.preferences,this.projects,this.downloads])await fs.mkdir(folder,{recursive:true,mode:0o700});
    await run('/usr/bin/ditto',[this.gate.candidate_bundle,this.bundle],{timeout:this.budget(90000)});
    assert.equal((await inventory(this.bundle)).sha256,this.initial.sha256);
    this.python=path.join(this.bundle,'Contents/Resources/runtime/python/bin/python3.11');
    assert.ok(within(this.bundle,await fs.realpath(this.python)));
    // No process.env spread. USER/LOGNAME retain the current local identity only.
    this.env={PATH:'/usr/bin:/bin:/usr/sbin:/sbin',HOME:this.home,TMPDIR:this.root,
      XDG_CONFIG_HOME:this.userData,RIEKE_PREFERENCES_DIR:this.preferences,PYTHONDONTWRITEBYTECODE:'1',
      LANG:'en_US.UTF-8',USER:os.userInfo().username,LOGNAME:os.userInfo().username};
    this.receipt.fixture_root=this.root;
    this.tag='organization-'+randomUUID(); this.projectName='Organization acceptance '+randomUUID().slice(0,8);
    this.projectPath=path.join(this.projects,'synthetic-project');
    await fs.writeFile(path.join(this.args.output,'bundle-inventory.json'),JSON.stringify(this.initial,null,2));
    return {fresh_owned_home:true,clone_inventory_equal:true};
  }
  async launch() {
    this.assertActive();await this.recheckBindings();
    this.responses=[];this.pending=[];
    assert.equal(require('playwright/package.json').version,'1.63.0');
    this.owner=new OwnedProcesses({python:this.python,bundle:this.bundle,home:this.home,preferences:this.preferences,env:this.env});
    this.app=new OwnedApplication({bundle:this.bundle,userData:this.userData,env:this.env,owner:this.owner,budget:cap=>this.budget(cap)});
    this.quitRequested=false;
    try {await this.app.start();}finally{this.process=this.app.process();}
    this.page=await this.app.firstWindow({timeout:this.budget(45000)});this.page.setDefaultTimeout(this.budget(20000));
    await this.owner.capture();
    const actual=await this.app.evaluate(({app,BrowserWindow})=>({packaged:app.isPackaged,name:app.getName(),version:app.getVersion(),
      appPath:app.getAppPath(),home:process.env.HOME,userData:app.getPath('userData'),preferences:process.env.RIEKE_PREFERENCES_DIR,
      electron:process.versions.electron,window:BrowserWindow.getAllWindows()[0]?.webContents.getLastWebPreferences()}));
    assert.equal(actual.packaged,true); assert.equal(actual.name,'Disco'); assert.equal(actual.version,this.manifest.application_version);
    assert.equal(actual.home,this.home); assert.equal(actual.userData,this.userData); assert.equal(actual.preferences,this.preferences);
    assert.ok(within(this.bundle,actual.appPath)); assert.equal(actual.electron,'44.5.0');
    const preferences=await this.app.evaluate(({BrowserWindow})=>{
      const value=BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();
      return {sandbox:value.sandbox,contextIsolation:value.contextIsolation,nodeIntegration:value.nodeIntegration,webSecurity:value.webSecurity};
    });
    assert.deepEqual(preferences,{sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true});
    this.page.on('pageerror',error=>this.receipt.failures.push({kind:'pageerror',message:error.message}));
    this.page.on('crash',()=>this.receipt.failures.push({kind:'renderer-crash'}));
    this.page.on('request',request=>{
      const url=new URL(request.url());
      if(request.method()==='POST'&&url.pathname==='/api/annotation-profiles')this.receipt.failures.push({kind:'forbidden-profile-create'});
    });
    this.page.on('response',response=>{
      const url=new URL(response.url());
      if(url.pathname==='/api/tree-pages'||url.pathname==='/api/annotations/group'||url.pathname.startsWith('/api/annotations/group-')||url.pathname.endsWith('/trace')) {
        const provenance={path:url.pathname,url:response.url(),session_id:this.session,request_id:++this.requestSequence,
          controller_read:this.controllerReads.has(url.pathname+url.search),status:response.status()};
        const pending=response.json().then(value=>this.responses.push({...provenance,value}))
          .catch(error=>this.receipt.failures.push({kind:'observed-response-read',message:error.message}));
        this.pending.push(pending);
      }
    });
    await this.page.getByRole('heading',{name:'Your projects',exact:true}).waitFor({timeout:this.budget(90000)});
    assert.match(this.page.url(),/^http:\/\/127\.0\.0\.1:\d+/);
    const service=JSON.parse(await fs.readFile(path.join(this.userData,'desktop-service.json'),'utf8'));
    assert.ok(within(this.bundle,service.executable)); assert.ok(service.session_id);
    this.session=service.session_id;
    await this.screenshot('launcher-'+(this.firstSession?'reopen':'first'));
    return {packaged:true,version:actual.version,session_id:this.session,isolation_verified:true};
  }
  async selectAuthor() {
    const profiles=await this.api('/api/annotation-profiles');
    const existing=profiles.profiles.find(row=>row.profile_uuid===profiles.default_profile_uuid);
    assert.ok(existing&&profiles.attribution==='local_profile_not_authentication');
    if(profiles.selected_profile_uuid!==existing.profile_uuid) {
      const dialog=this.page.getByRole('dialog',{name:'Tag author',exact:true});
      if(!await dialog.isVisible())await this.page.getByRole('button',{name:'Choose tag author profile',exact:true}).click();
      this.assertActive();
      await dialog.getByRole('button',{name:existing.display_name,exact:true}).click();
      await dialog.waitFor({state:'hidden'});
    }
    const selected=await this.api('/api/annotation-profiles');assert.equal(selected.selected_profile_uuid,existing.profile_uuid);
    this.profile=existing.profile_uuid; // Deliberately omit OS display name from receipt.
  }
  async createProject() {
    await this.page.getByRole('button',{name:/^Create a new project/}).click();
    const form=this.page.locator('.onboarding-create-form');await form.getByRole('textbox').first().fill(this.projectName);
    await this.app.evaluate(({dialog},directory)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[directory]});},this.projects);
    await form.getByRole('button',{name:'Browse: New project folder',exact:true}).click();
    const picker=this.page.getByRole('dialog',{name:'New project folder',exact:true});
    await picker.getByRole('checkbox',{name:'Create a new folder inside this location'}).check();
    await picker.getByRole('textbox',{name:'New folder name',exact:true}).fill('synthetic-project');
    this.assertActive();
    await picker.getByRole('button',{name:'Use new folder',exact:true}).click();
    assert.equal(await form.locator('#new-project-directory').inputValue(),this.projectPath);
    this.assertActive();
    await form.getByRole('button',{name:'Create & open',exact:true}).click();
    await this.page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:this.budget(90000)});
    this.project=(await this.api('/api/projects')).current_project_uuid; assert.ok(this.project);
    this.firstSession=this.session;await this.selectAuthor();await this.projectOwnership();
    return {project_uuid:this.project,project_path:this.projectPath,existing_default_author_selected:true};
  }
  async importRecording() {
    await this.page.getByRole('button',{name:'Data stores',exact:true}).click();
    await this.page.getByRole('button',{name:'Import H5s',exact:true}).click();
    const chooser=this.page.waitForEvent('filechooser');await this.page.getByRole('button',{name:'Browse H5 files',exact:true}).click();
    this.assertActive();
    await (await chooser).setFiles(this.input);
    const job=await this.poll(async()=>{
      const jobs=(await this.api('/api/jobs')).jobs; assert.ok(jobs.length<=1,'Unexpected import history');
      const row=jobs[0]; if(!row)return false;
      if(['failed','interrupted','duplicate','complete_with_warnings'].includes(row.status))throw Error(`Import terminal state ${row.status}`);
      return row.status==='complete'?row:false;
    },{timeout:120000});
    assert.equal(job.requires_reconciliation||false,false); assert.deepEqual(job.warnings||[],[]);
    assert.equal(job.source_sha256,this.fixtureReceipt.h5_sha256);
    assert.equal(job.recording_storage?.verified,true); assert.ok(within(this.projectPath,await fs.realpath(job.recording_storage.path)));
    assert.equal(await fileSha(job.recording_storage.path),this.fixtureReceipt.h5_sha256);
    this.managedSource=job.recording_storage.path;
    const overview=await this.api('/api/overview'); assert.equal(overview.sources.length,1);
    assert.equal(overview.counts.epochs,63); assert.equal(overview.counts.cells,2); assert.equal(overview.protocols.length,1);
    this.protocol=overview.protocols[0].protocol_uuid;
    const detail=await this.api('/api/data-stores/'+this.fixtureReceipt.h5_sha256);
    assert.deepEqual(detail.parser.warnings,[{code:'experiment_identity_restored',parser_uuid:this.oracle.animal_uuid,source_uuid:this.oracle.experiment_uuid}]);
    const source=overview.sources[0];
    assert.equal(source.experiment_uuid,this.oracle.experiment_uuid);
    assert.equal(source.source_sha256,this.fixtureReceipt.h5_sha256);
    assert.equal(source.metadata.uuid,this.oracle.experiment_uuid);
    assert.equal(source.metadata.label,this.oracle.root_label);
    assert.deepEqual(source.metadata.properties,this.oracle.root_properties);
    const review=this.page.getByRole('dialog',{name:'Review imported data',exact:true});
    if(!await review.isVisible())await this.page.getByRole('button',{name:/^Review import —/}).click();
    await review.waitFor();await this.screenshot('import-complete');
    await review.getByRole('button',{name:'Done reviewing',exact:true}).click();
    return {source_sha256:job.source_sha256,epochs:63,cells:2,protocols:1,expected_restoration_warning:detail.parser.warnings};
  }
  async pages() {
    for(const [name,heading] of [['Project overview',this.projectName],['Data stores','Data stores'],['Logs','Activity']]) {
      await this.page.getByRole('button',{name,exact:true}).click();
      await this.page.getByRole('heading',{name:heading,exact:true}).waitFor();await this.screenshot(name.toLowerCase().replaceAll(' ','-'));
    }
    await this.openInspection();return {actual_pages:['Project overview','Data stores','Logs','protocol inspection']};
  }
  async openInspection() {
    await this.page.getByRole('button',{name:'Project overview',exact:true}).click();
    await this.page.locator('.ov-protocol-row:visible').first().click();
    await this.page.getByRole('button',{name:'Go to epochs',exact:true}).click();
    await this.page.getByRole('button',{name:'Split tree',exact:true}).click();
    await this.page.getByRole('tree',{name:'Recording hierarchy',exact:true}).waitFor();
  }
  async expandTo(identity) {
    // Fixture has one date, two cells, one block each. Expand actual controls,
    // bounded by this known tiny topology, never inspect or mutate React state.
    const tree=this.page.getByRole('tree',{name:'Recording hierarchy',exact:true});
    for(let n=0;n<8;n++) {
      if(await tree.locator(`[data-epoch-uuid="${identity}"]`).count())return;
      const closed=tree.locator('li.ht-branch > button[aria-expanded="false"]');
      assert.ok(await closed.count(),'Expected synthetic tree branch is absent');await closed.first().click();
      await this.poll(async()=>!(await tree.locator('.ht-loading').count()));
    }
    throw Error('Synthetic branch expansion exceeded known topology');
  }
  async selectedOnPage() {
    return this.page.locator('.hierarchy-tree [data-epoch-uuid].selected').evaluateAll(nodes=>nodes.map(n=>n.dataset.epochUuid));
  }
  async treeSelection() {
    const [first,last]=this.oracle.selection_ids;await this.expandTo(first);
    const leaf=this.page.locator(`[data-epoch-uuid="${first}"]`);await leaf.click();
    const branch=leaf.locator('xpath=../..');
    assert.equal(await branch.locator('[data-epoch-uuid]').count(),60);
    await branch.getByRole('button',{name:'Next Epochs page',exact:true}).click();
    await this.page.locator(`[data-epoch-uuid="${last}"]`).click({modifiers:['Shift']});
    await this.poll(async()=>JSON.stringify(await this.selectedOnPage())===JSON.stringify([last]));
    await Promise.all(this.pending);
    const pages=this.responses.filter(row=>row.path==='/api/tree-pages'&&row.value.kind==='epochs'&&row.value.total===61).map(row=>row.value);
    const before=pages.find(row=>row.offset===0),after=pages.find(row=>row.offset===60);
    assert.ok(before&&after);assert.equal(before.revision,after.revision);assert.deepEqual(before.path,after.path);
    assert.deepEqual(before.epochs.map(e=>e.epoch_uuid),this.oracle.cells[0].epoch_ids.slice(0,60));
    assert.deepEqual(after.epochs.map(e=>e.epoch_uuid),[last]);
    await this.page.getByRole('button',{name:'Previous Epochs page',exact:true}).click();
    await this.poll(async()=>JSON.stringify(await this.selectedOnPage())===JSON.stringify([first]));
    await this.screenshot('selection-first-page');
    await this.page.getByRole('button',{name:'Next Epochs page',exact:true}).click();
    await this.poll(async()=>JSON.stringify(await this.selectedOnPage())===JSON.stringify([last]));
    await this.screenshot('selection-second-page');
    return {exact_ids:[first,last],first_page_selected:[first],second_page_selected:[last],branch_revision:before.revision,off_page_rows_not_assumed_present:true};
  }
  async trace() {
    const expected=this.oracle.epochs[60];await this.expandTo(expected.uuid);
    // Shift selection already focuses this row; plain click on reopen focuses it.
    await this.page.locator(`[data-epoch-uuid="${expected.uuid}"]`).click();
    await this.page.getByRole('region',{name:'Recorded response viewer',exact:true}).waitFor();
    await this.page.waitForFunction(()=>{const canvas=document.querySelector('.tv-base');return canvas?.width>0&&!document.querySelector('.tv-loading')&&!document.querySelector('.tv-error');});
    await Promise.all(this.pending);
    const painted=this.responses.filter(row=>row.path===`/api/epochs/${expected.uuid}/trace`&&row.status===200&&row.session_id===this.session&&!row.controller_read).at(-1);
    assert.ok(painted,'Actual renderer trace request was not observed');
    const assertTrace=value=>{
      assert.equal(value.epoch_uuid,expected.uuid);assert.equal(value.stream_uuid,expected.stream_uuid);
      assert.equal(value.sample_rate,10000);assert.equal(value.units,'pA');assert.equal(value.decimated,false);
      assert.equal(value.values.length,value.count);
      assert.deepEqual(value.values,Array.from({length:value.count},(_,i)=>expected.ordinal+(value.start+i)/256));
    };
    assertTrace(painted.value);
    assert.equal(painted.value.start,0);assert.equal(painted.value.count,256);
    await this.page.getByRole('spinbutton',{name:'Exact sample index for cursor',exact:true}).fill('17');
    await this.poll(async()=>
      await this.page.getByLabel('Recorded sample index',{exact:true}).textContent()==='17'&&
      await this.page.getByLabel('Time from stream start in seconds',{exact:true}).textContent()==='0.0017 s'&&
      await this.page.getByLabel('Recorded response and scientific units',{exact:true}).textContent()===`${expected.ordinal+17/256} pA`);
    const raw=await this.api(`/api/epochs/${expected.uuid}/trace?stream_uuid=${expected.stream_uuid}&start=17&count=127`);assertTrace(raw);
    assert.equal(raw.start,17);assert.equal(raw.count,127);
    await this.screenshot('trace-'+(this.reopened?'reopened':'first'));
    return {rendered_canvas:true,actual_cursor_readout:{sample:17,time_seconds:0.0017,value:expected.ordinal+17/256,units:'pA'},
      observed_renderer_trace:{session_id:painted.session_id,request_id:painted.request_id,url:painted.url},
      analytic_exact:true,supplemental_raw_window:{start:17,count:127},epoch_uuid:expected.uuid};
  }
  async verifyTags() {
    const ids=[...this.oracle.tag_ids,this.oracle.epochs[0].uuid];
    const read=await this.api('/api/annotations/read',{target_kind:'epoch',target_uuids:ids});
    for(const id of ids) {
      const matches=read.targets[id].tags.filter(row=>row.tag===this.tag&&row.profile_uuid===this.profile);
      assert.equal(matches.length,this.oracle.tag_ids.includes(id)?1:0);
    }
    return {tag:this.tag,profile_uuid:this.profile,exact_targets:this.oracle.tag_ids,negative_control:ids[2]};
  }
  async groupSave() {
    await this.expandTo(this.oracle.tag_ids[0]);
    const tree=this.page.getByRole('tree',{name:'Recording hierarchy',exact:true});
    const cellButton=tree.locator('li.ht-branch > button').filter({hasText:'Synthetic cell B'});
    assert.equal(await cellButton.count(),1);
    await cellButton.locator('xpath=..').locator(':scope > button.tree-group-tag-button').click();
    const dialog=this.page.getByRole('dialog',{name:'Tag this group',exact:true});
    await dialog.getByRole('button',{name:'Tag matching epochs · 2 epochs',exact:true}).click();
    await dialog.getByRole('combobox',{name:'Tag 2 selected epochs',exact:true}).fill(this.tag);
    this.assertActive();
    await dialog.getByRole('button',{name:'Add selected tag',exact:true}).click();
    await dialog.waitFor({state:'hidden',timeout:this.budget(30000)});await Promise.all(this.pending);
    const preview=this.responses.find(row=>row.path==='/api/annotations/group-preview');
    const saved=this.responses.find(row=>row.value?.format==='rieke-group-annotation-receipt');
    assert.ok(preview&&saved);assert.equal(preview.value.count,2);assert.equal(preview.value.profile_uuid,this.profile);
    assert.equal(saved.status,200);assert.ok(saved.value.operation_uuid);
    assert.equal(saved.value.target_count,2);assert.equal(saved.value.profile_uuid,this.profile);assert.equal(saved.value.tag,this.tag);
    return {...await this.verifyTags(),operation_uuid:saved.value.operation_uuid,opaque_group_save_observed:true};
  }
  async saveDownload(filename,click) {
    assert.ok(within(this.downloads,filename));await assert.rejects(fs.lstat(filename),{code:'ENOENT'});
    await this.app.evaluate(({session},filename)=>{
      global.__organizationDownload=new Promise(resolve=>session.fromPartition('rieke-desktop').once('will-download',(_event,item)=>{
        item.setSavePath(filename);item.once('done',(_e,state)=>resolve({state,path:item.getSavePath(),url:item.getURL()}));
      }));
    },filename);
    await click();
    const result=await Promise.race([this.app.evaluate(()=>global.__organizationDownload,undefined,{timeout:this.budget(90000)}),delay(this.budget(90000)).then(()=>{throw Error('Download timed out');})]);
    assert.equal(result.state,'completed');assert.equal(result.path,filename);assert.equal(new URL(result.url).origin,new URL(this.page.url()).origin);
    return {sha256:await fileSha(filename),size:(await fs.stat(filename)).size};
  }
  async exports() {
    const exports={};
    for(const [format,radio,label,filename] of [
      ['wheeler-sqlite',/Wheeler SQL database/,'Download SQLite database','recordings.sqlite'],
      ['matlab-mat',/MATLAB data \(\.mat\)/,'Download MAT data','recordings.mat']]) {
      await this.page.getByRole('button',{name:'Export',exact:true}).first().click();
      const dialog=this.page.getByRole('dialog',{name:'Export protocol',exact:true});
      await dialog.getByRole('radio',{name:radio}).check();await dialog.getByRole('button',{name:'All protocol recordings',exact:true}).click();
      await dialog.getByRole('combobox',{name:'Export membership policy',exact:true}).selectOption('include_unreviewed');
      await dialog.getByRole('textbox',{name:'Export name',exact:true}).fill('Synthetic organization '+format);
      const responsePromise=this.page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname===`/api/protocols/${this.protocol}/exports`);
      this.assertActive();
      await dialog.getByRole('button',{name:'Save & export 63 epochs',exact:true}).click();
      const response=await responsePromise;assert.equal(response.status(),200);
      const posted=response.request().postDataJSON();assert.equal(posted.format,format);assert.deepEqual(posted.filters,{});assert.ok(posted.query_revision);
      exports[format]=await this.saveDownload(path.join(this.downloads,filename),()=>dialog.getByRole('link',{name:label,exact:true}).click());
      await dialog.getByRole('button',{name:'Close protocol export',exact:true}).click();
    }
    this.exportHashes=exports;return {all_protocol_epochs:63,formats:exports};
  }
  async readback(name) {
    await this.recheckBindings();
    const output=path.join(this.args.output,name+'.json');
    await run(this.python,['-I','-B',path.join(ROOT,'tools/organization_e2e_readback.py'),
      '--oracle',this.oraclePath,'--sqlite',path.join(this.downloads,'recordings.sqlite'),
      '--mat',path.join(this.downloads,'recordings.mat'),'--project-root',this.projectPath,
      '--source-sha256',this.fixtureReceipt.h5_sha256,'--tag',this.tag,'--profile-uuid',this.profile,'--output',output],
      {env:this.env,timeout:this.budget(60000),maxBuffer:1024*1024});
    const result=JSON.parse(await fs.readFile(output,'utf8'));assert.equal(result.status,'passed');return result;
  }
  async quit() {
    assert.ok(this.process&&this.app);
    const exit=this.process.exitCode!==null?Promise.resolve(this.process.exitCode):new Promise(resolve=>this.process.once('exit',resolve));
    const quitDeadline=Date.now()+45000;
    const waitBounded=promise=>Promise.race([promise,delay(Math.max(1,quitDeadline-Date.now())).then(()=>{throw Error('Ordinary quit deadline; fixture retained');})]);
    if(!this.quitRequested) {
      this.quitRequested=true;
      let result, bridgeUnavailable=!this.page;
      if(this.page) {
        try {
          result=await waitBounded(this.page.evaluate(()=>
            typeof window.riekeDesktop?.quit==='function'?window.riekeDesktop.quit():{bridge_unavailable:true}));
          bridgeUnavailable=result?.bridge_unavailable===true;
        }catch(error) {
          if(!/Target.*closed|has been closed|Execution context was destroyed/.test(error.message))throw error;
          bridgeUnavailable=true;
        }
      }
      // A reported deferred quit must never be bypassed. Missing/destroyed
      // renderer IPC can use app.quit, which invokes the same orderly handler.
      if(result?.ready===false)throw Error('Ordinary quit deferred: '+(result.reason||'writer/recovery'));
      if(bridgeUnavailable&&this.process.exitCode===null) {
        try {await waitBounded(this.app.evaluate(({app})=>{app.quit();},undefined,{timeout:Math.max(1,quitDeadline-Date.now())}));}
        catch(error){if(!/Target.*closed|has been closed|Execution context was destroyed|Main context disconnected/.test(error.message))throw error;}
      }
    }
    this.app.markQuitDelivered();
    const code=await waitBounded(exit);
    const instrumentation=await this.app.disconnect();
    assert.equal(instrumentation.instrumentation_sockets_closed,true);
    this.app.assertHealthy();
    assert.equal(code,0);
    assert.ok(this.owner,'Ownership observation never established; quit occurred but cleanup unproven');
    const ownership=await this.owner.assertExited();
    await assert.rejects(fs.lstat(path.join(this.userData,'desktop-service.json')),{code:'ENOENT'});
    if(this.project) {
      const native=JSON.parse(await fs.readFile(path.join(this.projectPath,'database/native-owner.json'),'utf8'));
      assert.equal(native.project_uuid,this.project);assert.equal(native.clean_shutdown,true);
      assert.equal(native.last_project_path,this.projectPath);
      await assert.rejects(fs.lstat(path.join(this.projectPath,'database/native-runtime.json')),{code:'ENOENT'});
      const servicesPath=path.join(this.userData,'backend/desktop-services.json');
      try {const services=JSON.parse(await fs.readFile(servicesPath,'utf8'));assert.deepEqual(services.services,[]);assert.deepEqual(services.database_operations,[]);}
      catch(error){if(error.code!=='ENOENT')throw error;}
    }
    this.receipt.process_sessions||=[];this.receipt.process_sessions.push({session_id:this.session,records:this.owner.snapshot(),launcher:this.app.evidence(),exit_code:code});
    this.app=null;this.page=null;this.process=null;
    return {...ownership,exit_code:0,root_service_record_removed:true};
  }
  async reopen() {
    await this.launch();assert.notEqual(this.session,this.firstSession);
    await this.page.getByRole('button',{name:new RegExp('^Open '+this.projectName+',')}).click();
    await this.page.getByRole('button',{name:'Project overview',exact:true}).waitFor({timeout:this.budget(90000)});
    assert.equal((await this.api('/api/projects')).current_project_uuid,this.project);
    const profiles=await this.api('/api/annotation-profiles');assert.equal(profiles.selected_profile_uuid,this.profile);
    await this.verifyTags();const exports=(await this.api('/api/exports')).exports;assert.equal(exports.length,2);
    this.reopened=true;await this.openInspection();
    if(!await this.page.locator(`[data-epoch-uuid="${this.oracle.selection_ids[1]}"]`).count()) {
      await this.expandTo(this.oracle.selection_ids[0]);
      await this.page.getByRole('button',{name:'Next Epochs page',exact:true}).click();
    }
    await this.trace();await this.projectOwnership();return {same_project_uuid:true,new_session:true,tags_and_exports_persisted:true,trace_exact:true};
  }
  async projectOwnership() {
    const processes=await this.owner.capture();
    const services=JSON.parse(await fs.readFile(path.join(this.userData,'backend/desktop-services.json'),'utf8'));
    assert.equal(services.services.length,1);
    const record=services.services[0];
    assert.equal(record.project_uuid,this.project);assert.equal(record.project_path,this.projectPath);
    assert.equal(record.session_id,this.session);assert.equal(record.bound,true);
    assert.equal(record.source_commit,this.gate.candidate_commit);
    assert.ok(processes.some(row=>row.pid===record.pid&&row.created===record.created_at&&row.executable===record.executable));
    assert.ok(processes.some(row=>path.basename(row.executable)==='mysqld'),'Real owned native database process required');
    await this.owner.verifyNativeSocket(this.projectPath,this.project);
  }
  async main() {
    assert.equal(await fs.realpath(path.dirname(this.args.output)),path.dirname(this.args.output),'Canonical output parent required');
    assert.ok(!within(ROOT,this.args.output)&&!within(this.args['candidate-bundle'],this.args.output),'Evidence must remain outside source and package');
    await fs.mkdir(this.args.output,{mode:0o700}); // exclusive; never overwrite a prior run
    this.deadline=Date.now()+600000;this.receipt.status='running';await this.write();
    // Cooperative expiry: never initiate quit concurrently with an unfinished UI
    // operation. Bounded locator/API calls unwind to step's failure handler.
    const interrupted=()=>{this.abort=true;this.receipt.failures.push({kind:'controller-interrupt',message:'No new work; ordinary quit only'});};
    for(const signal of ['SIGINT','SIGTERM','SIGHUP'])process.on(signal,interrupted);
    const watchdog=setTimeout(()=>{this.abort=true;},600000);
    const hard=setTimeout(()=>{
      this.abort=true;this.receipt.status='failed';
      this.receipt.failures.push({kind:'total-deadline',message:'Controller deadline; owned fixture retained, cleanup unproven'});
      this.receipt.failure_cleanup={status:'blocked',fixture_retained:this.root};
      void Promise.allSettled([this.write(),this.app?.disconnect()]).finally(()=>process.exit(1));
    },660000);
    try {
      for(const [name,fn] of [['preflight',()=>this.preflight()],['clone',()=>this.clone()],['launch',()=>this.launch()],
        ['project',()=>this.createProject()],['import',()=>this.importRecording()],['pages',()=>this.pages()],
        ['tree-selection',()=>this.treeSelection()],['trace',()=>this.trace()],['group-save',()=>this.groupSave()],
        ['export',()=>this.exports()],['readback',()=>this.readback('readback')],['first-quit',()=>this.quit()],
        ['reopen',()=>this.reopen()],['reopened-readback',()=>this.readback('reopened-readback')],['final-quit',()=>this.quit()],
        ['immutability',async()=>{await this.recheckBindings();assert.equal((await inventory(this.bundle)).sha256,this.initial.sha256);
          assert.equal((await inventory(this.gate.candidate_bundle)).sha256,this.initial.sha256);
          assert.equal(await fileSha(this.input),this.fixtureReceipt.h5_sha256);assert.equal(await fileSha(this.managedSource),this.fixtureReceipt.h5_sha256);
          assert.deepEqual(this.receipt.failures,[]);return {bundle_and_sources_unchanged:true};}]])await this.step(name,fn);
      this.receipt.status='passed';await this.write();
    }catch(error){await this.finishFailure(error);process.exitCode=1;}
    finally {clearTimeout(watchdog);
      // Retained app OR timed-out no-signal helper handles may keep Node alive.
      // An unref cap permits idle exit yet still bounds those referenced handles.
      // Non-forwarding signal handlers remain until controller exit.
      hard.unref();
      try {await this.owner?.stopObservation();}
      catch(error){this.receipt.status='failed';this.receipt.failures.push({kind:'observer-stop',message:error.message});await this.write();process.exitCode=1;}
    }
  }
  async finishFailure(error) {
    if(this.finishing)return this.finishing;
    this.abort=true;
    this.finishing=(async()=>{
      this.receipt.status='failed';this.receipt.failures.push({kind:'workflow',message:error.message});await this.write();
      if(this.app) {
        try {this.receipt.failure_cleanup={status:'passed',evidence:await this.quit()};}
        catch(cleanup) {this.receipt.failure_cleanup={status:'failed',message:safeMessage(cleanup),fixture_retained:this.root};}
        if(this.app){this.receipt.launcher_failure=this.app.evidence();this.receipt.instrumentation_cleanup=await this.app.disconnect();}
      }
      try {await this.owner?.stopObservation();}
      catch(observation){this.receipt.failures.push({kind:'observer-stop',message:observation.message});}
      if(this.owner)this.receipt.last_owned_processes=this.owner.snapshot();
      await this.write();
    })();return this.finishing;
  }
}

if(require.main===module)new Acceptance(argumentsFrom(process.argv.slice(2))).main().catch(error=>{console.error(safeMessage(error));process.exitCode=1;});
module.exports={inventory,argumentsFrom};
