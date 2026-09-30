'use strict';
const REPOSITORY = 'maxwellsdm1867/disco';
const REPOSITORIES=new Set([REPOSITORY,'maxwellsdm1867/Rieke-OS']);
function distributionPolicy(value) {
  if (value === undefined) return Object.freeze({channel:'signed',repository:REPOSITORY});
  if (value?.format !== 'rieke-desktop-distribution' || value.version !== 1 ||
      !['signed','unsigned-testing'].includes(value.channel) || !REPOSITORIES.has(value.repository))
    throw new Error('The desktop distribution policy is invalid.');
  return Object.freeze({...value});
}
module.exports={distributionPolicy};
