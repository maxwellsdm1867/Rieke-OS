export default function EpochAnalysisInclusion({epoch,disabled=false,onToggle,scope='selection'}){
  const included=epoch.curation?.included!==false;
  return <><label className="analysis-inclusion-toggle"><input type="checkbox" checked={included} disabled={disabled} onChange={event=>onToggle(epoch,event.target.checked)}/> Include in analysis</label><span className="analysis-inclusion-help">{included?`Included in this ${scope}’s analysis exports.`:`Excluded from this ${scope}’s analysis exports. Still available to inspect.`}</span></>;
}
