import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Database,Hash,LoaderCircle,Search,SlidersHorizontal,Users,X} from 'lucide-react';
import {api} from '../api.js';
import './GlobalSearch.css';

export default function GlobalSearch({revision=0,onEpoch,onCell,onPredicate}){
  const dialog=useRef(null),input=useRef(null),items=useRef([]);
  const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[state,setState]=useState({data:null,loading:false,error:''});
  useEffect(()=>{const key=event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();setOpen(true);}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);
  useEffect(()=>{if(open){dialog.current?.showModal();input.current?.focus();}else dialog.current?.close();},[open]);
  useEffect(()=>{
    if(!open||!query.trim()){setState({data:null,loading:false,error:''});return;}
    const controller=new AbortController();setState({data:null,loading:true,error:''});
    const timer=setTimeout(()=>api(`/search?q=${encodeURIComponent(query.trim())}&limit=20`,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setState({data,loading:false,error:''});})
      .catch(error=>{if(!controller.signal.aborted)setState({data:null,loading:false,error:error.message});}),180);
    return()=>{controller.abort();clearTimeout(timer);};
  },[query,open,revision]);
  function choose(result){
    if(result.kind==='epoch'){if(result.protocol_uuid&&onEpoch)onEpoch(result);else onCell?.(result);}
    else if(result.kind==='cell')onCell?.(result);
    else onPredicate?.(result.predicate);
    setOpen(false);
  }
  const rows=state.data?.results||[];
  return <><button className="global-search-trigger" onClick={()=>setOpen(true)} aria-label="Search project metadata and UUIDs"><Search size={15}/><span>Search data</span><kbd>⌘ K</kbd></button>
    <dialog ref={dialog} className="global-search-dialog" aria-labelledby="global-search-title" onCancel={()=>setOpen(false)} onClose={()=>setOpen(false)} onClick={event=>{if(event.target===dialog.current){const box=dialog.current.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)setOpen(false);}}}>
      <header><div><h2 id="global-search-title">Search project data</h2><p>Look up an epoch or cell, or open a typed metadata predicate.</p></div><button className="icon-button" onClick={()=>setOpen(false)} aria-label="Close search"><X size={18}/></button></header>
      <label className="global-search-input"><Search size={19}/><input ref={input} value={query} onChange={event=>setQuery(event.target.value)} maxLength={512} placeholder="UUID, Cell3, frequencyCutoff = 100, history1 = [30, 10]" aria-label="Search UUID, field, or typed value" onKeyDown={event=>{if(event.key==='ArrowDown'&&rows.length){event.preventDefault();items.current[0]?.focus();}if(event.key==='Escape')setOpen(false);}}/>{state.loading&&<LoaderCircle size={17} className="spin"/>}</label>
      <p className="global-search-hint">Use <code>field = value</code>, <code>&gt;=</code>, or a JSON pair. Quoted text stays text; numbers stay numbers. UUID prefixes need at least 8 characters.</p>
      <div className="global-search-results" aria-live="polite">
        {state.error?<p className="error" role="alert">{state.error}</p>:state.loading?<p className="global-search-empty">Searching recorded metadata…</p>:!query.trim()?<p className="global-search-empty">Search works within the current project. Raw traces are loaded only after inspection.</p>:!rows.length?<p className="global-search-empty">No matches. Try a full UUID or an exact field name and typed value.</p>:<>
          {rows.map((result,index)=>{const Icon=result.kind==='cell'?Users:result.kind==='epoch'?Hash:SlidersHorizontal;return <button key={`${result.kind}:${result.id}`} ref={node=>{items.current[index]=node;}} className="global-search-result" onClick={()=>choose(result)} onKeyDown={event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const next=index+(event.key==='ArrowDown'?1:-1);if(next<0)input.current?.focus();else items.current[Math.min(rows.length-1,next)]?.focus();}}}>
            <Icon size={17}/><span><strong>{result.label}</strong><small>{result.detail}</small>{['cell','epoch'].includes(result.kind)&&<><code>{result.id}</code><small><Database size={11}/>{result.source_filename}{result.query_excluded?' · excluded from new source queries':''}{result.protocols?.length>0?` · inspect in ${result.protocols[0].name}`:''}</small></>}</span><ArrowRight size={15}/>
          </button>;})}
          {state.data.total>rows.length&&<p className="global-search-hint">Showing {rows.length} of {state.data.total} results. Narrow the field name or UUID prefix.</p>}
          {state.data.identity_ambiguous&&<p className="global-search-hint">This prefix matches multiple identities. Choose an exact UUID above.</p>}
          {state.data.field_ambiguous&&<p className="global-search-hint">This name appears at multiple metadata levels. Choose the recorded field above.</p>}
          {state.data.value_examples_only&&<p className="global-search-hint">General value results use catalog examples. Use an exact field/value expression to search every eligible epoch.</p>}
        </>}
      </div>
    </dialog></>;
}
