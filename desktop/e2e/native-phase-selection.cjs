'use strict';
// A focused receipt supplements prior evidence; it never claims the full suite.
function nativePhaseSelection(value){
 if(value===undefined)return{scope:'all',requestedPhases:['update','restore','rollback'],fullSuite:true};
 if(value==='rollback')return{scope:'rollback',requestedPhases:['rollback'],fullSuite:false};
 throw new Error('RIEKE_E2E_NATIVE_PHASE must be unset or rollback');
}
module.exports={nativePhaseSelection};
