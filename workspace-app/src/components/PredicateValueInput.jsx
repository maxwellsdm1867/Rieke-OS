import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ChevronDown,Pin} from 'lucide-react';
import {humanize,useResource} from '../api.js';
import {predicateValueSuggestions} from '../predicateValueSuggestions.js';

export default function PredicateValueInput({node,choices,pinnedProtocols,onChange,disabled}){
  const [open,setOpen]=useState(false),[active,setActive]=useState(0),[position,setPosition]=useState(null);
  const input=useRef(null),wrap=useRef(null),popup=useRef(null),list=useRef(null),id=useId();
  const protocol=node.field==='protocol';
  const sharedTag=/^annotations\/(cell|epoch|effective)\/tags$/.test(node.field);
  // Fetch the live vocabulary: catalog array examples can be truncated and
  // cannot reliably suggest tags saved after the predicate catalog loaded.
  const tags=useResource(open&&sharedTag?`/annotation-tags?q=${encodeURIComponent(node.valueText)}&limit=100`:null,0,120);
  const tagChoices=(tags.data?.tags||[]).map(item=>({type:'string',value:item.tag}));
  const suggestions=predicateValueSuggestions(sharedTag?[...tagChoices,...choices]:choices,node.valueText,pinnedProtocols,protocol);
  const selected=Math.min(active,Math.max(0,suggestions.length-1));
  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  useEffect(()=>{
    if(!open)return;
    function place(){const box=wrap.current?.getBoundingClientRect();if(!box)return;const width=Math.min(Math.max(box.width,400),window.innerWidth-32),below=window.innerHeight-box.bottom-12,above=box.top-12,lower=below>=220||below>=above,height=Math.min(310,Math.max(100,lower?below:above));setPosition({left:Math.max(16,Math.min(box.left,window.innerWidth-width-16)),top:lower?box.bottom+5:Math.max(8,box.top-height-5),width,maxHeight:height});}
    function outside(event){if(!wrap.current?.contains(event.target)&&!popup.current?.contains(event.target))setOpen(false);}
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);document.addEventListener('pointerdown',outside);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);document.removeEventListener('pointerdown',outside);};
  },[open]);
  useEffect(()=>{const option=list.current?.children[selected];if(!option)return;const top=option.offsetTop,bottom=top+option.offsetHeight;if(top<list.current.scrollTop)list.current.scrollTop=top;else if(bottom>list.current.scrollTop+list.current.clientHeight)list.current.scrollTop=bottom-list.current.clientHeight;},[selected]);
  function choose(choice){onChange({...node,valueText:choice.value});setOpen(false);setActive(0);}
  return <div className="pb-value-control pb-autocomplete" ref={wrap}>
    <input ref={input} role="combobox" aria-label="Condition value" aria-autocomplete="list" aria-expanded={open} aria-controls={open?id:undefined} aria-activedescendant={open&&suggestions[selected]?`${id}-${selected}`:undefined} disabled={disabled} value={node.valueText} title={node.valueText} placeholder={protocol?'e.g. VariableMeanNoise':sharedTag?'Search tags…':'Enter value'} onFocus={()=>{setOpen(true);setActive(0);}} onBlur={event=>{if(!wrap.current?.contains(event.relatedTarget)&&!popup.current?.contains(event.relatedTarget))setOpen(false);}} onChange={event=>{onChange({...node,valueText:event.target.value});setActive(0);setOpen(true);}} onKeyDown={event=>{
      if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();setOpen(false);}
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(!open){setOpen(true);setActive(0);}else setActive(Math.max(0,Math.min(suggestions.length-1,selected+(event.key==='ArrowDown'?1:-1))));}
      if(open&&(event.key==='Enter'||event.key==='Tab')&&!event.shiftKey&&suggestions[selected]){if(event.key==='Enter')event.preventDefault();choose(suggestions[selected]);}
    }}/>
    <button type="button" disabled={disabled} className="pb-value-toggle" aria-label="Show value suggestions" onMouseDown={event=>event.preventDefault()} onClick={()=>{const next=!open;input.current?.focus();setOpen(next);}}><ChevronDown size={13}/></button>
    {open&&position&&createPortal(<div ref={popup} className="pb-value-popup" style={position} onMouseDown={event=>event.preventDefault()}>
      <div className="pb-value-popup-title">{protocol?'Protocol ID suggestions':sharedTag?'Saved tags':'Recorded values'}<small>↑ ↓ choose · Tab complete</small></div>
      <div ref={list} role="listbox" id={id} aria-label="Matching value suggestions" className="pb-value-options">{suggestions.map((choice,index)=><button type="button" tabIndex={-1} role="option" id={`${id}-${index}`} aria-selected={index===selected} key={choice.value} className={index===selected?'active':''} onMouseEnter={()=>setActive(index)} onClick={()=>{choose(choice);input.current?.focus();setOpen(false);}}><span><strong>{protocol?humanize(choice.value.split('.').at(-1)):choice.value}</strong>{protocol&&<small>{choice.value}</small>}</span>{choice.pinned&&<span className="pb-value-pin"><Pin size={11}/> Pinned</span>}</button>)}</div>
      {!suggestions.length&&<p>{sharedTag&&tags.loading?'Finding tags…':'No suggestions. You can use your own text.'}</p>}
    </div>,wrap.current?.closest('dialog')||document.body)}
  </div>;
}
