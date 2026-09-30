import {humanize} from '../api.js';

function recordedValue(value) {
  if (value === undefined || value === null) return 'Not recorded';
  if (value === '[]' || (Array.isArray(value) && value.length === 0)) return '[] (empty recorded field)';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}
export default function ScientificContext({epoch}) {
  const additions = epoch.metadata?.group?.properties?.externalSolutionAdditions;
  const historyProtocol=/VariableHistoryNoiseCurInject/.test(epoch.protocol_name || '');
  const controlFlag=Object.hasOwn(epoch.parameters || {},'isControl')?epoch.parameters.isControl:epoch.parameters?.controlMode;
  const historyControl=historyProtocol&&[1,true].includes(controlFlag);
  const historyPairs=historyProtocol?['history1','history2','target'].filter(key=>Array.isArray(epoch.parameters?.[key])&&epoch.parameters[key].length===2):[];
  const conditions = [
    ['currentMean','Current mean',''],
    ['currentSD','Current SD',''],
    ['frequencyCutoff','Frequency cutoff',''],
    ['stimTime','Stimulus duration',''],
  ].filter(([key])=>epoch.parameters?.[key] !== undefined && epoch.parameters[key] !== null);
  return <section className="scientific-context" aria-label="Recording and condition context">
    <div className="context-inline"><strong>{humanize(epoch.cell_type) || 'Type not recorded'}</strong><span>{epoch.source_filename || 'Source not recorded'}</span></div>
    <div className="context-inline"><span>Group label: <strong>{recordedValue(epoch.group_label)}</strong></span><span>External additions: <strong>{recordedValue(additions)}</strong></span></div>
    {historyControl&&<p className="history-control-note">Control epoch · target only; history settings were recorded but not delivered.</p>}
    {historyPairs.length>0&&<div className="history-pair-facts">{historyPairs.map(key=><div key={key}><span>{key==='target'?'Target':key==='history1'?'History 1':'History 2'}{historyControl&&key!=='target'?' · configured only':''}</span><strong>{recordedValue(epoch.parameters[key][0])} / {recordedValue(epoch.parameters[key][1])}</strong><small>Recorded mean / SD</small></div>)}</div>}
    {conditions.length>0&&<div className="condition-facts">{conditions.map(([key,label,units])=><div key={key}>
      <span>{label}</span><strong>{recordedValue(epoch.parameters[key])}{units && ` ${units}`}</strong>
    </div>)}</div>}
    <details className="context-timing"><summary>Block {epoch.block_start_time?.split(' ')[1] || 'time not recorded'} · acquisition details</summary><div className="context-facts">
      <div><span>Epoch block started</span><strong>{recordedValue(epoch.block_start_time)}</strong></div>
      <div><span>Epoch block ended</span><strong>{recordedValue(epoch.block_end_time)}</strong></div>
      <div className="context-protocol"><span>Acquisition protocol · source value</span><strong>{recordedValue(epoch.protocol_name)}</strong></div>
    </div><p className="source-note">Group labels and solution fields are separate source records. Empty fields do not establish control or wash.</p></details>
  </section>;
}
