import {useMemo, useState} from 'react';
import {Combine, Plus, X} from 'lucide-react';
import {combineLevels,shortFieldLabel} from '../jointGrouping.js';

export default function JointGroupingEditor({fields,order,onChange}) {
  const [selected,setSelected]=useState([]),[search,setSearch]=useState(''),[error,setError]=useState('');
  const available=useMemo(()=>fields.filter(field=>!field.components&&!field.id.startsWith('joint/')),[fields]);
  const byId=useMemo(()=>new Map(available.map(field=>[field.id,field])),[available]);
  const candidates=available.filter(field=>!selected.includes(field.id)&&`${field.label} ${field.id}`.toLowerCase().includes(search.trim().toLowerCase()));
  const matches=candidates.slice(0,40);
  const stale=selected.some(id=>!byId.has(id));
  const history=['parameters/history1','parameters/history2','parameters/target'];
  function apply(components) {
    try {
      if(components.some(id=>!byId.has(id)))throw new Error('A selected field is no longer available. Remove it and choose a recorded field.');
      onChange(combineLevels(order,components));setSelected([]);setSearch('');setError('');
    }
    catch(e){setError(e.message);}
  }
  return <details className="tb-joint-editor"><summary><Combine size={14}/> Combine fields into one level</summary>
    <p>Group epochs only when <strong>every value matches</strong>. Each combination becomes one branch.</p>
    {history.every(id=>byId.has(id))&&<button className="tb-joint-history" onClick={()=>apply(history)}><Combine size={14}/><span>History 1 + History 2 + Target</span></button>}
    <div className="tb-joint-members" aria-label="Fields to combine">{selected.map((id,index)=><span key={id} className={`joint-chip joint-color-${index%3}`}><span>{shortFieldLabel(byId.get(id))}</span><button aria-label={`Remove ${shortFieldLabel(byId.get(id))} from combination`} onClick={()=>setSelected(previous=>previous.filter(key=>key!==id))}><X size={12}/></button></span>)}</div>
    <input aria-label="Find fields to combine" placeholder="Find a field to combine…" value={search} onChange={event=>setSearch(event.target.value)}/>
    <select aria-label="Add field to combination" value="" disabled={selected.length>=6} onChange={event=>{if(event.target.value)setSelected(previous=>[...previous,event.target.value]);setSearch('');setError('');}}>
      <option value="">{selected.length>=6?'Six fields selected':'Choose a recorded field…'}</option>
      {matches.map(field=><option key={field.id} value={field.id}>{field.label}</option>)}
    </select>
    {candidates.length>40&&<small>Showing 40 fields. Search to find more.</small>}
    <button className="tb-joint-apply" disabled={selected.length<2||stale} onClick={()=>apply(selected)}><Plus size={13}/> Add combined level{selected.length>0?` · ${selected.length} fields`:''}</button>
    {stale&&<p role="alert">A selected field is no longer available. Remove it to continue.</p>}
    <small>Replaces these fields’ separate levels, if present. Drag the combined level to place it.</small>
    {error&&<p role="alert" className="tb-error">{error}</p>}
  </details>;
}
