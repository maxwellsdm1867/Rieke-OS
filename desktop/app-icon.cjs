'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const nativeDockIcons=new WeakMap();
const variants=new Set(['disco','rieke']);
function iconPath(variant){if(!variants.has(variant))throw new TypeError('Unknown application icon');return path.join(__dirname,variant==='rieke'?'rieke-emblem.png':'icon.png');}
function applyAppIcon(app,windows,variant,nativeImage){
 const file=iconPath(variant);
 if(process.platform==='darwin'&&app.isPackaged&&nativeImage){
  let state=nativeDockIcons.get(app);
  if(!state){
   // Capture the system-rendered bundle icon before any alternate icon is set.
   state={image:nativeImage.createFromNamedImage('NSApplicationIcon'),variant:'disco'};
   nativeDockIcons.set(app,state);
  }
  // Keep the native bundle icon at startup: replacing it with the raw PNG
  // changes its mask/scale when the process starts and again when it exits.
  if(variant!==state.variant){
   app.dock?.setIcon(variant==='disco'&&!state.image.isEmpty()?state.image:file);
   state.variant=variant;
  }
 }else app.dock?.setIcon(file);
 for(const window of windows)if(!window.isDestroyed())window.setIcon?.(file);
 return{icon:variant};
}
async function savedAppIcon(){
 try{const file=path.join(process.env.RIEKE_PREFERENCES_DIR||path.join(os.homedir(),'.rieke-os'),'appearance.json');const stat=await fs.lstat(file);if(stat.isSymbolicLink()||stat.size>4096)throw new Error('Invalid appearance preference');const saved=JSON.parse(await fs.readFile(file,'utf8'));return saved.format==='disco-appearance'&&saved.version===1&&variants.has(saved.icon)?saved.icon:'disco';}catch{return'disco';}
}
module.exports={iconPath,applyAppIcon,savedAppIcon};
