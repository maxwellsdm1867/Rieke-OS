import {useOverviewCells} from '../useOverviewCells.js';
import CellsWindow from '../../epoch-browser/ui/CellsWindow.jsx';
import {Activity,ArrowRight,CalendarDays,Clock3,Database,Download,Inbox,Info} from 'lucide-react';
import {duration,number} from "../../api.js";
import {aggregateCellTypes,countNoun,groupTotal,recordingDateLabel,validCellCount,validRecordedDuration} from '../protocolOverviewModel.js';
import {overviewModel} from './overviewModel.js';
import CellsIcon from "../../components/CellsIcon.jsx";
import CellTypeAccordions from "../../cell-qc/ui/CellTypeAccordions.jsx";
import RecordingSize from "../../components/RecordingSize.jsx";
import ProtocolTagSummary from "../../annotations/ui/ProtocolTagSummary.jsx";
import './ProtocolInfographic.css';
import {protocolDatasetStatus} from '../protocolDatasetStatus.js';
import ProtocolDatasetStatus from './ProtocolDatasetStatus.jsx';

const countLabel=value=>validCellCount(value)?number(value):'Unavailable';
const durationLabel=(value,status)=>status==='failed'?'Preparation failed':status==='pending'?'Preparing…':validRecordedDuration(value)?duration(value):'Unavailable';

// Visual language follows the project Overview: a hero metric row, cells by type
// beside recording dates, and a footer inventory strip.
export default function ProtocolInfographic({data,revision,overviewCache,onFilter,onInspect,onQC,pendingReviewCells=null,onWorkbench,presentationOnly=false}){
  const cellList=useOverviewCells(data,`/protocols/${data.definition?.protocol_uuid}/overview`,revision,{enabled:!presentationOnly});
  const cellsData=cellList.cells;
  const counts=data.counts||{},hasCellSummary=Array.isArray(cellsData),omitted=hasCellSummary?cellsData.filter(cell=>!(cell?.cell_uuid||cell?.uuid)).length:0,completeCellSummary=hasCellSummary&&!omitted&&!cellList.partial,types=aggregateCellTypes(cellsData),cells=types.flatMap(type=>type.cells),model=overviewModel({cells}),total=Number.isSafeInteger(data.cells_total)?data.cells_total:completeCellSummary?cells.length:null;
  // Epochs partition by cell, so per-type export counts sum without double counting.
  const exported=completeCellSummary?groupTotal(types,'exported'):null;
  const maxDateCells=Math.max(1,...model.dates.map(date=>date.cells));
  return <section className="protocol-infographic" aria-label="Protocol dataset infographic">
    <ProtocolDatasetStatus data={data} pendingReviewCells={pendingReviewCells}/>

    <div className="pi-cohort-summary"><div className="pi-metrics">
      <div><span><CellsIcon size={16}/> Cells</span><strong>{countLabel(total)}</strong><small>Each cell UUID counted once</small></div>
      <div><span><CalendarDays size={16}/> Recording dates</span><strong>{countLabel(completeCellSummary?model.dateCount:null)}</strong><small>{model.unknownDateCells?`${countNoun(model.unknownDateCells,'cell')} missing a date`:'From recording metadata'}</small></div>
      <div><span><Activity size={16}/> Epochs</span><strong>{countLabel(counts.epochs)}</strong><small>{countLabel(counts.included)} included · {countLabel(counts.excluded)} excluded</small></div>
      <div><span><Clock3 size={16}/> Recorded time</span><strong>{durationLabel(counts.duration_seconds,counts.duration_status)}</strong><small>Sum of epoch durations</small></div>
    </div>
    {protocolDatasetStatus(data).state==='saved'&&pendingReviewCells!==0&&<section className="pi-pending-review" aria-label="Needs review"><div><Inbox size={19}/><h3>Needs review</h3></div><strong>{countLabel(pendingReviewCells)}</strong><p>Cells with matching epochs from new recordings. Merge after review to add them to the data shown here.</p>{onWorkbench&&Number.isSafeInteger(pendingReviewCells)&&pendingReviewCells>0&&<button onClick={onWorkbench}>Review incoming cells <ArrowRight size={14}/></button>}</section>}</div>
    {cellList.partial&&<p className="pi-cell-coverage" role="status">Types, dates and export participation summarize loaded cells.</p>}{!completeCellSummary&&!cellList.partial&&<p className="pi-cell-coverage" role="status">{hasCellSummary?`${number(omitted)} cell summary ${omitted===1?'row lacks':'rows lack'} a UUID and ${omitted===1?'is':'are'} omitted. Available identities are shown; complete membership counts are unavailable.`:'Cell summaries are unavailable; complete membership counts cannot be determined.'}</p>}
    <div className="pi-acquisition">
      {hasCellSummary&&<section className="pi-types" aria-label="Cells by type"><div className="pi-section-title"><h3>Cells by type</h3><small>Select a type to list its cells</small></div><CellTypeAccordions cells={cellsData} onInspect={onInspect} onQC={onQC} showInclusion variant="summary"/>{cellList.window&&<CellsWindow {...cellList.window}/>}</section>}
      <section className="pi-dates" aria-label="Recording dates"><div className="pi-section-title"><h3><CalendarDays size={16}/> Recording dates</h3><Info size={14} aria-label="Dates come from cell recording metadata, not import timestamps."/></div>
        <div className="pi-date-list">{model.dates.slice(0,8).map(date=><div key={date.date}><span className="pi-date-dot"/><span className="pi-date-identity"><strong>{recordingDateLabel(date.date)}</strong><small>{countNoun(date.epochs,'epoch')} · {durationLabel(date.duration,date.duration_status)}</small></span><span className="pi-date-track"><i style={{width:`${date.cells/maxDateCells*100}%`}}/></span><span className="pi-date-count">{countNoun(date.cells,'cell')}</span></div>)}</div>
        {model.dates.length>8&&<small className="pi-more-dates">{number(model.dates.length-8)} more dates</small>}{!model.dates.length&&<p>{completeCellSummary?'No recording dates in this scope.':'Recording date coverage unavailable.'}</p>}
      </section>
    </div>
    <div className="pi-inventory" aria-label="Linked data">
      <div className="pi-source-size"><Database size={16}/><span>Linked source size</span><RecordingSize overviewCache={overviewCache} protocolId={data.definition?.protocol_uuid} sourceIds={data.source_sha256s} revision={revision}/><small>· whole files, shared across protocols</small></div>
      <div className="pi-exported" title="Unique cohort epochs appearing in saved exports"><Download size={16}/><span><strong>{countLabel(exported)}</strong> exported epochs</span></div>
      <section className="pi-export-history" aria-label="Saved export history"><details><summary>About saved exports</summary><p>Current cohort epochs appearing in saved exports, counted once. Inclusion and review marks above describe the current cohort.</p></details></section>
    </div>
    <ProtocolTagSummary protocol={{...data,cells}} onFilter={onFilter}/>
  </section>;
}
