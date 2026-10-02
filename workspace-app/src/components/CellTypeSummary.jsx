import NeuronIcon from './NeuronIcon.jsx';
import {number} from '../api.js';
import {cellTypeColor} from '../cellTypes.js';
import './CellTypeSummary.css';

// Input is the distinct authoritative cell summary, never epoch facet counts.
export default function CellTypeSummary({types,total,label='Matching cells',selected,onSelect,showExports=false}) {
  const circumference=2*Math.PI*44;let offset=0;
  return <div className="cell-type-summary" aria-label={`${label} by recorded cell type`}>
    <svg viewBox="0 0 120 120" role="img" aria-label={`${number(total)} ${label.toLowerCase()}: ${types.map(row=>`${row.type}: ${number(row.count)}`).join(', ')}`}>
      <circle cx="60" cy="60" r="44" fill="none" stroke="var(--plot-grid)" strokeWidth="10"/>
      {types.map(row=>{const length=total?row.count/total*circumference:0,start=offset;offset+=length;return <circle key={row.type} cx="60" cy="60" r="44" fill="none" stroke={cellTypeColor(row.type)} strokeWidth="10" strokeDasharray={`${length} ${circumference-length}`} strokeDashoffset={-start} transform="rotate(-90 60 60)"/>;})}
      <text x="60" y="60" textAnchor="middle" className="ov-donut-number">{number(total)}</text><text x="60" y="77" textAnchor="middle" className="ov-donut-label">cells</text>
    </svg>
    <div className="cell-type-breakdown"><h3><NeuronIcon size={16}/>{label} <strong>{number(total)}</strong></h3>
      <div className="cell-type-legend">{types.map(row=>{const content=<><i style={{background:cellTypeColor(row.type)}}/><span>{row.type}</span><strong>{number(row.count)}</strong>{showExports&&<small>{number(row.withExports)} with saved exports</small>}</>;return onSelect?<button key={row.type} aria-pressed={selected===row.type} title="Filter the cell list below" onClick={()=>onSelect(selected===row.type?null:row.type)}>{content}</button>:<div className="cell-type-entry" key={row.type}>{content}</div>;})}</div>
      {!types.length&&<p>No cells in this scope.</p>}<small>Each cell UUID counted once{showExports?' · export counts are cells with at least one exported epoch':''}.</small>
    </div>
  </div>;
}
