'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {assertInstallNameCompatible}=require('../install-name.cjs');
test('both released startup destinations admit same-name update and rollback, reject cross-name bootstrap',()=>{
 for(const [executable,expected] of [['Disco','Disco.app'],['Rieke OS','Rieke OS.app']]){
  for(const destination of ['Disco.app','Rieke OS.app']){
   const wouldBootstrap=destination!==expected;
   if(wouldBootstrap)assert.throws(()=>assertInstallNameCompatible(executable,'/owned/Applications/'+destination),error=>error.code==='MANUAL_APP_NAME_TRANSITION'&&/Install and Open manually/.test(error.message));
   else assert.doesNotThrow(()=>assertInstallNameCompatible(executable,'/owned/Applications/'+destination));
  }
 }
 for(const executable of ['../Disco','Unknown'])assert.throws(()=>assertInstallNameCompatible(executable,'/owned/Disco.app'));
});
