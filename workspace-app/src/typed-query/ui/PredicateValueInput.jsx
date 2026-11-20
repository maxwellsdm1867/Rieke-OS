import {useRetainedView} from '../../retainedWorkspaceViews.js';
import {useSemanticReset} from '../../useSemanticReset.js';
import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ChevronDown,Pin} from 'lucide-react';
import {humanize,useResource} from '../../api.js';
import {predicateValueSuggestions} from '../predicateValueSuggestions.js';

function recordedPath(field,scope,query){
  const params=new URLSearchParams({field,limit:'30'});
  if(scope.protocol)params.set('protocol_uuid',scope.protocol);
  if(scope.filters&&Object.keys(scope.filters).length)params.set('filters',JSON.stringify(scope.filters));
  if(query)params.set('q',query);
  return '/explore/field-values?'+params;
}

function applyRecordedChoice(node,choice){
  const literal=choice.value_json,value=JSON.parse(literal);
  const unsafe=number=>Number.isInteger(number)&&!Number.isSafeInteger(number);
  if(!['in','not_in'].includes(node.operator)){
    const exact=choice.type==='number'&&(node.field.startsWith('h5/')||unsafe(value));
    return {...node,valueType:exact?'exact':choice.type,valueText:choice.type==='string'?value:literal};
  }
  const source=node.valueText.trim()||'[]',numberToken=Symbol(),items=JSON.parse(source,(_key,item,context)=>
    typeof item==='number'?{[numberToken]:context?.source,unsafe:unsafe(item)}:item);
  if(!Array.isArray(items))throw Error('Enter a JSON list before adding a recorded value.');
  if(items.some(item=>choice.type==='number'?item?.[numberToken]===literal:item===value))return node;
  if(items.length>=100)throw Error('Use at most 100 alternative values.');
  const exact=node.valueType==='exact'||items.some(item=>item?.unsafe)||choice.type==='number'&&unsafe(value);
  // Append to the original JSON so existing 64-bit integers retain every digit.
  return {...node,valueType:exact?'exact':'array',valueText:source.slice(0,-1)+(items.length?',':'')+literal+']'};
}

export default function PredicateValueInput({node,choices,pinnedProtocols,onChange,disabled,recorded=null}){
  const retainedActive=useRetainedView()?.active!==false;
  const [open,setOpen]=useState(false),[active,setActive]=useState(0),[position,setPosition]=useState(null);
  const [query,setQuery]=useState(''),[selectionError,setSelectionError]=useState('');
  const input=useRef(null),searchInput=useRef(null),wrap=useRef(null),popup=useRef(null),list=useRef(null),id=useId();
  const protocol=node.field==='protocol',alternatives=['in','not_in'].includes(node.operator);
  const sharedTag=/^annotations\/(cell|epoch|effective)\/tags$/.test(node.field);
  const path=!open||disabled?null:recorded?recordedPath(node.field,recorded,query):sharedTag?`/annotation-tags?q=${encodeURIComponent(node.valueText)}&limit=100`:null;
  const vocabulary=useResource(path,recorded?.revision||0,120);
  const data=vocabulary.data;
  const stale=recorded&&data&&(data.field!==node.field||!data.generation||
    ['metadata','typed','source','publication'].some(key=>data.generation[key]!==recorded.generation?.[key]));
  const tagChoices=(data?.tags||[]).map(item=>({type:'string',value:item.tag}));
  const suggestions=recorded?(stale||vocabulary.loading||vocabulary.error?[]:data?.values||[]):
    predicateValueSuggestions(sharedTag?[...tagChoices,...choices]:choices,node.valueText,pinnedProtocols,protocol);
  const selected=Math.min(active,Math.max(0,suggestions.length-1));
  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  useEffect(()=>{
    if(!open||!retainedActive)return;
    function place(){const box=wrap.current?.getBoundingClientRect();if(!box)return;const width=Math.min(Math.max(box.width,400),window.innerWidth-32),below=window.innerHeight-box.bottom-12,above=box.top-12,lower=below>=220||below>=above,height=Math.min(310,Math.max(100,lower?below:above));setPosition({left:Math.max(16,Math.min(box.left,window.innerWidth-width-16)),top:lower?box.bottom+5:Math.max(8,box.top-height-5),width,maxHeight:height});}
    function outside(event){if(!wrap.current?.contains(event.target)&&!popup.current?.contains(event.target))setOpen(false);}
    place();window.addEventListener('resize',place);window.addEventListener('scroll',place,true);document.addEventListener('pointerdown',outside);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);document.removeEventListener('pointerdown',outside);};
  },[open,retainedActive]);
  const searchVisible=!!recorded&&open&&!!position&&retainedActive;
  useEffect(()=>{if(searchVisible)searchInput.current?.focus();},[searchVisible]);
  useSemanticReset(selected,()=>{if(!retainedActive)return;const option=list.current?.children[selected];if(!option)return;const top=option.offsetTop,bottom=top+option.offsetHeight;if(top<list.current.scrollTop)list.current.scrollTop=top;else if(bottom>list.current.scrollTop+list.current.clientHeight)list.current.scrollTop=bottom-list.current.clientHeight;});
  function choose(choice){
    try{onChange(recorded?applyRecordedChoice(node,choice):{...node,valueText:choice.value});}
    catch{setSelectionError('Use a valid JSON list with at most 100 alternatives.');return;}
    setSelectionError('');setActive(0);
    input.current?.focus();setOpen(false);
  }
  function keys(event){
    if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();input.current?.focus();setOpen(false);}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(!open){setOpen(true);setActive(0);}else setActive(Math.max(0,Math.min(suggestions.length-1,selected+(event.key==='ArrowDown'?1:-1))));}
    if(open&&(event.key==='Enter'||!recorded&&event.key==='Tab')&&!event.shiftKey&&suggestions[selected]){if(event.key==='Enter')event.preventDefault();choose(suggestions[selected]);}
  }
  function blur(event){if(!wrap.current?.contains(event.relatedTarget)&&!popup.current?.contains(event.relatedTarget))setOpen(false);}
  return <div className="pb-value-control pb-autocomplete" ref={wrap}>
    <input ref={input} role="combobox" aria-label="Condition value" aria-autocomplete="list" aria-expanded={open} aria-controls={open?id:undefined} aria-activedescendant={open&&suggestions[selected]?`${id}-${selected}`:undefined} disabled={disabled} value={node.valueText} title={node.valueText} placeholder={alternatives?'[25, 100]':protocol?'e.g. VariableMeanNoise':sharedTag?'Search tags…':'Enter value'} onFocus={()=>{setOpen(!recorded);setActive(0);}} onBlur={blur} onChange={event=>{onChange({...node,valueText:event.target.value});setActive(0);if(!recorded)setOpen(true);}} onKeyDown={keys}/>
    <button type="button" disabled={disabled} className="pb-value-toggle" aria-label="Show value suggestions" aria-expanded={open} onMouseDown={event=>event.preventDefault()} onClick={()=>{const next=!open;input.current?.focus();setQuery('');setSelectionError('');setOpen(next);}}><ChevronDown size={13}/></button>
    {open&&position&&retainedActive&&createPortal(<div ref={popup} className="pb-value-popup" style={position} onMouseDown={event=>{if(event.target.tagName!=='INPUT')event.preventDefault();}}>
      <div className="pb-value-popup-title">{protocol?'Protocol ID suggestions':sharedTag?'Saved tags':'Recorded values'}<small>{recorded?'↑ ↓ choose · Enter to select':'↑ ↓ choose · Tab complete'}</small></div>
      {recorded&&<input type="search" ref={searchInput} role="combobox" aria-label="Find a recorded value" aria-expanded="true" aria-autocomplete="list" aria-controls={id} aria-activedescendant={suggestions[selected]?`${id}-${selected}`:undefined} placeholder="Find a recorded value" value={query} maxLength={120} onBlur={blur} onKeyDown={keys} onChange={event=>{setQuery(event.target.value);setActive(0);}}/>}
      <div ref={list} role="listbox" id={id} aria-label="Matching value suggestions" className="pb-value-options">{suggestions.map((choice,index)=>{
        const value=recorded?(choice.type==='string'?JSON.parse(choice.value_json):choice.value_json):choice.value;
        return <button type="button" tabIndex={-1} role="option" id={`${id}-${index}`} aria-selected={index===selected} key={recorded?choice.type+choice.value_json:choice.value} className={index===selected?'active':''} onMouseEnter={()=>setActive(index)} onClick={()=>choose(choice)}><span><strong>{protocol?humanize(value.split('.').at(-1)):value===''?'""':value}</strong>{protocol&&<small>{value}</small>}</span>{recorded&&<small>{choice.type}</small>}{choice.pinned&&<span className="pb-value-pin"><Pin size={11}/> Pinned</span>}</button>;
      })}</div>
      {selectionError&&<p role="alert">{selectionError}</p>}
      {recorded?(vocabulary.error||stale?<p role="alert">{vocabulary.error||'Recorded fields changed. Refresh the field catalog.'}{vocabulary.error&&<button type="button" onClick={vocabulary.reload}>Retry</button>}</p>:
        vocabulary.loading?<p role="status">Finding recorded values…</p>:!suggestions.length?<p>No matching recorded values.</p>:data?.truncated&&<p>More values are recorded. Narrow the search.</p>):
        !suggestions.length&&<p>{sharedTag&&vocabulary.loading?'Finding tags…':'No suggestions. You can use your own text.'}</p>}
    </div>,wrap.current?.closest('dialog')||document.body)}
  </div>;
}
