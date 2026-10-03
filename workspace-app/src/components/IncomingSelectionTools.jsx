import {useLayoutEffect,useRef,useState} from 'react';
import {CheckSquare,Plus,Square,MoreHorizontal,Eye} from 'lucide-react';
import {api,number} from '../api.js';
import {loadIncomingSelection,incomingSelectionCount} from '../incomingSelection.js';
import IncomingCellTypes from './IncomingCellTypes.jsx';

export default function IncomingSelectionTools({source,cells,freshCells=null,filtered=false,targets,cell,epoch,focusUuid=null,onSelect,disabled,savedCount,onSave,onReview,onReplace}){
  const [working,setWorking]=useState(false),[error,setError]=useState('');
  const pending=useRef(null),committed=useRef(null);
  const scope=JSON.stringify([source,cells.map(value=>[value.cell_uuid,value.epochs]),targets,cell?.cell_uuid,targets.length||cell?null:focusUuid,disabled]);
  useLayoutEffect(()=>{committed.current=scope;return()=>{committed.current=null;pending.current?.abort();};},[scope]);
  const importCount=incomingSelectionCount({targets,cells,cell,epoch});
  const hasTarget=targets.length>0||!!cell||!!epoch;
  const noun=targets.length?'selected':cell?'cell':epoch?'epoch':'selected';
  async function run(action){
    if(disabled||pending.current)return;
    const controller=new AbortController();pending.current=controller;setWorking(true);setError('');
    const isCurrent=()=>committed.current===scope&&!controller.signal.aborted;
    try{
      const wholeView=action==='select-all'||action==='replace-view';
      const ids=wholeView||cell&&!targets.length
        ?await loadIncomingSelection({source,cells,cellUuid:wholeView?null:cell.cell_uuid,request:api,signal:controller.signal,isCurrent})
        :targets.length?[...targets]:epoch?[epoch.epoch_uuid]:[];
      if(!isCurrent()||!ids.length)return;
      if(action==='select-all')onSelect(ids);
      else {
        const saved=action==='replace-view'?await onReplace(ids):action==='review'?await onReview(ids):await onSave(ids,action==='add');
        if(saved===false&&committed.current!==null)setError('Draft update was not confirmed. Check the draft warning and refresh before continuing.');
      }
    }catch(error){
      if(error.name==='AbortError'&&committed.current!==null)setError('Incoming view changed while preparing the selection. Choose the action again.');
      else if(isCurrent())setError(error.message);
    }
    finally{if(pending.current===controller){pending.current=null;setWorking(false);}}
  }
  const locked=disabled||working;
  return <section className="incoming-draft-tools" aria-label="Incoming draft selection">
    {filtered&&<div className="incoming-filtered-types"><IncomingCellTypes cells={freshCells} count={freshCells?.length} scope="Filtered incoming view" compact/></div>}
    <div className="incoming-draft-summary"><strong>Draft selection</strong><span aria-live="polite">{savedCount==null?'Saved count unavailable':`${number(savedCount)} saved`}</span></div>
    <div className="incoming-draft-controls"><button disabled={locked||!cells.length} title="Highlight every epoch in this filtered incoming view, up to 1,000" onClick={()=>run('select-all')}><CheckSquare size={13}/> Select all</button><button disabled={locked||!targets.length} title="Clear temporary highlights; saved draft selections stay unchanged" onClick={()=>onSelect([])}><Square size={13}/> Deselect all</button></div>
    <div className="incoming-draft-controls"><button className="primary" disabled={locked||importCount==null||importCount===0} aria-description="Add these exact epochs to the review draft. Review marks and Main stay unchanged." title="Add these exact epochs to the review draft; review marks and Main stay unchanged" onClick={()=>run('add')}><Plus size={14}/> Import ({importCount==null?'count unavailable':`${number(importCount)} ${importCount===1?'epoch':'epochs'}`})</button><button disabled={locked||!hasTarget} title="Mark these exact epochs reviewed without changing saved selections" onClick={()=>run('review')}><Eye size={13}/> Review {noun}</button><details><summary aria-label="More draft selection actions" title="Remove or replace saved selections"><MoreHorizontal size={16}/></summary><div><button disabled={locked||!hasTarget} onClick={()=>run('remove')}>Remove {noun} from draft</button><p>Draft selection and review marks are separate. Shared tags save immediately.</p></div></details></div>
    {filtered&&<div className="incoming-filtered-export"><button disabled={locked||!cells.length||!onReplace} title="Replace saved selections with this exact filtered view; review marks and exclusions stay unchanged" onClick={()=>run('replace-view')}>Use only this view in draft</button><small>Then review the selected epochs and Export. Export uses the saved draft, not view filters.</small></div>}
    {working&&<p role="status">Preparing selection…</p>}{error&&<p role="alert">{error}</p>}
  </section>;
}
