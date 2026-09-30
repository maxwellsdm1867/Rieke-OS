import {humanize} from '../api.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {Badge} from './Common.jsx';

export default function EpochDetailHeading({epoch,onQC,disabled=false}){
  return <div className="epoch-heading"><div><h2>{datedCellLabel(epoch)}</h2><p>{humanize(epoch.protocol_name?.split('.').at(-1))||'Protocol not recorded'} · Epoch {epoch.epoch_number??'—'} within block · {epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'Time not recorded'}</p></div><div className="epoch-heading-badges">{onQC&&<button disabled={disabled} onClick={()=>onQC(epoch.cell_uuid)} title="Open quality-control recordings linked to this cell">Cell QC</button>}<Badge kind={epoch.curation?.included===false?'neutral':'info'}>{epoch.curation?.included===false?'Excluded':'Included'}</Badge><Badge>{epoch.exports?.length?`${epoch.exports.length} saved exports`:'No saved export'}</Badge></div></div>;
}
