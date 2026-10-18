'use strict';
// macOS shows a localized name in the menu bar and Dock only when the raw
// CFBundleName/CFBundleDisplayName equal the bundle filename (Disco) and
// LSHasLocalizedDisplayName is set. The raw names stay Disco because installed
// updaters require Disco.app and Electron finds "<CFBundleName> Helper" from
// the raw Info.plist; only the shown name becomes DISCO.
const fs=require('node:fs/promises');
const path=require('node:path');
const DISPLAY_NAME='DISCO';
const infoPlistStrings=(name=DISPLAY_NAME,menu=DISPLAY_NAME)=>`"CFBundleDisplayName" = "${name}";\n"CFBundleName" = "${menu}";\n`;
// Every bundled localization needs the strings: macOS picks the user's
// language folder and falls back to the raw Disco name when it lacks them.
async function writeLocalizedDisplayName(app,{name=DISPLAY_NAME}={}){
  const resources=path.join(app,'Contents/Resources');
  const folders=(await fs.readdir(resources)).filter(entry=>entry.endsWith('.lproj'));
  if(!folders.includes('en.lproj')){await fs.mkdir(path.join(resources,'en.lproj'));folders.push('en.lproj');}
  for(const folder of folders)await fs.writeFile(path.join(resources,folder,'InfoPlist.strings'),infoPlistStrings(name));
  return folders.sort();
}
module.exports={DISPLAY_NAME,infoPlistStrings,writeLocalizedDisplayName};
