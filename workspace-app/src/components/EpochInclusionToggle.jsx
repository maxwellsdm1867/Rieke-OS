import {epochIncluded} from '../incomingReviewDecision.js';
import {Check,X} from 'lucide-react';
import './EpochInclusionToggle.css';

export default function EpochInclusionToggle({epoch,label,onToggle,disabled=false,className='',incoming=false}){
  const included=epochIncluded(epoch,incoming),available=included!==null;
  return <button className={`epoch-inclusion-toggle ${className}`} disabled={disabled||!available} aria-label={incoming?`Allow ${label} in incoming additions`:`Include ${label} in protocol exports`} aria-pressed={available?included:undefined} title={incoming?(!available?'Proposal decision unavailable. Refresh this incoming view.':included?'Allowed as an incoming addition. Click to exclude from your draft.':'Excluded from incoming additions. Click to allow in your draft.'):(included?'Included in protocol exports. Click to exclude; recording stays visible.':'Excluded from protocol exports. Click to include; recording stays visible.')} onClick={()=>onToggle(epoch,!included)}>{!available?<span aria-hidden="true">—</span>:included?<Check size={13}/>:<X size={13}/>}</button>;
}
