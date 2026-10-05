import {Check,ChevronDown,Eye,Layers,SlidersHorizontal} from 'lucide-react';
import {humanize,number} from "../../api.js";
import {tagFilterLabel} from "../../typed-query/protocolViewFilter.js";
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
  <div className="protocol-scope-readouts">
   <span><Layers size={14}/> Protocol <strong>{number(all.epochs)}</strong> epochs · <strong>{number(all.cells)}</strong> cells</span>
   <span><Eye size={14}/> Browsing <strong>{number(visible.epochs)}</strong> epochs · <strong>{number(visible.cells)}</strong> cells{filtered&&<button className="quiet" onClick={onClear}>Show all recordings</button>}</span>
   <span><Check size={14}/> Export marks <strong>{number(all.included??visible.included)}</strong> included · {number((all.epochs||0)-(all.included??visible.included??0))} excluded</span>
   <button className="quiet" onClick={onExport}>Choose export subset</button>
  </div>
  {badges.length>0&&<div className="protocol-view-chips"><span>View filters</span>{badges.map(label=><span key={label}>{label}</span>)}</div>}
  <details className="protocol-query-details"><summary><ChevronDown size={13}/> Protocol rule & scope details</summary><div className="protocol-rule-summary"><Rule value={query}/></div><p>Browsing filters change what you see. Export marks are independent; choose export filters in the export dialog.</p><button className="quiet" onClick={onEdit}><SlidersHorizontal size={14}/> Edit protocol rule</button><pre>{JSON.stringify(query,null,2)}</pre></details>
 </section>;
}
