import {useEffect,useId,useRef,useState} from 'react';
import {MessageCircle,Plus,X} from 'lucide-react';
import {useResource} from '../api.js';
import './EpochTags.css';

export default function EpochTags({value,onValue,onAdd,onRemove,selectedTags=[],busy,scope='focused epoch',revision,focusRequest=0}){
  const [query,setQuery]=useState(value),[open,setOpen]=useState(false),[active,setActive]=useState(-1),input=useRef(null),listId=useId();
  useEffect(()=>{const timer=setTimeout(()=>setQuery(value.trim()),160);return()=>clearTimeout(timer);},[value]);
  useEffect(()=>{if(focusRequest){input.current?.focus();setOpen(true);}},[focusRequest]);
  const suggestions=useResource(open?`/tags?q=${encodeURIComponent(query)}&limit=12`:null,revision);
  const items=(suggestions.data?.tags||[]).filter(item=>!selectedTags.includes(item.tag));
  const choose=tag=>{onValue(tag);input.current?.focus();setOpen(false);setActive(-1);};
  useEffect(()=>setActive(-1),[query]);
  return <section className="epoch-tags" aria-label="Epoch tagging" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false);}}><header><MessageCircle size={14}/><strong>Tags</strong><small>{scope}</small></header>
    <form onSubmit={event=>{event.preventDefault();if(value.trim()){setOpen(false);onAdd(value.trim());}}}>
      <input ref={input} role="combobox" aria-expanded={open} aria-controls={open?listId:undefined} aria-autocomplete="list" aria-activedescendant={open&&items[active]?`${listId}-${active}`:undefined} aria-label={`Tag to add to ${scope}`} placeholder="Type a tag…" value={value} maxLength={255} disabled={busy} onFocus={()=>setOpen(true)} onChange={event=>{onValue(event.target.value);setActive(-1);setOpen(true);}} onKeyDown={event=>{if(event.key==='Escape')setOpen(false);if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();setOpen(true);setActive(index=>Math.max(0,Math.min(items.length-1,index+(event.key==='ArrowDown'?1:-1))));}if(event.key==='Enter'&&open&&items[active]){event.preventDefault();choose(items[active].tag);}}}/>
      <button disabled={busy||!value.trim()} className="primary" aria-label={`Add tag to ${scope}`}><Plus size={14}/> Add tag</button>
    </form>
    {open&&<div className="tag-suggestions"><div><small>Saved project tags</small><button aria-label="Close tag suggestions" onClick={()=>setOpen(false)}><X size={12}/></button></div><div id={listId} role="listbox" aria-label="Previously saved tag suggestions">{suggestions.loading?<small>Finding tags…</small>:suggestions.error?<small>Suggestions unavailable. You can still enter a tag.</small>:items.length?items.map((item,index)=><button role="option" aria-selected={active===index} id={`${listId}-${index}`} key={item.tag} disabled={busy} onClick={()=>choose(item.tag)}><MessageCircle size={11}/><span>{item.tag}</span></button>):<small>{value.trim()?'New tag — choose Add tag to save.':'No saved tags yet. Type your first tag.'}</small>}</div></div>}
    <div className="epoch-tag-chips">{selectedTags.map(tag=><button key={tag} disabled={busy} onClick={()=>onRemove(tag)} title="Remove from this epoch only" aria-label={`Remove tag ${tag} from focused epoch only`}>{tag}<X size={12}/></button>)}{!selectedTags.length&&<small>No tags on this epoch</small>}</div>
  </section>;
}
