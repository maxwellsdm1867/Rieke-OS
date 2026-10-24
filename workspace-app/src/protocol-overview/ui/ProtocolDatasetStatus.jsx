import {protocolDatasetStatus} from '../protocolDatasetStatus.js';
const operators={eq:'is',ne:'is not',neq:'is not',gt:'is greater than',gte:'is at least',lt:'is less than',lte:'is at most',in:'is one of',not_in:'is not one of',contains:'contains',exists:'exists',missing:'is missing',is_null:'is null'};
function Predicate({value}){
  if(!value||typeof value!=='object')return <pre>{JSON.stringify(value,null,2)}</pre>;
  for(const key of ['all','any'])if(Array.isArray(value[key]))return <div className="protocol-query-group"><strong>{key==='all'?'All of these conditions':'Any of these conditions'}</strong>{value[key].length?<ul>{value[key].map((child,index)=><li key={index}><Predicate value={child}/></li>)}</ul>:<p>{key==='all'?'All epochs match (no conditions).':'No epochs match (no alternatives).'}</p>}</div>;
  if(value.not)return <div className="protocol-query-group"><strong>Not</strong><Predicate value={value.not}/></div>;
  const op=value.operator??value.op;
  if(value.field&&operators[op])return <span><code>{value.field}</code> {operators[op]}{Object.hasOwn(value,'value')&&<> <code>{JSON.stringify(value.value)}</code></>}</span>;
  return <pre>{JSON.stringify(value,null,2)}</pre>;
}
export default function ProtocolDatasetStatus({data,pendingReviewCells}){
  const {state,query,filtered}=protocolDatasetStatus(data);
  const preset=data.starter_query??data.definition?.query;
  const pendingKnown=Number.isSafeInteger(pendingReviewCells)&&pendingReviewCells>=0;
  return <div className="protocol-dataset-description">
    <p><strong>{filtered?'Filtered view of this protocol':state==='saved'?'Saved data in this protocol':state==='live'?'Data matching this protocol’s query':'Protocol data'}</strong></p>
    <p>{state==='saved'?'New imports are not added automatically. Matching epochs from new recordings wait for review before you merge them into this dataset.':state==='live'?'Showing current matches to the protocol preset. Before the next import, DISCO saves this set; matching new recordings then wait for review rather than being added automatically.':'The protocol’s dataset state is unavailable. Automatic import behavior could not be verified.'}</p>
    {filtered&&<p>The counts below include only the current browsing filters.</p>}
    {state==='saved'&&<p>{pendingKnown?(pendingReviewCells===0?'No new recordings are waiting for review.':`${pendingReviewCells.toLocaleString()} ${pendingReviewCells===1?'cell has':'cells have'} matching epochs waiting for review.`):'Incoming review status is unavailable.'} Review here refers to incoming data; epoch review marks are separate.</p>}
    <details className="protocol-query-details" key={`${data.definition?.protocol_uuid}:${data.query_revision??''}`}><summary>Show query</summary>
      {query?<><p>{state==='saved'?'Current saved predicate. It is used to find matching new recordings; rerunning it can differ from the saved epochs shown here.':'Current protocol predicate. These are current catalog matches, not a saved set of epochs.'} Read-only.</p><h4>Current query</h4><Predicate value={query.predicate??query}/><details><summary>Exact query</summary><pre>{JSON.stringify(query,null,2)}</pre></details></>:<p>The current protocol query is unavailable. Refresh the overview to try again.</p>}
      {preset&&<details className="protocol-preset-details"><summary>Protocol preset</summary><p>The protocol’s starter rule. A saved dataset can use a different predicate; the current query above takes precedence.</p><Predicate value={preset.predicate??preset}/><details><summary>Exact preset</summary><pre>{JSON.stringify(preset,null,2)}</pre></details></details>}
    </details>
  </div>;
}
