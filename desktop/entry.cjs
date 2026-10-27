'use strict';
const {app,dialog,BrowserWindow}=require('electron');
const path=require('node:path');
const os=require('node:os');
const {enclosingApp}=require('./bootstrap.cjs');
const {RuntimeGenerations,admitRuntime,runtimeStore}=require('./runtime-generations.cjs');
// Preview admission must precede all managed state writes.
try {
  const preview=require('./local-preview.cjs').localPreview({app});
  const policy=require('./distribution.cjs').distributionPolicy(require('./distribution.json'));
  const bundle=enclosingApp(process.execPath);
  if(preview||!app.isPackaged||process.platform!=='darwin'||policy.channel!=='unsigned-testing') {
    require('./main.cjs').startDesktop();
  } else {
    const context=admitRuntime({bundle});
    if(context)require('./main.cjs').startDesktop(context);
    else {
      const profile=require('./branding.cjs').configureBranding(app);
      // Front-door Electron must never initialize Chromium in a scientific
      // session's profile while copying/validating its future runtime.
      const store=new RuntimeGenerations({python:path.join(bundle,'Contents/Resources/runtime/python/bin/python3.11')});
      const temporary=store.createFrontDoorProfile();
      app.setPath('userData',temporary);
      app.setPath('sessionData',temporary);
      app.enableSandbox();
      let finished=false,opening;
      const openingTimer=setTimeout(()=>void app.whenReady().then(()=>{
        if(finished)return;
        opening=new BrowserWindow({width:440,height:240,title:'DISCO',show:false,resizable:false,minimizable:false,maximizable:false,
          webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true}});
        opening.once('ready-to-show',()=>{if(!finished&&!opening.isDestroyed())opening.show();});
        opening.on('close',()=>{if(!finished)app.quit();});
        void opening.loadFile(path.join(__dirname,'opening.html'));
      }),500);
      const finish=()=>{finished=true;clearTimeout(openingTimer);if(opening&&!opening.isDestroyed())opening.destroy();};
      (async()=>{
        const canonical=path.join(os.homedir(),'Applications/Disco.app');
        // A canonical front door honors the current pointer, including explicit
        // rollback. Opening a download imports it without touching live bundles.
        let current;
        if(bundle===canonical||bundle.startsWith(path.join(runtimeStore(),'generations')+path.sep))try{current=store.current();}catch{}
        if(!current)current=await store.activate(await store.stage(bundle));
        await store.launch({profile,preparation:current.generation.preparation,fresh:process.argv.includes('--disco-new-session'),recover:process.argv.includes('--disco-recover-session')});
        finish();
        app.quit();
      })().catch(error=>{finish();dialog.showErrorBox('Open DISCO',error.message);app.quit();});
    }
  }
} catch(error) { dialog.showErrorBox('Open DISCO',error.message);app.exit(1); }
