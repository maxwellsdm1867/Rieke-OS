import {Check,ChevronDown,Eye,Layers,SlidersHorizontal} from 'lucide-react';
import {humanize,number} from '../api.js';
import {tagFilterLabel} from '../protocolViewFilter.js';
import './ProtocolSelectionSummary.css';

function Rule({value}){
 if(!value)return null;
 if(value.kind==='source_predicate')return <Rule value={value.predicate}/>;
 if(value.not)return <span className="protocol-rule-group"><small>NOT</small><Rule value={value.not}/></span>;
 if(value.all||value.any){const rules=value.all||value.any;return rules.length?<span className="protocol-rule-group">{rules.map((rule,i)=><span key={i}>{i>0&&<small>{value.all?'AND':'OR'}</small>}<Rule value={rule}/></span>)}</span>:<span className="protocol-rule-chip">{value.all?'All project recordings':'No project recordings'}</span>;}
 const field=value.field==='EpochBlock.protocol_name'?'protocol':value.field;
 const label=field==='protocol'?humanize(String(value.value).split('.').at(-1)):Array.isArray(value.value)?value.value.join(', '):String(value.value??'');
 const operator={eq:'is',ne:'is not',contains:'contains',gt:'>',gte:'≥',lt:'<',lte:'≤'}[value.operator]||value.operator;
 return <span className="protocol-rule-chip"><span>{humanize(field)}</span><small>{operator}</small><strong title={String(value.value)}>{label}</strong></span>;
}
export default function ProtocolSelectionSummary({data,filters,onClear,onEdit,onExport}){
 const all=data.total_counts||data.counts||{},visible=data.counts||{},query=data.effective_query||data.definition?.query;
 const filtered=Object.keys(filters).length>0;
 const badges=[filters.cell_type&&`Cell type: ${filters.cell_type}`,filters.group_label&&`Group: ${filters.group_label}`,filters.cell_uuid&&'Selected cell',tagFilterLabel(filters)].filter(Boolean);
 return <section className="protocol-selection-flow" aria-label="Protocol recordings and export marks">
  <header><div><Layers size={16}/><h2>Recordings in this protocol</h2></div><button className="quiet" onClick={onEdit}><SlidersHorizontal size={14}/> Edit protocol rule</button></header>
  <div className="protocol-rule-summary"><Rule value={query}/></div>
  <div className="protocol-scope-cards">
   <div><span><Layers size={15}/> Protocol recordings</span><strong>{number(all.epochs)} <small>epochs</small></strong><p>{number(all.cells)} {all.cells===1?'cell':'cells'}</p></div>
   <div><span><Eye size={15}/> Browsing now</span><strong>{number(visible.epochs)} <small>epochs</small></strong><p>{filtered?`${number(visible.cells)} cells match the view filters`:'All protocol recordings are visible'}</p>{filtered&&<button className="quiet" onClick={onClear}>Show all recordings</button>}</div>
   <div><span><Check size={15}/> Marked for export</span><strong>{number(all.included??visible.included)} <small>epochs</small></strong><p>{number((all.epochs||0)-(all.included??visible.included??0))} excluded · still visible when browsing</p><button className="quiet" onClick={onExport}>Choose export subset</button></div>
  </div>
  {badges.length>0&&<div className="protocol-view-chips"><span>View filters</span>{badges.map(label=><span key={label}>{label}</span>)}</div>}
  <details className="protocol-query-details"><summary><ChevronDown size={13}/> Technical query details</summary><pre>{JSON.stringify(query,null,2)}</pre></details>
 </section>;
}
