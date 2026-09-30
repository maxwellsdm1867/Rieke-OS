'use strict';
// Synthetic fixture versions only; this does not identify a published prior app.
function stableParts(value,label){
  if(typeof value!=='string'||!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(value))
    throw new Error(`${label} must be a stable major.minor.patch version`);
  const parts=value.split('.').map(Number);
  if(parts.some(value=>!Number.isSafeInteger(value)))throw new Error(`${label} stable version components exceed the safe integer range`);
  return parts;
}
function releaseVersions(candidateVersion,requestedPrior){
  const parts=stableParts(candidateVersion,'Candidate'),prior=[...parts];
  if(requestedPrior!==undefined){
    const requested=stableParts(requestedPrior,'Synthetic prior');
    const index=requested.findIndex((value,index)=>value!==parts[index]);
    if(index<0||requested[index]>=parts[index])throw new Error('Synthetic prior must be strictly older than the candidate');
    return {candidateVersion,priorVersion:requestedPrior};
  }
  const index=prior.findLastIndex(value=>value>0);
  if(index<0)throw new Error('Candidate 0.0.0 has no older stable synthetic prior version');
  prior[index]--;prior.fill(0,index+1);
  return {candidateVersion,priorVersion:prior.join('.')};
}
module.exports={releaseVersions};
