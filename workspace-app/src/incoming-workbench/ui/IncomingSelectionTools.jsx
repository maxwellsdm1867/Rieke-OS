import {useLayoutEffect,useRef,useState} from 'react';
import {CheckSquare,Square,Eye,GitMerge} from 'lucide-react';
import {api,number} from '../../api.js';
import {loadIncomingSelection,incomingSelectionCount} from '../incomingSelection.js';
export default function IncomingSelectionTools({source,cells,targets=[],onSelect,disabled,onMerge,viewSelected=false,onViewSelected,children}){
  const [working,setWorking]=useState(false),[error,setError]=useState('');
  const pending=useRef(null),committed=useRef(null);
  const scope=JSON.stringify([source,cells.map(value=>[value.cell_uuid,value.epochs]),targets,disabled]);
  useLayoutEffect(()=>{committed.current=scope;return()=>{committed.current=null;pending.current?.abort();};},[scope]);
  const count=incomingSelectionCount({targets}),locked=disabled||working;
  async function selectAll(){
    if(locked||pending.current)return;
    const controller=new AbortController();pending.current=controller;setWorking(true);setError('');
    const isCurrent=()=>committed.current===scope&&!controller.signal.aborted;
    try{const ids=await loadIncomingSelection({source,cells,request:api,signal:controller.signal,isCurrent});if(isCurrent())onSelect(ids,{treeSelection:{on:true}});}
    catch(error){if(committed.current!==null)setError(error.name==='AbortError'?'Incoming view changed while selecting. Choose Select all again.':error.message);}
    finally{if(pending.current===controller){pending.current=null;setWorking(false);}}
  }
  return <section className="incoming-draft-tools" aria-label="Incoming selection actions">
    <button disabled={locked||!cells.length} onClick={selectAll}><CheckSquare size={13}/> Select all</button>
    <button disabled={locked} onClick={()=>onSelect([],{treeSelection:{on:false}})}><Square size={13}/> Deselect all</button>
    {typeof children==='function'?children(locked):children}
    <button disabled={locked||!viewSelected&&!targets.length} aria-pressed={viewSelected} onClick={onViewSelected}><Eye size={13}/> {viewSelected?'Return to all':'View selected'}</button>
    <button className="primary" disabled={locked||count==null||count===0||!onMerge} aria-description="Merge these selected epochs into Main, marking them reviewed. Existing Main data is preserved." onClick={()=>onMerge([...targets])}><GitMerge size={14}/> Merge ({count==null?'count unavailable':`${number(count)} ${count===1?'epoch':'epochs'}`})</button>
    {working&&<p className="incoming-draft-feedback" role="status">Selecting all scoped epochs…</p>}{error&&<p className="incoming-draft-feedback" role="alert">{error}</p>}
  </section>;
}
