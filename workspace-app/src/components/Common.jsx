import CellTypeIcon from './CellTypeIcon.jsx';
import {cellTypeColor,recordingRigLabel} from "../cell-qc/cellTypes.js";
import {useMemo,useState} from 'react';
import {groupedCellPage} from '../tree-browser/boundedTree.js';
import "../cell-qc/ui/CellList.css";
import MetadataTable from '../epoch-browser/ui/MetadataTable.jsx';
import {recordingDate,datedCellLabel} from '../recording-import/recordingIdentity.js';
import { AlertTriangle, LoaderCircle, ArrowRight, ChevronDown, CheckCircle2, Circle } from 'lucide-react';
import { number, duration } from '../api.js';
export function Status({loading, error, children, retry, data}) {
  if (loading && !data) return <div className="status" role="status"><LoaderCircle className="spin" size={22} aria-hidden="true"/> Loading data…</div>;
  if (error) return <div className="error" role="alert"><AlertTriangle size={20}/><div><strong>Could not load data</strong><p>{error}</p>{retry && <button onClick={retry}>Try again</button>}</div></div>;
  return children;
}
export function Empty({title, children}) {return <div className="empty"><Circle size={24}/><h3>{title}</h3><p>{children}</p></div>;}
export function Badge({kind='neutral', children}) {return <span className={`badge ${kind}`}>{children}</span>;}
export function SourceEligibilityNotice({eligibility,onStores}) {
  if (!eligibility?.propagation_required) return null;
  return <div className="source-eligibility-notice" role="status"><AlertTriangle size={17}/><span><strong>{number(eligibility.excluded_epoch_count)} working-set epochs belong to sources excluded from queries.</strong><small>Propagate source changes before a new export. Past exports remain unchanged.</small></span>{onStores&&<button onClick={onStores}>Data stores <ArrowRight size={14}/></button>}</div>;
}
export function Stats({items}) {return <div className="stats">{items.map(({label,value,detail,icon: Icon}) => <div key={label} className="stat"><div className="stat-label">{Icon && <Icon size={15}/>} {label}</div><strong>{value}</strong>{detail && <small>{detail}</small>}</div>)}</div>;}
export function Metadata(props) {return <MetadataTable {...props}/>;}

export function CellList({cells = [], onInspect,onQC}) {
  const [offset,setOffset]=useState(0);
  const page=useMemo(()=>groupedCellPage(cells,offset),[cells,offset]);
  return <div className="cell-list">{page.total>60&&<nav className="cell-list-pagination" aria-label="Cell list pages"><span>{number(page.offset+1)}–{number(page.end)} of {number(page.total)} cells</span><button disabled={!page.hasPrevious} onClick={()=>setOffset(page.offset-60)}>Previous cells</button><button disabled={!page.hasNext} onClick={()=>setOffset(page.offset+60)}>Next cells</button></nav>}{page.groups.map(({type,cells:group,total}) => <section key={type}>
    <div className="group-heading"><span className="type-dot" style={{background:cellTypeColor(type)}}/><strong>{type}</strong><span>{group.length===total?`${number(total)} cells`:`${number(group.length)} of ${number(total)} cells on this page`}</span></div>
    <div className="cell-columns"><span>Cell</span><span>Recording date</span><span>Rig</span><span>Epochs</span><span>Recorded time</span><span title="Unique epochs appearing in saved exports; inclusion and review are independent.">Exported epochs</span><span/></div>
    {group.map(cell => {
      const total=cell.epoch_count ?? cell.epochs;
      const exported=cell.exported;
      const count=value=>Number.isFinite(value)&&value>=0?number(value):'Unavailable';
      const excluded=Number.isFinite(total)&&Number.isFinite(cell.included)?Math.max(0,total-cell.included):null;
      const uuid=cell.cell_uuid || cell.uuid;
      const date=recordingDate(cell),rig=recordingRigLabel(cell);
      const rawLabel=cell.cell_label || cell.label || 'Cell label not recorded';
      const label=rawLabel.startsWith(`${date} · `)?rawLabel.slice(date.length+3):rawLabel;
      return <div className="cell-row" data-has-qc={onQC?true:undefined} key={uuid}>
        <details className="cell-disclosure">
          <summary><div className="cell-identity"><span className="cell-glyph" style={{color:cellTypeColor(type)}}><CellTypeIcon type={type} size={24}/></span><span className="cell-recording-identity"><strong>{label}{cell.identity_qualifier&&<small> · {cell.identity_qualifier}</small>}</strong></span><ChevronDown className="cell-expand-cue" size={15} aria-hidden="true"/></div>
            <span className="cell-value cell-date"><small>Recording date</small>{date}</span><span className="cell-value cell-rig"><small>Rig</small>{rig}</span>
            <span className="cell-value"><small>Epochs</small>{count(total)}</span><span className="cell-value"><small>Recorded time</small>{duration(cell.duration_seconds)}</span>
            <span className="cell-value"><small>Exported epochs</small><Badge kind={exported>0?'info':'neutral'}>{Number.isFinite(exported)?exported>0?number(exported):'None':'Unavailable'}</Badge></span>
            <span className="expand-hint">Details <ChevronDown size={14} aria-hidden="true"/></span>
          </summary>
          <div className="cell-details">
            <table className="cell-detail-table" aria-label="Recorded cell details">
              <thead><tr><th scope="col">Recorded type</th><th scope="col">Included epochs</th><th scope="col">Excluded epochs</th><th scope="col">Cell UUID</th><th scope="col" className="cell-tags-heading">Cell tags</th></tr></thead>
              <tbody><tr><td>{type}</td><td>{count(cell.included)}</td><td>{count(excluded)}</td><td className="mono">{uuid}</td><td className="cell-detail-tags">
                  {Array.isArray(cell.tags)&&cell.tags.length>0&&<div className="tags" aria-label="Cell tags">{cell.tags.map(tag=><Badge key={tag}>{tag}</Badge>)}</div>}
                  {cell.annotations?.cell_tags?.length>0&&<div className="tags" aria-label="Shared cell tags"><span className="cell-tag-label">Shared</span>{cell.annotations.cell_tags.map(chip=><span key={`${chip.profile_uuid}:${chip.tag}`} title={`${chip.tag} · cell tag · ${chip.author_name||'author not recorded'}`}><Badge>{chip.tag}</Badge></span>)}</div>}
                </td></tr></tbody>
            </table>
            {onInspect&&<button className="primary" onClick={()=>onInspect(uuid)}>Inspect & tag epochs <ArrowRight size={16}/></button>}
          </div>
        </details>
        {onQC&&<button className="cell-qc-action" aria-label={`Open QC for ${datedCellLabel(cell,true)} · Rig ${rig}`} onClick={()=>onQC(uuid)}>Cell QC <ArrowRight size={15}/></button>}
      </div>;
    })}
  </section>)}</div>;
}
