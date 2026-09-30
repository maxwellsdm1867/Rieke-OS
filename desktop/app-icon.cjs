'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const variants=new Set(['disco','rieke']);
function iconPath(variant){if(!variants.has(variant))throw new TypeError('Unknown application icon');return path.join(__dirname,variant==='rieke'?'rieke-emblem.png':'icon.png');}
function applyAppIcon(app,windows,variant){const file=iconPath(variant);app.dock?.setIcon(file);for(const window of windows)if(!window.isDestroyed())window.setIcon?.(file);return{icon:variant};}
async function savedAppIcon(){
 try{const file=path.join(process.env.RIEKE_PREFERENCES_DIR||path.join(os.homedir(),'.rieke-os'),'appearance.json');const stat=await fs.lstat(file);if(stat.isSymbolicLink()||stat.size>4096)throw new Error('Invalid appearance preference');const saved=JSON.parse(await fs.readFile(file,'utf8'));return saved.format==='disco-appearance'&&saved.version===1&&variants.has(saved.icon)?saved.icon:'disco';}catch{return'disco';}
}
module.exports={iconPath,applyAppIcon,savedAppIcon};
