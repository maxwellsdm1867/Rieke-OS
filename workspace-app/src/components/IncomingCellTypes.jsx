import {incomingCellTypes} from '../incomingCellTypes.js';
import {cellTypeColor} from '../cellTypes.js';
import {number} from '../api.js';
import NeuronIcon from './NeuronIcon.jsx';

export default function IncomingCellTypes({cells,count,scope='Frozen proposal',compact=false}){
  const groups=incomingCellTypes(cells,count);
  const chips=groups?.map(({type,count})=><span className="incoming-type-chip" key={type} role="listitem" tabIndex={0} style={{'--type-color':cellTypeColor(type)}}><NeuronIcon size={13}/><strong>{number(count)}</strong> {type.replace(/^RGC\\/i,'')}</span>);
  return <div className={`incoming-cell-types ${compact?'compact':''}`} role="group" aria-label={`${scope} cell types`}>
    {compact&&<span className="incoming-type-summary">{scope} · {groups===null?'unavailable':`${number(count)} ${count===1?'cell':'cells'}`}</span>}
    <div className="incoming-type-chips" role="list" aria-label={`${scope} recorded type counts`}>{groups===null?<span role="listitem">Types unavailable</span>:groups.length?chips:<span role="listitem">0 cells</span>}</div>
  </div>;
}
