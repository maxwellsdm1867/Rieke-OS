import {useLayoutEffect,useRef,useState} from 'react';
import {CheckSquare,Plus,Square,MoreHorizontal} from 'lucide-react';
import {api,number} from '../api.js';
import {loadIncomingSelection} from '../incomingSelection.js';

export default function IncomingSelectionTools({source,cells,targets,cell,epoch,focusUuid=null,onSelect,disabled,savedCount,onSave,onReview}){
  const [working,setWorking]=useState(false),[error,setError]=useState('');
  const pending=useRef(null),committed=useRef(null);
  const scope=JSON.stringify([source,cells.map(value=>[value.cell_uuid,value.epochs]),targets,cell?.cell_uuid,targets.length||cell?null:focusUuid,disabled]);
  useLayoutEffect(()=>{committed.current=scope;return()=>{committed.current=null;pending.current?.abort();};},[scope]);
  const hasTarget=targets.length>0||!!cell||!!epoch;
  const noun=targets.length?'selected':cell?'cell':epoch?'epoch':'selected';
  async function run(action){
    if(disabled||pending.current)return;
    const controller=new AbortController();pending.current=controller;setWorking(true);setError('');
    const isCurrent=()=>committed.current===scope&&!controller.signal.aborted;
    try{
      const ids=action==='select-all'||cell&&!targets.length
        ?await loadIncomingSelection({source,cells,cellUuid:action==='select-all'?null:cell.cell_uuid,request:api,signal:controller.signal,isCurrent})
        :targets.length?[...targets]:epoch?[epoch.epoch_uuid]:[];
      if(!isCurrent()||!ids.length)return;
      if(action==='select-all')onSelect(ids);
      else if(action==='review')await onReview(ids);
      else await onSave(ids,action==='add');
    }catch(error){if(error.name!=='AbortError'&&isCurrent())setError(error.message);}
    finally{if(pending.current===controller){pending.current=null;setWorking(false);}}
  }
  const locked=disabled||working;
  return <section className="incoming-draft-tools" aria-label="Incoming draft selection">
    <div className="incoming-draft-summary"><strong>Draft selection</strong><span aria-live="polite">{savedCount==null?'Saved count unavailable':`${number(savedCount)} saved`}</span></div>
    <div className="incoming-draft-controls"><button disabled={locked||!cells.length} title="Highlight every epoch in this filtered incoming view, up to 1,000" onClick={()=>run('select-all')}><CheckSquare size={13}/> Select all</button><button disabled={locked||!targets.length} title="Clear temporary highlights; saved draft selections stay unchanged" onClick={()=>onSelect([])}><Square size={13}/> Deselect all</button></div>
    <div className="incoming-draft-controls"><button className="primary" disabled={locked||!hasTarget} title="Save these exact epochs in the proposal draft; review marks and Main stay unchanged" onClick={()=>run('add')}><Plus size={14}/> Add {noun}{targets.length?` (${number(targets.length)})`:''}</button><details><summary aria-label="More draft selection actions" title="Remove saved selections or mark reviewed"><MoreHorizontal size={16}/></summary><div><button disabled={locked||!hasTarget} onClick={()=>run('remove')}>Remove {noun} from draft</button><button disabled={locked||!hasTarget} onClick={()=>run('review')}>Mark {noun} reviewed</button><p>Draft selection and review marks are separate. Shared tags save immediately.</p></div></details></div>
    {working&&<p role="status">Preparing selection…</p>}{error&&<p role="alert">{error}</p>}
  </section>;
}
