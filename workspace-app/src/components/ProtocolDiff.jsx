import NeuronIcon from './NeuronIcon.jsx';
import {useState} from 'react';
import {ArrowRight,ChevronDown,Clock3,Layers3,RefreshCw,Activity} from 'lucide-react';
import {duration,number} from '../api.js';
import './ProtocolDiff.css';
import {datedCellLabel} from '../recordingIdentity.js';

const length=value=>Array.isArray(value)?value.length:value??0;
const signed=value=>value>0?`+${number(value)}`:value<0?`−${number(Math.abs(value))}`:'No change';
function Metric({icon:Icon,label,previous,next,delta,hint}){
  return <div className="protocol-diff-metric"><span title={hint}><Icon size={14}/>{label}</span><div><span>{previous==null?'—':number(previous)}</span><ArrowRight size={14}/><strong>{next==null?'—':number(next)}</strong><small className={delta>0?'diff-add':delta<0?'diff-remove':'diff-neutral'}>{delta==null?'—':signed(delta)}</small></div></div>;
}
export function CompactProtocolDiff({comparison,showProtocolCount=true}){
  const summary=comparison.diff_summary;
  const current=summary?.current || {epochs:comparison.previous_count};
  const proposed=summary?.proposed || {epochs:comparison.next_count};
  const delta=summary?.delta || {epochs:proposed.epochs-current.epochs};
  return <div className="protocol-diff-compact" aria-label="Current to proposed dataset counts">{[['cells','Cells'],['epochs','Epochs'],['acquisition_protocols','Recorded protocols']].map(([key,label])=><span key={key}><span>{label}</span><strong>{current[key]==null?'—':number(current[key])} → {proposed[key]==null?'—':number(proposed[key])}</strong>{delta[key]!=null&&delta[key]!==0&&<small className={delta[key]>0?'diff-add':'diff-remove'}>{signed(delta[key])}</small>}</span>)}</div>;
}
export default function ProtocolDiff({comparison,showProtocolCount=true,detailsOnly=false}){
  const [limit,setLimit]=useState(20);
  const summary=comparison.diff_summary;
  const current=summary?.current || {epochs:comparison.previous_count};
  const proposed=summary?.proposed || {epochs:comparison.next_count};
  const delta=summary?.delta || {epochs:proposed.epochs-current.epochs};
  const diff=comparison.diff_counts || comparison.diff || {};
  const added=length(diff.added),removed=length(diff.removed),changed=length(diff.changed);
  const retained=Math.max(0,(current.epochs || 0)-removed);
  const scale=Math.max(current.epochs || 0,proposed.epochs || 0,1);
  const cellChanges=summary?.cell_changes || {};
  const rows=['added','removed','updated'].flatMap(kind=>(Array.isArray(cellChanges[kind])?cellChanges[kind]:[]).map(cell=>({...cell,change:kind})));
  const totals=cellChanges.counts || {};
  const cellChangeCount=['added','removed','updated'].reduce((sum,key)=>sum+(totals[key]??cellChanges[key]?.length??0),0);
  const CellContainer=detailsOnly?'section':'details';
  const CellHeading=detailsOnly?'h4':'summary';
  return <div className="protocol-diff">
    {!detailsOnly&&<>
    <div className="protocol-diff-legend"><span>Current <ArrowRight size={12}/> Proposed</span><span>Saved candidate</span></div>
    <div className="protocol-diff-metrics"><Metric icon={NeuronIcon} label="Cells" previous={current.cells} next={proposed.cells} delta={delta.cells}/><Metric icon={Activity} label="Epochs" previous={current.epochs} next={proposed.epochs} delta={delta.epochs}/>{showProtocolCount&&<Metric icon={Layers3} label="Recorded protocols" hint="Unique acquisition protocol names in the dataset; saved protocol workspaces are not counted here." previous={current.acquisition_protocols} next={proposed.acquisition_protocols} delta={delta.acquisition_protocols}/>}</div>
    <div className="protocol-diff-distribution"><div className="protocol-diff-bars" role="img" aria-label={`Current: ${number(current.epochs)} epochs, ${number(removed)} to remove. Proposed: ${number(proposed.epochs)} epochs, ${number(added)} to add. ${number(retained)} retained.`}>
      <div><span>Current</span><div className="protocol-diff-track"><i className="retained" style={{width:`${retained/scale*100}%`}}/><i className="removed" style={{width:`${removed/scale*100}%`}}/></div><small>{number(current.epochs)}</small></div>
      <div><span>Proposed</span><div className="protocol-diff-track"><i className="retained" style={{width:`${Math.max(0,(proposed.epochs || 0)-added)/scale*100}%`}}/><i className="added" style={{width:`${added/scale*100}%`}}/></div><small>{number(proposed.epochs)}</small></div>
    </div><div className="protocol-diff-chips"><span><i className="retained"/>{number(retained)} retained</span><span><i className="added"/>+{number(added)} added</span><span><i className="removed"/>−{number(removed)} removed</span>{changed>0&&<span><RefreshCw size={11}/>{number(changed)} metadata changed</span>}</div></div>
    </>}
    {(current.duration_seconds!=null||cellChangeCount>0)&&<div className="protocol-diff-footer">{current.duration_seconds!=null&&<span><Clock3 size={12}/>{duration(current.duration_seconds)} <ArrowRight size={11}/> {duration(proposed.duration_seconds)} recorded duration</span>}
      {cellChangeCount>0&&<CellContainer className="protocol-diff-cells"><CellHeading><ChevronDown size={13}/>{number(cellChangeCount)} affected {cellChangeCount===1?'cell':'cells'}</CellHeading><div className="protocol-diff-cell-list"><div className="protocol-diff-cell-head"><span>Change</span><span>Cell · recording date</span><span>Cell type</span><span>Epochs</span></div>{rows.slice(0,limit).map((cell,index)=><div className="protocol-diff-cell-row" key={`${cell.change}:${cell.cell_uuid || index}`}><span className={`cell-${cell.change}`}>{cell.change==='added'?'+ New to dataset':cell.change==='removed'?'− Removed':'Updated'}</span><span><strong>{datedCellLabel(cell,true)}</strong></span><span>{cell.cell_type || 'Not recorded'}</span><span className="protocol-diff-cell-count" title={`${cell.epochs_added || 0} added, ${cell.epochs_removed || 0} removed, ${cell.epochs_changed || 0} metadata changed`}>{number(cell.previous_epoch_count)} <ArrowRight size={11}/> {number(cell.proposed_epoch_count)}</span></div>)}{rows.length>limit&&<button onClick={()=>setLimit(value=>value+20)}>Show more cells</button>}{cellChangeCount>rows.length&&<p>Showing {number(rows.length)} of {number(cellChangeCount)} affected cells returned in this comparison.</p>}</div></CellContainer>}
    </div>}
  </div>;
}
