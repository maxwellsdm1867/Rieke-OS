import {Check,X} from 'lucide-react';
import './EpochInclusionToggle.css';

export default function EpochInclusionToggle({epoch,label,onToggle,disabled=false,className=''}){
  const included=epoch.curation?.included!==false;
  return <button className={`epoch-inclusion-toggle ${className}`} disabled={disabled} aria-label={`Include ${label} in protocol exports`} aria-pressed={included} title={included?'Included in protocol exports. Click to exclude; recording stays visible.':'Excluded from protocol exports. Click to include; recording stays visible.'} onClick={()=>onToggle(epoch,!included)}>{included?<Check size={13}/>:<X size={13}/>}</button>;
}
