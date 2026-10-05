import {Tag} from 'lucide-react';
import {number} from '../../api.js';
import {annotationPredicate} from '../../annotationTags.js';
import '../../components/AnnotationTags.css';

export default function IncomingTagSummary({summary,onFilter,disabled=false}){
  return <section className="incoming-tag-summary" aria-label="Current shared tags in incoming page">
    <header><Tag size={13}/><strong>Current tags</strong><span>Incoming page</span></header>
    {summary?<><small>{number(summary.loaded)} of {number(summary.total)} epochs loaded · frozen membership</small><div className="incoming-tag-totals">{number(summary.cells)} cells · {number(summary.epochs)} epochs tagged</div>
      <div className="incoming-tag-list">{summary.tags.map(item=><button key={item.tag} disabled={disabled||!onFilter} className={`tag-color-${item.color}`} onClick={()=>onFilter(annotationPredicate('effective',item.tag))} title={`${item.tag}\n${item.authors.map(author=>`${author.kind==='cell'?'Inherited cell':'Direct epoch'} · ${author.name}${author.profile_uuid?` (${author.profile_uuid})`:''}`).join('\n')}\nFilter this exact current shared tag from any author; saved selections stay unchanged.`}><span>{item.tag}</span><small>{number(item.cells)} {item.cells===1?'cell':'cells'} · {number(item.epochs)} {item.epochs===1?'epoch':'epochs'}</small></button>)}</div>
      {!summary.tags.length&&<small>{summary.loaded?'No shared tags in this page.':'No epochs in this page.'}</small>}</>:<small role="status">Tag counts unavailable while this page refreshes.</small>}
  </section>;
}
