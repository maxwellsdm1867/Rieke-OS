import {useMemo, useState} from 'react';
import {Combine, Plus, X} from 'lucide-react';
import {combineLevels,shortFieldLabel} from '../jointGrouping.js';

export default function JointGroupingEditor({fields,order,onChange,onOpenChange,onRequestField}) {
  const [selected,setSelected]=useState([]),[error,setError]=useState('');
  const available=useMemo(()=>fields.filter(field=>!field.components&&!field.id.startsWith('joint/')),[fields]);
  const byId=useMemo(()=>new Map(available.map(field=>[field.id,field])),[available]);
  const stale=selected.some(id=>!byId.has(id));
  const history=['parameters/history1','parameters/history2','parameters/target'];
  function apply(components) {
    try {
      if(components.some(id=>!byId.has(id)))throw new Error('A selected field is no longer available. Remove it and choose a recorded field.');
      onChange(combineLevels(order,components));setSelected([]);setError('');
    }
    catch(e){setError(e.message);}
  }
  return <details className="tb-joint-editor" onToggle={event=>onOpenChange?.(event.currentTarget.open)}><summary><Combine size={14}/> Combine fields into one level</summary>
    <p>Group epochs only when <strong>every value matches</strong>. Each combination becomes one branch.</p>
    {history.every(id=>byId.has(id))&&<button className="tb-joint-history" onClick={()=>{setSelected(history);setError('');}}><Combine size={14}/><span>History 1 + History 2 + Target</span></button>}
    <div className="tb-joint-members" aria-label="Fields to combine">{selected.map((id,index)=><span key={id} className={`joint-chip joint-color-${index%3}`}><span>{shortFieldLabel(byId.get(id))}</span><button aria-label={`Remove ${shortFieldLabel(byId.get(id))} from combination`} onClick={()=>setSelected(previous=>previous.filter(key=>key!==id))}><X size={12}/></button></span>)}</div>
    <button disabled={selected.length>=6} aria-haspopup="dialog" onClick={event=>onRequestField?.({selected,anchor:event.currentTarget,onSelect:field=>{setSelected(previous=>previous.includes(field.id)?previous:[...previous,field.id]);setError('');}})}><Plus size={13}/>{selected.length?'Add another field':'Add a field'}</button>
    <button className="tb-joint-apply" disabled={selected.length<2||stale} onClick={()=>apply(selected)}><Plus size={13}/> Add combined level{selected.length>0?` · ${selected.length} fields`:''}</button>
    {stale&&<p role="alert">A selected field is no longer available. Remove it to continue.</p>}
    <small>Replaces these fields’ separate levels, if present. Drag the combined level to place it.</small>
    {error&&<p role="alert" className="tb-error">{error}</p>}
  </details>;
}
