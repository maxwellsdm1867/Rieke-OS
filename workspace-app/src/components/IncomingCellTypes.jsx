import {incomingCellTypes} from '../incomingCellTypes.js';
import {cellTypeColor} from '../cellTypes.js';
import {number} from '../api.js';
import NeuronIcon from './NeuronIcon.jsx';

export default function IncomingCellTypes({cells,count,scope='Frozen proposal',compact=false}){
  const groups=incomingCellTypes(cells,count);
  const chips=groups?.map(({type,count})=><span className="incoming-type-chip" key={type} title={type} style={{'--type-color':cellTypeColor(type)}}><NeuronIcon size={13}/><strong>{number(count)}</strong> {type.replace(/^RGC\\/i,'')}</span>);
  return <details className={`incoming-cell-types ${compact?'compact':''}`}>
    <summary aria-label={`${scope} cell types`}><span className="incoming-type-summary">{compact?`${scope} · ${groups===null?'unavailable':`${number(count)} ${count===1?'cell':'cells'}`}`:'Cell types'}</span><span className="incoming-type-chips">{groups===null?'Types unavailable':groups.length?chips:'0 cells'}</span></summary>
    <div className="incoming-type-disclosure"><strong>{scope} · {groups===null?'count unavailable':`${number(count)} distinct cells`}</strong><div>{groups===null?'Complete cell identities and counts are unavailable.':groups.length?chips:'No cells in this scope.'}</div><small>Recorded types only. Unclassified includes missing or unknown types. {compact?'Counts follow the current filters; saved draft selections are separate.':'View filters do not change the frozen incoming scope.'}</small></div>
  </details>;
}
