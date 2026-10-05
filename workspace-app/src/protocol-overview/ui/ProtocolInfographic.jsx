import {Activity,ArrowRight,CalendarDays,Clock3,Database,Inbox} from 'lucide-react';
import {duration,number} from "../../api.js";
import {aggregateCellTypes,isTypingProtocol,validCellCount,validRecordedDuration} from '../protocolOverviewModel.js';
import {overviewModel} from './overviewModel.js';
import NeuronIcon from "../../components/NeuronIcon.jsx";
import CellTypeAccordions from "../../cell-qc/ui/CellTypeAccordions.jsx";
import RecordingSize from "../../components/RecordingSize.jsx";
import ProtocolTagSummary from "../../annotations/ui/ProtocolTagSummary.jsx";
import './ProtocolInfographic.css';

const countLabel=value=>validCellCount(value)?number(value):'Unavailable';
const durationLabel=value=>validRecordedDuration(value)?duration(value):'Unavailable';

export default function ProtocolInfographic({data,revision,onFilter,onInspect,onQC,pendingReviewCells=null,onWorkbench}){
  const counts=data.counts||{},hasCellSummary=Array.isArray(data.cells),omitted=hasCellSummary?data.cells.filter(cell=>!(cell?.cell_uuid||cell?.uuid)).length:0,completeCellSummary=hasCellSummary&&!omitted,types=aggregateCellTypes(data.cells),cells=types.flatMap(type=>type.cells),model=overviewModel({cells}),total=completeCellSummary?cells.length:null;
  // The caller supplies the unfiltered protocol DTO. Retain a truthful fallback
  // if this component is ever used with an explicitly filtered or unbound DTO.
  const filtered=Object.keys(data.filters||{}).length>0;
  const frozen=!!data.binding?.revision_uuid&&!filtered;
  const scope=filtered?'Browsing selection':frozen?'Main · frozen protocol cohort':'Source query · unbound protocol';
  return <section className="protocol-infographic" aria-label="Protocol dataset infographic">
    <header><span>{scope}</span><small>{isTypingProtocol(data)?'QC & typing recordings':'Recordings in this protocol'}</small></header>
    <div className="pi-cohort-intro"><p>{frozen?'Cells in the main frozen cohort':filtered?'Cells matching the browsing filters':'Cells matching the unbound source query'}</p><small>Expand a recorded type to inspect its cells. {frozen?'Membership is frozen; inclusion and review marks remain independent.':filtered?'This selection is filtered.':'Membership follows the source query until a cohort is frozen.'}</small></div>
    {!completeCellSummary&&<p className="pi-cell-coverage" role="status">{hasCellSummary?`${number(omitted)} cell summary ${omitted===1?'row lacks':'rows lack'} a UUID and ${omitted===1?'is':'are'} omitted. Available identities are shown; complete membership counts are unavailable.`:'Cell summaries are unavailable; complete membership counts cannot be determined.'}</p>}{hasCellSummary&&<CellTypeAccordions cells={data.cells} onInspect={onInspect} onQC={onQC} showInclusion/>}
    <div className="pi-cohort-summary"><div className="pi-metrics">
      <div><span><NeuronIcon size={16}/> Total cells</span><strong>{countLabel(total)}</strong><small>Each cell UUID counted once</small></div>
      <div><span><CalendarDays size={16}/> Recording dates</span><strong>{countLabel(completeCellSummary?model.dateCount:null)}</strong><small>{model.unknownDateCells?`${number(model.unknownDateCells)} cells missing a date`:'From recording metadata'}</small></div>
      <div><span><Activity size={16}/> Epochs</span><strong>{countLabel(counts.epochs)}</strong><small>{countLabel(counts.included)} included · {countLabel(counts.excluded)} excluded</small></div>
      <div><span><Clock3 size={16}/> Recorded time</span><strong>{durationLabel(counts.duration_seconds)}</strong><small>Sum of epoch durations</small></div>
    </div>
    {pendingReviewCells!==0&&<section className="pi-pending-review" aria-label="Needs review"><div><Inbox size={19}/><h3>Needs review</h3></div><strong>{countLabel(pendingReviewCells)}</strong><p>Pending candidate cells, separate from main membership.</p>{onWorkbench&&<button onClick={onWorkbench}>Review incoming cells <ArrowRight size={14}/></button>}</section>}</div>
    <div className="pi-context-grid">
      <section className="pi-dates" aria-label="Recording dates"><h3><CalendarDays size={14}/> Recording dates</h3><div className="pi-date-list">{model.dates.slice(0,8).map(date=><div key={date.date}><span>{date.date}</span><strong>{number(date.cells)} cells</strong><small>{countLabel(date.epochs)} epochs</small></div>)}</div>{model.dates.length>8&&<small>{number(model.dates.length-8)} more dates</small>}{!model.dates.length&&<p>{completeCellSummary?'No recording dates in this scope.':'Recording date coverage unavailable.'}</p>}<div className="pi-source-size"><span><Database size={14}/> Linked source size</span><RecordingSize sourceIds={data.source_sha256s} revision={revision}/><small>Whole H5 files · shared across protocols</small></div></section>
      <div className="pi-review-context"><section className="pi-export-history" aria-label="Saved export history"><strong>Saved export history</strong><p>Current cohort epochs appearing in saved exports, counted once. Inclusion and review marks above describe the current cohort.</p></section></div>
    </div>
    <ProtocolTagSummary protocol={{...data,cells}} onFilter={onFilter}/>
  </section>;
}
