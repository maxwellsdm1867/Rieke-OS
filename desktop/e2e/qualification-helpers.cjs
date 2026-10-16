'use strict';
// Keep the immutable launcher and isolation assertions; select its active document.
const helpers=require('./helpers.cjs');
const fs=require('node:fs/promises'),path=require('node:path');
const {viewNamespace,VIEW_COMPATIBILITY}=require('../startup/startup-session.cjs');
const {waitForRenderer}=require('./renderer-target.cjs');
async function launch(fixture,{renderer='application'}={}){
 const launched=await helpers.launch(fixture);
 fixture.activePage=launched.page;
 try{return {...launched,page:await waitForRenderer(launched.application,{mode:renderer,bundle:fixture.bundle})};}
 catch(error){error.launchedApplication=launched.application;error.launchedPage=launched.page;throw error;}
}
async function projectDraftPath(fixture,project){
 if(project.uuid==='launcher')throw Error('Launcher drafts use the separate root store');
 const home=await fs.realpath(fixture.home),userData=await fs.realpath(fixture.userData),projectPath=await fs.realpath(project.path);
 if(!userData.startsWith(home+path.sep)||!projectPath.startsWith(home+path.sep))throw Error('Project draft fixture escapes its owned HOME');
 return path.join(userData,'scoped-views',viewNamespace(project.uuid,projectPath,VIEW_COMPATIBILITY),'drafts',project.uuid+'.json');
}
// Only ordinary bridge Quit is attempted; timeout retains the owned fixture.
async function cleanupOwnedFixture(application,page,{timeout=45000}={}){
 if(!application)return {state:'not-launched'};
 if(application.process().exitCode!==null)return {state:'already-exited',exit_code:application.process().exitCode};
 if(!page)return {state:'owned-fixture-retained',reason:'No owned renderer handle is available for ordinary Quit'};
 let timer;
 try{
  await Promise.race([helpers.gracefulQuit(application,page),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Ordinary cleanup deadline reached')),timeout);})]);
  return {state:'orderly-exit'};
 }catch(error){return {state:'owned-fixture-retained',reason:error.message};}
 finally{clearTimeout(timer);}
}
module.exports={...helpers,launch,cleanupOwnedFixture,projectDraftPath};
