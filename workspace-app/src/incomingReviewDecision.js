// Proposal decisions belong to the actor's incoming draft. Scientific curation
// remains an independent DTO and must never be rewritten to display them.
export function incomingReviewDecision(epoch){
  const decision=epoch?.review_decision;
  return decision&&decision.valid!==false&&['selected','reviewed','excluded'].every(key=>typeof decision[key]==='boolean')?decision:null;
}
export function epochIncluded(epoch,incoming=false){
  if(!incoming)return epoch?.curation?.included!==false;
  const decision=incomingReviewDecision(epoch);
  return decision?!decision.excluded:null;
}
