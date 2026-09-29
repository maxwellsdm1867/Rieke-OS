import {MessageCircle} from 'lucide-react';
import {number} from '../api.js';
import {annotationPredicate} from '../annotationTags.js';
import './AnnotationTags.css';
export default function ProtocolTagSummary({protocol,onFilter}){
  const counts=protocol.counts||{};
  const recorded=protocol.annotation_summary?.tags;
  const cellTags=new Map();for(const cell of protocol.cells||[])for(const chip of cell.annotations?.cell_tags||[])cellTags.set(chip.tag,chip.tag);
  const tags=Array.isArray(recorded)?recorded:[...cellTags.values()].map(tag=>({tag,scope:'cell'}));
  const summary=tags.slice(0,12),totalTags=protocol.annotation_summary?.total_tags??tags.length;
  return <section className="protocol-tag-summary" aria-label="Shared annotation summary"><header><MessageCircle size={15}/><strong>Tags</strong><span>{Number.isFinite(counts.shared_tagged_cells)?number(counts.shared_tagged_cells):'—'} cells tagged · {Number.isFinite(counts.shared_tagged_epochs)?number(counts.shared_tagged_epochs):'—'} epochs with effective tags</span></header><div className="annotation-summary-list">{summary.map(item=>onFilter?<button key={item.tag} onClick={()=>onFilter(annotationPredicate(item.scope==='cell'?'cell':'effective',item.tag))} title="Open a search predicate for this exact shared tag">{item.tag}{Number.isFinite(item.epoch_count)?` · ${number(item.epoch_count)} epochs`:item.scope==='cell'?' · cell':''}</button>:<span key={item.tag}>{item.tag}</span>)}</div>{!summary.length&&<small>Use Tags in the epoch browser to annotate a cell or individual epoch.</small>}{totalTags>12&&<small>{number(totalTags-12)} more tag values</small>}</section>;
}
