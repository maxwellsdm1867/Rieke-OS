'use strict';
// A small presentation preference, never a runtime or scientific authority.
const fs=require('node:fs/promises'),path=require('node:path');
const {createHash}=require('node:crypto');
const {atomicJSON}=require('../supervisor.cjs');
const {validateProjectId}=require('../security.cjs');
const FORMAT='disco-startup-session';
// Presentation compatibility follows the saved schema, not the app release.
const VIEW_COMPATIBILITY='view-v1';
const LEGACY_VIEW_COMPATIBILITIES=['0.1.9:view-v1','0.1.8:view-v1'];
function compatibleViews(compatibility){
  return compatibility===VIEW_COMPATIBILITY?[compatibility,...LEGACY_VIEW_COMPATIBILITIES]:[compatibility];
}
function valid(value,compatibility){
  return value?.format===FORMAT&&value.version===1&&value.compatibility===compatibility&&
    ['resume','chooser'].includes(value.mode)&&typeof value.projectPath==='string'&&path.isAbsolute(value.projectPath)&&
    path.normalize(value.projectPath)===value.projectPath&&typeof value.projectId==='string'&&value.projectId!=='launcher'&&
    validateProjectId(value.projectId)===value.projectId;
}
function viewNamespace(projectId,projectPath,compatibility='view-v1'){
  validateProjectId(projectId);if(!path.isAbsolute(projectPath))throw Error('Expected canonical project path');
  return createHash('sha256').update(JSON.stringify([projectId,projectPath,compatibility])).digest('hex');
}
class StartupSession {
  constructor(userData,compatibility){this.file=path.join(userData,'startup-session.json');this.compatibility=compatibility;this.value=null;this.claimed=false;this.cancelled=false;this.chain=Promise.resolve();}
  async load(){
    try{const stat=await fs.lstat(this.file);if(!stat.isFile()||stat.isSymbolicLink()||stat.uid!==process.getuid()||stat.size>16384)return;
      const value=JSON.parse(await fs.readFile(this.file,'utf8'));
      if(compatibleViews(this.compatibility).some(version=>valid(value,version)))this.value={...value,compatibility:this.compatibility};
    }catch{} // Unknown/corrupt/older state is preserved and opens the chooser.
  }
  claim(){if(this.claimed)return null;this.claimed=true;this.target=!this.cancelled&&this.value?.mode==='resume'?{...this.value}:null;return this.target;}
  save(value){this.value=value;const next={...value};this.chain=this.chain.catch(()=>{}).then(()=>atomicJSON(this.file,next));return this.chain;}
  remember(projectId,projectPath,view){
    const value={format:FORMAT,version:1,compatibility:this.compatibility,mode:this.preference||this.value?.mode||'resume',projectId,projectPath,view:typeof view==='string'?view.slice(0,80):'overview'};
    if(!valid(value,this.compatibility))throw Error('Invalid startup session');return this.save(value);
  }
  async choose(){this.cancelled=true;this.preference='chooser';if(this.value)await this.save({...this.value,mode:'chooser'});}
  async resume(){this.cancelled=false;this.preference='resume';if(this.value)await this.save({...this.value,mode:'resume'});}
}
module.exports={StartupSession,viewNamespace,valid,VIEW_COMPATIBILITY,compatibleViews};
