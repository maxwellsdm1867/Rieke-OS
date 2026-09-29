import {useMemo,useState} from 'react';
import {groupedCellPage} from '../boundedTree.js';
import './CellList.css';
import MetadataTable from './MetadataTable.jsx';
import {datedCellLabel} from '../recordingIdentity.js';
import { AlertTriangle, LoaderCircle, ArrowRight, CheckCircle2, Circle } from 'lucide-react';
import { number, duration, humanize } from '../api.js';
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
    <div className="group-heading"><span className="type-dot"/><strong>{humanize(type)}</strong><span>{group.length===total?`${number(total)} cells`:`${number(group.length)} of ${number(total)} cells on this page`}</span></div>
    <div className="cell-columns"><span>Cell / recording date</span><span>Epochs</span><span>Recorded time</span><span>Saved exports</span><span/></div>
    {group.map(cell => {
      const total=cell.epoch_count ?? cell.epochs;
      const exported=cell.exported ?? 0;
      return <details className="cell-row" key={cell.cell_uuid || cell.uuid}>
        <summary><div className="cell-identity"><span className="cell-glyph">{(cell.cell_label || cell.label || 'C').replace('Cell','')}</span><span><strong>{datedCellLabel(cell,true)}</strong></span></div>
          <span>{number(total)}</span><span>{duration(cell.duration_seconds)}</span>
          <Badge kind={exported>0?'info':'neutral'}>{exported>0?`${number(exported)} epochs exported`:'No saved export'}</Badge>
          <span className="expand-hint">Details</span>
        </summary>
        <div className="cell-details"><div><strong>{humanize(type)}</strong><p className="mono">{cell.cell_uuid || cell.uuid}</p>
          <p>{Number.isFinite(cell.included)?`${number(cell.included)} included · ${number(Math.max(0,total-cell.included))} excluded · `:''}{number(exported)} of {number(total)} epochs in saved exports.</p>
          {Array.isArray(cell.tags)&&cell.tags.length>0&&<div className="tags" style={{marginTop:8}}>{cell.tags.map(tag=><Badge key={tag}>{tag}</Badge>)}</div>}
          {cell.annotations?.cell_tags?.length>0&&<div className="tags" aria-label="Shared cell tags">{cell.annotations.cell_tags.map(chip=><Badge key={`${chip.profile_uuid}:${chip.tag}`}>{chip.tag} · {chip.author_name} · cell</Badge>)}</div>}
          <p>Recording identity is shared across this project’s protocols. Review is optional.</p>
        </div>{onQC&&<button onClick={()=>onQC(cell.cell_uuid || cell.uuid)}>Cell QC <ArrowRight size={15}/></button>}{onInspect && <button className="primary" onClick={() => onInspect(cell.cell_uuid || cell.uuid)}>Inspect & tag epochs <ArrowRight size={16}/></button>}</div>
      </details>;
    })}
  </section>)}</div>;
}
