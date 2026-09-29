import {Activity,CalendarDays,Clock3,Database,Shapes,Users} from 'lucide-react';
import {duration,number,humanize} from '../api.js';
import {datedCellLabel} from '../recordingIdentity.js';
import {isTypingProtocol,protocolCellSummary} from '../protocolOverviewModel.js';
import {overviewModel} from './overviewModel.js';
import RecordingSize from './RecordingSize.jsx';
import './ProtocolInfographic.css';
import ProtocolTagSummary from './ProtocolTagSummary.jsx';
export default function ProtocolInfographic({data,revision,onFilter}){
  const counts=data.counts||{},model=overviewModel(data),cells=[...(data.cells||[])].sort((a,b)=>(b.epochs||0)-(a.epochs||0)),max=Math.max(1,...cells.map(cell=>cell.epochs||0)),{types,matchingCells:total,cellTypes,unclassifiedCells}=protocolCellSummary(data.cells);
  return <section className="protocol-infographic" aria-label="Protocol dataset infographic"><header><span>{isTypingProtocol(data)?'QC & typing recordings':'Experimental dataset'}</span><small>Current query and filters</small></header>
    <div className="pi-cell-headline" aria-label="Matching cells and cell types">
      <div><span><Users size={18}/> Matching cells</span><strong>{number(total)}</strong><small>Unique cells in this protocol</small></div>
      <div><span><Shapes size={18}/> Cell types</span><strong>{number(cellTypes)}</strong><small>{unclassifiedCells?`${number(unclassifiedCells)} ${unclassifiedCells===1?'cell has':'cells have'} no recorded type`:'Distinct recorded types'}</small></div>
    </div>
    <div className="pi-type-summary">
      <div className="pi-type-heading"><h3><Users size={17}/> Cells by type</h3><span>Each cell counted once</span></div>
      <div className="pi-type-columns"><span>Cell type</span><span>Cells in this dataset</span><span>With saved exports</span></div>
      <div className="pi-type-list">{types.map(({type,count,withExports})=><div className="pi-type-row" key={type}>
        <strong title={type}>{humanize(type)}</strong>
        <div className="pi-type-count"><div className="pi-track"><i style={{width:`${100*count/Math.max(1,total)}%`}}/></div><strong>{number(count)} <small>{count===1?'cell':'cells'}</small></strong></div>
        <span>{number(withExports)} / {number(count)}</span>
      </div>)}</div>
      {!types.length?<p>No cells match these filters.</p>:<small>Unique cells in the current query · “With saved exports” counts cells with at least one exported epoch.</small>}
    </div>
    <div className="pi-metrics"><div><span><CalendarDays size={16}/> Recording dates</span><strong>{number(model.dateCount)}</strong><small>Across matching cells</small></div><div><span><Activity size={16}/> Epochs</span><strong>{number(counts.epochs)}</strong><small>{number(counts.included)} included · {number(counts.excluded)} excluded</small></div><div><span><Clock3 size={16}/> Recorded time</span><strong>{duration(counts.duration_seconds)}</strong><small>Sum of epoch durations</small></div><div><span><Database size={16}/> Linked source size</span><RecordingSize sourceIds={data.source_sha256s} revision={revision}/><small className="pi-size-note">Whole H5 files · shared across protocols</small></div></div>
    <div className="pi-distribution"><details className="pi-epoch-details"><summary>Epochs by cell</summary>{cells.slice(0,8).map(cell=><div className="pi-cell-row" key={cell.cell_uuid}><span title={cell.cell_uuid}>{datedCellLabel(cell,true)}</span><div className="pi-track"><i style={{width:`${100*(cell.epochs||0)/max}%`}}/></div><strong>{number(cell.epochs)}</strong><small>{duration(cell.duration_seconds)}</small></div>)}{cells.length>8&&<small>{number(cells.length-8)} more cells in the list below</small>}{!cells.length&&<p>No cells match these filters.</p>}</details><div className="pi-dates"><h3><CalendarDays size={14}/> Recording dates</h3>{model.dates.slice(0,8).map(date=><div key={date.date}><span>{date.date}</span><strong>{number(date.cells)} cells</strong><small>{number(date.epochs)} epochs</small></div>)}{model.dates.length>8&&<small>{number(model.dates.length-8)} more dates</small>}<p>{number(counts.exported)} epochs in saved exports</p></div></div>
    <ProtocolTagSummary protocol={data} onFilter={onFilter}/>
  </section>;
}
