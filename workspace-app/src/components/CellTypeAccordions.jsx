import {useEffect,useId,useMemo,useState} from 'react';
import {ChevronDown} from 'lucide-react';
import {duration,number} from '../api.js';
import {aggregateCellTypes} from '../protocolOverviewModel.js';
import {CellList} from './Common.jsx';
import {CellTypeIdentity} from './CellTypeSummary.jsx';
import './CellTypeAccordions.css';

const countLabel=value=>value===null?'Unavailable':number(value);

function CellTypeGroup({group,total,onInspect,onQC,showInclusion,revealKey}){
  const id=useId(),[open,setOpen]=useState(false);
  // A project date/type filter reveals its matching groups. Keep their CellList
  // mounted when collapsed so native details and pagination retain their state.
  useEffect(()=>{if(revealKey)setOpen(true);},[revealKey]);
  return <section className="cell-type-group" aria-label={`${group.type} cells`}>
    <div className="cell-type-group-heading">
      <h3><button className="cell-type-toggle" aria-expanded={open} aria-controls={id} onClick={()=>setOpen(value=>!value)}>
        <CellTypeIdentity type={group.type} count={group.count} total={total}/>
        <span className="cell-type-disclosure"><span>{open?'Hide':'Show'} cells</span><ChevronDown size={17} aria-hidden="true"/></span>
      </button></h3>
      <dl className="cell-type-metrics">
        <div><dt>Epochs</dt><dd>{countLabel(group.epochs)}</dd></div>
        <div><dt>Recorded time</dt><dd>{group.duration_seconds===null?'Unavailable':duration(group.duration_seconds)}</dd></div>
        <div><dt>Saved export history</dt><dd>{countLabel(group.exported)}{group.exported!==null&&<small> epochs</small>}{group.withExports!==null&&<small> · {number(group.withExports)} {group.withExports===1?'cell':'cells'}</small>}</dd></div>
      </dl>
      {showInclusion&&<p className="cell-type-marks">Export marks: <strong>{countLabel(group.included)}</strong> included · <strong>{countLabel(group.reviewed)}</strong> marked reviewed</p>}
    </div>
    <div id={id} className="cell-type-cells" hidden={!open}><CellList cells={group.cells} onInspect={onInspect} onQC={onQC}/></div>
  </section>;
}

export default function CellTypeAccordions({cells,onInspect,onQC,showInclusion=false,revealKey=0}){
  const groups=useMemo(()=>aggregateCellTypes(cells),[cells]);
  return <div className="cell-type-accordions">{groups.map(group=><CellTypeGroup key={group.type} group={group} total={groups.reduce((sum,row)=>sum+row.count,0)} onInspect={onInspect} onQC={onQC} showInclusion={showInclusion} revealKey={revealKey}/>)}{!groups.length&&<p className="cell-list-empty">No cells in this scope.</p>}</div>;
}
