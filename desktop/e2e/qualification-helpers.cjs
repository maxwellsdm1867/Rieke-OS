'use strict';
// Keep the immutable launcher and isolation assertions; select its active document.
const helpers=require('./helpers.cjs');
const {waitForRenderer}=require('./renderer-target.cjs');
async function launch(fixture,{renderer='application'}={}){
 const launched=await helpers.launch(fixture);
 fixture.activePage=launched.page;
 try{return {...launched,page:await waitForRenderer(launched.application,{mode:renderer,bundle:fixture.bundle})};}
 catch(error){error.launchedApplication=launched.application;error.launchedPage=launched.page;throw error;}
}
module.exports={...helpers,launch};
