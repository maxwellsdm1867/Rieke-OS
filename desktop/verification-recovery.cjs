'use strict';
// Block synchronously, then retain accepted work/drafts through normal cleanup.
async function recoverVerificationFailure({blockNewWork,pause,saveDrafts,closeServices,showRecovery}) {
  blockNewWork();
  let pauseError;
  try {await pause();} catch(error) {pauseError=error.message;}
  let drafts;
  try {drafts=await saveDrafts();} catch(error) {drafts={ready:false,reason:error.message};}
  let services;
  try {services=await closeServices(drafts);} catch(error) {services={ready:false,reason:error.message};}
  const result={drafts,services,pauseError};
  showRecovery(result);
  return result;
}
module.exports={recoverVerificationFailure};
