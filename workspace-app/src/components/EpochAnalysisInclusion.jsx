import {epochIncluded} from '../incoming-workbench/incomingReviewDecision.js';
export default function EpochAnalysisInclusion({epoch,disabled=false,onToggle,scope='selection',incoming=false}){
  const included=epochIncluded(epoch,incoming);
  if(incoming&&included===null)return <span role="status">Proposal inclusion unavailable. Refresh this incoming view.</span>;
  return <><label className="analysis-inclusion-toggle"><input type="checkbox" checked={included} disabled={disabled} onChange={event=>onToggle(epoch,event.target.checked)}/> {incoming?'Allow as incoming addition':'Include in export'}</label><span className="analysis-inclusion-help">{incoming?(included?'Allowed as an incoming addition.':'Excluded from incoming additions. Still available to inspect.'):(included?`Included in this ${scope}’s analysis exports.`:`Excluded from this ${scope}’s analysis exports. Still available to inspect.`)}</span></>;
}
