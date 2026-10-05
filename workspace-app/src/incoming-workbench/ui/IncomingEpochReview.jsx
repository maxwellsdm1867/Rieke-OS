import {Eye} from 'lucide-react';
import {incomingReviewDecision} from '../incomingReviewDecision.js';
export default function IncomingEpochReview({epoch,disabled=false,onReview}){
  const decision=incomingReviewDecision(epoch);
  if(!decision)return <p role="status">Proposal decisions unavailable. Refresh this incoming view.</p>;
  return <details className="optional-review incoming-epoch-review"><summary>Proposal review · {decision.reviewed?'Reviewed':'Not marked'}</summary>
    <p>{decision.selected?'Saved in your proposal selection.':'Not saved in your proposal selection.'} {decision.excluded?'Excluded from incoming additions; still visible.':'Allowed as an incoming addition.'}</p>
    <p>This marker belongs to your incoming draft. Shared tags and main dataset curation stay separate.</p>
    <button disabled={disabled} onClick={()=>onReview(!decision.reviewed)}><Eye size={14}/>{decision.reviewed?'Clear incoming epoch review marker':'Mark incoming epoch reviewed'}</button>
  </details>;
}
