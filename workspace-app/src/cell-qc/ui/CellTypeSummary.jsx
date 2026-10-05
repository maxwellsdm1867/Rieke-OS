import NeuronIcon from "../../components/NeuronIcon.jsx";
import {number} from "../../api.js";
import {cellTypeColor} from '../cellTypes.js';
import './CellTypeSummary.css';

export function CellTypeIdentity({type,count,total}){
  return <><span className="cell-type-neuron" style={{color:cellTypeColor(type)}}><NeuronIcon size={44}/></span><span className="cell-type-identity"><strong className="cell-type-count">{number(count)}</strong><span className="cell-type-name">{type}<small>{count===1?'cell':'cells'}</small></span>{total>0&&<span className="cell-type-comparison" aria-hidden="true"><i style={{width:`${100*count/total}%`,background:cellTypeColor(type)}}/></span>}</span></>;
}

// Input is the distinct authoritative cell summary, never epoch facet counts.
export default function CellTypeSummary({types,total,label='Matching cells',selected,onSelect}){
  return <div className="cell-type-summary" aria-label={`${label} by recorded cell type · ${number(total)} distinct cells`}>
    <h3>{label}</h3>
    <div className="cell-type-legend">{types.map(row=>onSelect?<button key={row.type} aria-pressed={selected===row.type} title="Filter the cell list below" onClick={()=>onSelect(selected===row.type?null:row.type)}><CellTypeIdentity type={row.type} count={row.count} total={total}/></button>:<div className="cell-type-entry" key={row.type}><CellTypeIdentity type={row.type} count={row.count} total={total}/></div>)}</div>
    {!types.length&&<p>No cells in this scope.</p>}<small>Each cell UUID counted once.</small>
  </div>;
}
