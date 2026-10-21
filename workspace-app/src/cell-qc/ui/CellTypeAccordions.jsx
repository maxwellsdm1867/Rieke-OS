import {useSemanticReset} from '../../useSemanticReset.js';
import {useId,useMemo,useState} from 'react';
import {ChevronDown} from 'lucide-react';
import {duration,number} from "../../api.js";
import {aggregateCellTypes,countNoun} from "../../protocol-overview/protocolOverviewModel.js";
import {CellList} from "../../components/Common.jsx";
import {CellTypeIdentity} from './CellTypeSummary.jsx';
import './CellTypeAccordions.css';

const countLabel=value=>value===null?'Unavailable':number(value);

// One muted line of per-type quantities for the summary variant; each value keeps
// the same unavailable rule as the default metric grid.
function summaryDetail(group,showInclusion){
  const parts=[countNoun(group.epochs,'epoch'),group.duration_status==='failed'?'Duration preparation failed':group.duration_status==='pending'?'Preparing duration…':group.duration_seconds===null?'Unavailable duration':duration(group.duration_seconds),`${countLabel(group.exported)} exported`];
  if(showInclusion)parts.push(`${countLabel(group.included)} included`,`${countLabel(group.reviewed)} reviewed`);
  return parts.map((part,index)=><span key={index}>{index?' · ':''}<span className="cell-type-summary-part">{part}</span></span>);
}

function CellTypeGroup({group,total,onInspect,onQC,showInclusion,revealKey,summary}){
  const id=useId(),[open,setOpen]=useState(false);
  // A project date/type filter reveals its matching groups. Keep their CellList
  // mounted when collapsed so native details and pagination retain their state.
  useSemanticReset(revealKey,()=>{if(revealKey)setOpen(true);});
  const cellsPanel=<div id={id} className="cell-type-cells" hidden={!open}><CellList cells={group.cells} onInspect={onInspect} onQC={onQC}/></div>;
  // Summary rows share the project overview's type identity: icon, count, name and
  // proportion bar, with quantities on one secondary line and no resting fill.
  if(summary)return <section className="cell-type-group" aria-label={`${group.type} cells`}>
    <button className="cell-type-toggle" aria-expanded={open} aria-controls={id} title={`${open?'Hide':'Show'} ${group.type} cells`} onClick={()=>setOpen(value=>!value)}>
      <CellTypeIdentity type={group.type} count={group.count} total={total}/>
      <span className="cell-type-summary-detail">{summaryDetail(group,showInclusion)}</span>
      <span className="cell-type-disclosure"><span>{open?'Hide':'Show'} cells</span><ChevronDown size={16} aria-hidden="true"/></span>
    </button>
    {cellsPanel}
  </section>;
  return <section className="cell-type-group" aria-label={`${group.type} cells`}>
    <div className="cell-type-group-heading">
      <h3><button className="cell-type-toggle" aria-expanded={open} aria-controls={id} onClick={()=>setOpen(value=>!value)}>
        <CellTypeIdentity type={group.type} count={group.count} total={total}/>
        <span className="cell-type-disclosure"><span>{open?'Hide':'Show'} cells</span><ChevronDown size={17} aria-hidden="true"/></span>
      </button></h3>
      <dl className="cell-type-metrics">
        <div><dt>Epochs</dt><dd>{countLabel(group.epochs)}</dd></div>
        <div><dt>Recorded time</dt><dd>{group.duration_status==='failed'?'Duration preparation failed':group.duration_status==='pending'?'Preparing…':group.duration_seconds===null?'Unavailable':duration(group.duration_seconds)}</dd></div>
        <div><dt title="Unique epochs appearing in saved exports; inclusion and review are independent.">Exported epochs</dt><dd>{countLabel(group.exported)}</dd></div>
      </dl>
      {showInclusion&&<dl className="cell-type-marks"><div><dt>Included epochs</dt><dd>{countLabel(group.included)}</dd></div><div><dt>Marked reviewed</dt><dd>{countLabel(group.reviewed)}</dd></div></dl>}
    </div>
    {cellsPanel}
  </section>;
}

// variant="summary" is the protocol Overview presentation; the default grid is
// unchanged for the project cell list.
export default function CellTypeAccordions({cells,onInspect,onQC,showInclusion=false,revealKey=0,variant}){
  const groups=useMemo(()=>aggregateCellTypes(cells),[cells]),summary=variant==='summary';
  return <div className={summary?'cell-type-accordions cell-type-accordions-summary':'cell-type-accordions'}>{groups.map(group=><CellTypeGroup key={group.type} group={group} total={groups.reduce((sum,row)=>sum+row.count,0)} onInspect={onInspect} onQC={onQC} showInclusion={showInclusion} revealKey={revealKey} summary={summary}/>)}{!groups.length&&<p className="cell-list-empty">No cells in this scope.</p>}</div>;
}
