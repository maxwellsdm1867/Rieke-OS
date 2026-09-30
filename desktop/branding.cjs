'use strict';
// Product labels change; the existing profile, drafts and receipts do not move.
function configureBranding(app){
  app.setName('Rieke OS');
  const legacyUserData=app.getPath('userData');
  app.setName('Disco');
  app.setPath('userData',legacyUserData);
  return legacyUserData;
}
module.exports={configureBranding};
