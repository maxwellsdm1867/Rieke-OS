import {useOverviewCells} from '../useOverviewCells.js';
import CellsWindow from '../../epoch-browser/ui/CellsWindow.jsx';
import CellListSection from "../../cell-qc/ui/CellListSection.jsx";
import CellsIcon from "../../components/CellsIcon.jsx";
import CellTypeSummary from "../../cell-qc/ui/CellTypeSummary.jsx";
import {recordedCellType} from "../../cell-qc/cellTypes.js";
import RecordingSize from "../../components/RecordingSize.jsx";
import {aggregateCellTypes,isTypingProtocol,recordingDateLabel as recordingDate,validCellCount,validRecordedDuration} from '../protocolOverviewModel.js';
import { useMemo, useRef, useState } from 'react';
import { Activity, ArrowRight, ArrowUpRight, CalendarDays, Check, Clock3, Database, Download, FileStack, Image, Info, Layers, Link2, Plus, Search, X } from 'lucide-react';
import { duration, humanize, number, time } from "../../api.js";
import { Badge, Metadata } from "../../components/Common.jsx";
import { overviewModel } from './overviewModel.js';
import './Overview.css';

const countLabel=value=>validCellCount(value)?number(value):'Unavailable';
const durationLabel=(value,status)=>status==='pending'?'Preparing…':validRecordedDuration(value)?duration(value):'Unavailable';
const colors=Array.from({length:6},(_,index)=>`var(--chart-${index+1})`);
export default function Overview({data,overviewCache,revision=0,onProtocol,onImport,onExplore,projectName,onQC,presentationOnly=false}){
  const cellList=useOverviewCells(data,'/overview',revision,{enabled:!presentationOnly});
  const sourceCells=useMemo(()=>aggregateCellTypes(cellList.cells).flatMap(type=>type.cells),[cellList.cells]);
  const model=useMemo(()=>overviewModel({...data,cells:sourceCells}),[data,sourceCells]);
  const completeCellSummary=!cellList.partial&&Array.isArray(cellList.cells)&&cellList.cells.every(cell=>cell?.cell_uuid||cell?.uuid);
  const [dateScope,setDateScope]=useState(null),[typeScope,setTypeScope]=useState(null);
  const cellsPanel=useRef(null),cellsToggle=useRef(null);
  const [cellsOpen,setCellsOpen]=useState(false);
  const [cellsReveal,setCellsReveal]=useState(0);
  function revealCells(){setCellsOpen(true);setCellsReveal(value=>value+1);requestAnimationFrame(()=>{cellsToggle.current?.focus({preventScroll:true});cellsPanel.current?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});});}
  const counts=data.counts||{},protocols=data.protocols||[],sources=data.sources||[];
  const maxDateCells=Math.max(1,...model.dates.map(date=>date.cells));
  const cells=sourceCells.filter(cell=>(!dateScope||(cell.date||'Not recorded')===dateScope)&&(!typeScope||recordedCellType(cell)===typeScope));
  const experiments=protocols.filter(protocol=>!isTypingProtocol(protocol)),typing=protocols.filter(isTypingProtocol);
  const experimentalIds=new Set(experiments.map(protocol=>protocol.protocol_uuid));
  const experimentalCells=sourceCells.filter(cell=>(cell.protocol_uuids||[]).some(id=>experimentalIds.has(id))).length;
  const stats=[{label:'Cells',value:Number.isSafeInteger(data.cells_total)?data.cells_total:completeCellSummary?model.totalCells:null,icon:CellsIcon,note:`${number(experimentalCells)}${cellList.partial?' loaded cells':''} in experimental datasets`},{label:'Recording dates',value:completeCellSummary?model.dateCount:null,icon:CalendarDays,note:model.unknownDateCells?`${model.unknownDateCells} cells missing a date`:null},{label:'Recorded epochs',value:counts.epochs,icon:Activity}];
  const visibleEvents=(data.events||[]).slice(0,5);
  return <div className="page infographic-overview" inert={presentationOnly?true:undefined} aria-busy={presentationOnly||undefined}>
    <header className="page-heading"><div><div className="eyebrow">PROJECT OVERVIEW</div><h1>{projectName || data.project?.display_name || data.project?.name || 'Project'}</h1><p>Your experiment, from recorded cells to analysis datasets.</p></div><div className="overview-discovery-actions"><button className="primary" onClick={onExplore}><Search size={16}/> Search predicate</button><button onClick={onImport}><Plus size={16}/> Add data store</button></div></header>
    <section className="ov-infographic" aria-label="Project infographic">
      <div className="ov-metric-ribbon">{stats.map(({label,value,icon:Icon,note})=><div key={label}><span><Icon size={16}/>{label}</span><strong>{countLabel(value)}</strong>{note&&<small>{note}</small>}</div>)}<div><span><Database size={16}/> Source recording size</span>{presentationOnly?<span className="ov-subtle">Checking…</span>:<RecordingSize overviewCache={overviewCache} revision={revision} sourceIds={sources.map(source=>source.source_sha256)}/>}<small>All registered sources · includes archived</small></div></div>
      <div className="ov-acquisition-grid"><section className="ov-types">{cellList.partial&&<p className="ov-subtle">Types and dates summarize loaded cells.</p>}{!completeCellSummary&&!cellList.partial&&<p className="ov-subtle">Cell summary coverage unavailable; only identified cells are shown.</p>}<CellTypeSummary types={model.types} total={model.totalCells} label={cellList.partial?"Loaded source cells":"Source cells"} selected={typeScope} onSelect={value=>{setTypeScope(value);revealCells();}}/></section><section className="ov-dates"><div className="ov-section-title"><h2><CalendarDays size={16}/> Recording dates</h2><Info size={14} aria-label="Dates come from cell recording metadata, not import timestamps."/></div>
        <div className="ov-date-list">{model.dates.map(date=><button key={date.date} className={dateScope===date.date?'selected':''} aria-pressed={dateScope===date.date} title={`Show cells recorded ${recordingDate(date.date)}`} onClick={()=>{setDateScope(dateScope===date.date?null:date.date);revealCells();}}><span className="ov-date-dot"/><span className="ov-date-identity"><strong>{recordingDate(date.date)}</strong><small>{countLabel(date.epochs)} epochs · {durationLabel(date.duration,date.duration_status)}</small></span><span className="ov-date-track"><i style={{width:`${date.cells/maxDateCells*100}%`}}/></span><span className="ov-date-count"><span>{number(date.cells)}</span> <span>{date.cells===1?'cell':'cells'}</span></span></button>)}{!model.dates.length&&<div className="ov-empty"><CalendarDays size={24}/><span>Your first recording date appears after import.</span><button onClick={onImport}>Add data store <Plus size={13}/></button></div>}</div>
      </section></div>
      <div className="ov-inventory" aria-label="Data inventory"><div><Database size={17}/><span><strong>{number(sources.length)}</strong> {sources.length===1?'source store':'source stores'}</span></div><ArrowRight size={14}/><div><Layers size={17}/><span><strong>{number(protocols.length)}</strong> saved selections</span></div><ArrowRight size={14}/><div><Download size={17}/><span><strong>{countLabel(counts.exported)}</strong> unique epochs exported</span></div><span className="ov-recorded-time"><Clock3 size={14}/>{durationLabel(counts.duration_seconds,counts.duration_status)} recorded</span></div>
    </section>
    <CellListSection footer={cellList.window&&<CellsWindow {...cellList.window}/>} cells={cells} title="Source cells in overview" open={cellsOpen} onOpenChange={setCellsOpen} toggleRef={cellsToggle} panelRef={cellsPanel} onQC={onQC} byType revealKey={cellsReveal} filters={<div className="ov-cell-filters">{dateScope&&<Badge><CalendarDays size={12}/>{recordingDate(dateScope)}</Badge>}{typeScope&&<Badge>{typeScope}</Badge>}{(dateScope||typeScope)&&<button className="quiet" onClick={()=>{setDateScope(null);setTypeScope(null);}}><X size={13}/> Clear</button>}</div>}/>
    <ProtocolVolumes protocols={experiments} title="Experimental protocols" onProtocol={onProtocol}/>
    <details className="ov-qc-protocols"><summary><Activity size={15}/> QC & typing <span>{typing.length} recording types</span></summary><p>Expanding spots, single spots and split-field centering support cell typing and quality checks.</p><ProtocolVolumes protocols={typing} title="QC & typing recordings" onProtocol={onProtocol}/></details>
    <section className="ov-figures" aria-label="Future linked figures"><span className="ov-figure-icon"><Image size={25}/><Link2 size={12}/></span><div><h2>Linked figures</h2><p>A place for figures connected to protocol datasets and their source cells.</p></div><Badge>Planned</Badge></section>

    <div className="ov-bottom-grid"><section className="section ov-source-register"><div className="section-heading"><h2><FileStack size={16}/> Source register</h2><span className="ov-subtle" title="The catalog records an import timestamp when available, otherwise the parser validation timestamp. Exact actions are in Activity & logs.">Catalog timestamps <Info size={12}/></span></div>{sources.map(source=><div className="ov-source-row" key={source.source_sha256}><span className="ov-source-icon"><Database size={16}/></span><span><strong>{source.filename}</strong><small>{source.imported_at?time(source.imported_at):'Import time not recorded'}</small></span><span title="Source metadata validated"><Check size={14}/></span></div>)}<div className="ov-activity-heading"><h3><Clock3 size={14}/> Recent activity</h3></div>{visibleEvents.map((event,index)=><div className="ov-activity-row" key={event.event_uuid||index}><i/><span>{humanize(event.action||event.status||'Recorded event').replace(/_/g,' ')}</span><time>{time(event.occurred_at||event.at)}</time></div>)}{!visibleEvents.length&&<p className="ov-empty">Actions will appear here as you work.</p>}</section>
      <Metadata title="Project metadata" data={{project_uuid:data.project?.project_uuid,main_database:data.catalog?.database || 'schema',adapter:data.catalog?.adapter || 'DataJoint',source_files:sources.length,...data.project}}/>
    </div>
  </div>;
}

function ProtocolVolumes({protocols,title,onProtocol}){return <section className="ov-protocols section"><div className="section-heading"><h2><Layers size={16}/> {title}</h2><span className="ov-subtle" title="These are saved selections over the main database. One epoch may belong to several selections."><Info size={13}/> Selections may overlap</span></div>
      <div className="ov-protocol-head"><span>Dataset</span><span className="ov-protocol-number">Cells</span><span className="ov-protocol-number">Epochs</span><span className="ov-protocol-number">Recorded time</span><span/></div>
      {protocols.map((protocol,index)=>{const n=protocol.counts?.epochs ?? protocol.epoch_count ?? 0;const percent=n/Math.max(1,...protocols.map(item=>item.counts?.epochs??item.epoch_count??0))*100;return <button className="ov-protocol-row" key={protocol.protocol_uuid} onClick={()=>onProtocol(protocol.protocol_uuid)}><span className="ov-protocol-identity"><i style={{background:colors[index%colors.length]}}/><span><strong>{humanize(protocol.name)}</strong><small>{protocol.binding?`Working dataset · v${protocol.binding.version}`:'Saved source query'}</small></span></span><span className="ov-protocol-number">{number(protocol.counts?.cells??protocol.cell_count)}</span><span className="ov-coverage"><span><strong>{number(n)}</strong></span><span className="ov-coverage-track"><i style={{width:`${Math.min(100,Math.max(0,percent))}%`,background:colors[index%colors.length]}}/></span></span><span className="ov-protocol-duration">{durationLabel(protocol.counts?.duration_seconds,protocol.counts?.duration_status)}</span><ArrowUpRight size={15}/></button>;})}
      {!protocols.length&&<div className="ov-empty">Protocol selections will appear here.</div>}
    </section>;}
