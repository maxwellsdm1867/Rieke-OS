import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowDown, ArrowUp, Check, Copy, Code2, ChevronDown, ChevronRight, GitBranch, GripVertical, Keyboard, LoaderCircle, Plus, Search, X } from 'lucide-react';
import { number, useResource } from '../api.js';
import './TreeBuilder.css';
import { reorderIds } from '../ordering.js';
import { startPointerDrag } from '../pointerDrag.js';
import {COMMON_TREE_FIELDS,treeFieldLabel,treeFieldHint,treeFieldExamples,treeFieldMatches,groupingFieldRank} from '../treeFieldPresentation.js';
import {jointDefinition,shortFieldLabel,uncombineLevel} from '../jointGrouping.js';
import JointGroupingEditor from './JointGroupingEditor.jsx';
import {useDelayedLoading} from './NavigationLoading.jsx';

const categories = ['Common', 'Parameters', 'Combinations', 'Conditions', 'Suggested', 'All'];
const categoryLabel = category => category === 'Suggested' ? 'Recommended' : category === 'Parameters' ? 'Protocol settings' : category === 'All' ? 'All metadata' : category;
const sameOrder = (a,b) => JSON.stringify(a) === JSON.stringify(b);
const sampleText = treeFieldExamples;
function Highlight({text, term}) {
  const value = String(text || '');
  const query = term.trim();
  const index = query ? value.toLocaleLowerCase().indexOf(query.toLocaleLowerCase()) : -1;
  return index < 0 ? value : <>{value.slice(0,index)}<mark>{value.slice(index,index+query.length)}</mark>{value.slice(index+query.length)}</>;
}

export default function TreeBuilder({protocolId, catalogPath, catalogData, queryString='', revision=0, value, onChange, preview, loading, error}) {
  const [order,setOrder] = useState(value);
  const fetchedCatalog = useResource(catalogData?null:`${catalogPath || `/protocols/${protocolId}/tree-fields`}${queryString?'?'+queryString:''}`,revision);
  const catalog = catalogData?{data:catalogData,loading:false,error:null,reload:()=>{}}:fetchedCatalog;
  const fields = useMemo(()=>{
    const recorded=(catalog.data?.fields || []).map(field=>({...field,label:treeFieldLabel(field)}));
    for(const id of order)if(!recorded.some(field=>field.id===id)){
      const combined=jointDefinition(id,recorded);if(combined)recorded.push(combined);
    }
    return recorded;
  },[catalog.data?.fields,JSON.stringify(order)]);
  const fieldMap = useMemo(()=>new Map(fields.map(field=>[field.id,field])),[fields]);
  const suggestions = catalog.data?.suggestions || [];
  const presets=[{id:'acquisition-groups',label:'Date → Cell → Epoch group → Block',fields:['date','cell','group','block']},...(catalog.data?.presets || [])];
  const [expanded,setExpanded] = useState(true);
  const [showMoveControls,setShowMoveControls] = useState(false);
  const [search,setSearch] = useState('');
  const [category,setCategory] = useState('Common');
  const [open,setOpen] = useState(false);
  const [active,setActive] = useState(0);
  const [visible,setVisible] = useState(40);
  const [position,setPosition] = useState(null);
  const input = useRef(null), trigger = useRef(null), popup = useRef(null);
  const listId = useId(), dragHelpId = useId();
  const cancelDrag = useRef(null), currentOrder = useRef(order);
  currentOrder.current=order;
  useEffect(()=>()=>cancelDrag.current?.(),[]);
  const [dragging,setDragging] = useState(null);
  const [dropSpot,setDropSpot] = useState(null);
  const [announcement,setAnnouncement] = useState('');
  const [copyMessage,setCopyMessage]=useState(null),[layoutError,setLayoutError]=useState('');
  const orderKey = JSON.stringify(order), valueKey = JSON.stringify(value);
  useEffect(()=>setCopyMessage(null),[orderKey]);
  useEffect(()=>setOrder(JSON.parse(valueKey)),[valueKey]);
  function changeOrder(next){
    const updated=typeof next==='function'?next(currentOrder.current):next;
    currentOrder.current=updated;setOrder(updated);onChange(updated);
  }
  const matches = useMemo(()=>{
    return fields.filter(field=>treeFieldMatches(field,{order,category,suggestions,search}))
      .sort((a,b)=>category==='Common'?COMMON_TREE_FIELDS.indexOf(a.id)-COMMON_TREE_FIELDS.indexOf(b.id):category==='Suggested'?suggestions.indexOf(a.id)-suggestions.indexOf(b.id):groupingFieldRank(a)-groupingFieldRank(b) || (a.grouping_priority ?? 100)-(b.grouping_priority ?? 100) || a.label.localeCompare(b.label));
  },[fields,orderKey,search,category,suggestions]);
  const suggestedLayout=catalog.data?.suggested_layout;
  const offerLayout=suggestedLayout&&!sameOrder(order,suggestedLayout.fields);
  const shown=matches.slice(0,visible);
  useEffect(()=>{setActive(0);setVisible(40);},[search,category,orderKey]);
  useEffect(()=>{
    if(!open)return;
    const reposition=()=>{
      const box=trigger.current?.getBoundingClientRect();
      if(!box)return;
      const width=Math.min(430,window.innerWidth-24);
      const availableBelow=window.innerHeight-box.bottom-14;
      const availableAbove=box.top-14;
      const below=availableBelow>=440 || availableBelow>=availableAbove;
      const height=Math.min(440,Math.max(160,below?availableBelow:availableAbove));
      setPosition({left:Math.max(12,Math.min(box.left,window.innerWidth-width-12)),width,
        top:below?box.bottom+5:Math.max(8,box.top-height-5),height});
    };
    const outside=event=>{if(!trigger.current?.contains(event.target)&&!popup.current?.contains(event.target))setOpen(false);};
    reposition();window.addEventListener('resize',reposition);window.addEventListener('scroll',reposition,true);
    document.addEventListener('pointerdown',outside);
    return()=>{window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);document.removeEventListener('pointerdown',outside);};
  },[open]);
  useEffect(()=>{
    if(open)document.getElementById(`${listId}-${active}`)?.scrollIntoView({block:'nearest'});
  },[active,open,listId]);
  function add(field) {
    if(order.length>=8||order.includes(field.id))return;
    changeOrder(previous=>[...previous,field.id]);setSearch('');setOpen(false);trigger.current?.focus();
  }
  function commitOrder(next, sourceId) {
    if(next===order || sameOrder(next,order))return;
    changeOrder(next);
    setAnnouncement(`${fieldMap.get(sourceId)?.label || sourceId} moved to level ${next.indexOf(sourceId)+1} of ${next.length}.`);
  }
  function move(index,offset) {
    if(index+offset<0 || index+offset>=order.length)return;
    commitOrder(reorderIds(order,order[index],order[index+offset],offset>0?'after':'before'),order[index]);
  }
  function clearDrag() {cancelDrag.current?.();cancelDrag.current=null;setDragging(null);setDropSpot(null);}
  function pointerStart(event,id) {
    cancelDrag.current?.();
    const root=event.currentTarget.closest('.tree-builder');
    function targetAt(event) {
      const hit=root?.ownerDocument.elementFromPoint(event.clientX,event.clientY);
      if(!hit || !root.contains(hit))return null;
      let row=hit.closest('[data-tree-field]');
      if(!row && hit.closest('.tb-steps')) {
        row=[...root.querySelectorAll('[data-tree-field]')].sort((a,b)=>{
          const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();
          return Math.abs(event.clientY-(x.top+x.height/2))-Math.abs(event.clientY-(y.top+y.height/2));
        })[0];
      }
      if(!row || !root.contains(row))return null;
      const box=row.getBoundingClientRect();
      return {id:row.dataset.treeField,placement:event.clientY<box.top+box.height/2?'before':'after'};
    }
    cancelDrag.current=startPointerDrag(event,{
      getTarget:targetAt,
      onStart:()=>{setDragging(id);setOpen(false);},
      onTarget:target=>setDropSpot(previous=>previous?.id===target?.id&&previous?.placement===target?.placement?previous:target),
      onDrop:target=>{
        const previous=currentOrder.current,next=reorderIds(previous,id,target.id,target.placement);
        if(next!==previous){changeOrder(next);setAnnouncement(`${fieldMap.get(id)?.label || id} moved to level ${next.indexOf(id)+1} of ${next.length}.`);}
      },
      onCancel:()=>setAnnouncement('Reordering cancelled. Your grouping is unchanged.'),
      onFinish:()=>{cancelDrag.current=null;setDragging(null);setDropSpot(null);},
    });
  }
  function usePreset(preset) {
    if(preset.fields.length>8||new Set(preset.fields).size!==preset.fields.length||preset.fields.some(id=>!fieldMap.has(id)))return;
    changeOrder([...preset.fields]);setOpen(false);setSearch('');
  }
  function keys(event) {
    if(event.key==='Escape'){setOpen(false);event.stopPropagation();return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp') {
      event.preventDefault();setOpen(true);
      setActive(index=>Math.max(0,Math.min(shown.length-1,open?index+(event.key==='ArrowDown'?1:-1):0)));return;
    }
    if(event.key==='Enter') {event.preventDefault();if(open&&shown[active])add(shown[active]);else setOpen(true);}
    if(event.key==='Tab')setOpen(false);
  }
  const isCurrent = !loading && sameOrder((preview?.levels || []).map(level=>level.field),order);
  const pending = loading || orderKey!==valueKey;
  const showPending=useDelayedLoading(pending&&!error);
  async function copyMatlab(){
    if(!isCurrent||pending||error||!preview?.matlab_command)return;
    try{await navigator.clipboard.writeText(preview.matlab_command);setCopyMessage({text:'Copied EpicTreeGUI command',error:false});}
    catch{setCopyMessage({text:'Clipboard unavailable. Select the code to copy it.',error:true});}
  }
  const heading = order.map(id=>fieldMap.get(id)?.label || id).join(' → ');
  const groups=shown.reduce((result,field,index)=>{
    const groupCategory=category==='Common'?'Common':field.category;
    const group=result.find(g=>g.category===groupCategory);
    if(group)group.entries.push({field,index});else result.push({category:groupCategory,entries:[{field,index}]});
    return result;
  },[]);
  return <section className="tree-builder" aria-label="Tree builder">
    <div className="tb-heading"><button className="tb-disclosure" onClick={()=>{setExpanded(!expanded);setOpen(false);}} aria-expanded={expanded}>
      {expanded?<ChevronDown size={14}/>:<ChevronRight size={14}/>}<GitBranch size={15}/><strong>Arrange tree</strong>
    </button><span>{order.length} / 8 levels</span></div>
    <div className="tb-body">{!expanded?<button className="tb-collapsed-summary" onClick={()=>setExpanded(true)}>{heading || 'All epochs · flat view'}</button>:<>
      <div className={`tb-drag-guide ${dragging?'active':''}`}><GripVertical size={14}/><span>{dragging?`Moving ${fieldMap.get(dragging)?.label || dragging} · release to place`:'Drag levels into the order you want'}</span></div>
      <p id={dragHelpId} className="tb-visually-hidden">Drag a level or its handle to rearrange levels. On a handle, use Alt and the up or down arrow. Optional move buttons are available under Show move controls.</p>
      <div className="tb-visually-hidden" role="status" aria-live="polite">{announcement}</div>
      <ol className={`tb-steps ${dragging?'tb-is-dragging':''}`} aria-label="Ordered tree splits" onKeyDown={event=>{if(event.key==='Escape'&&dragging){event.preventDefault();clearDrag();setAnnouncement('Reordering cancelled.');}}}>
        {order.map((id,index)=>{
          const field=fieldMap.get(id),level=isCurrent?preview.levels[index]:null;
          return <li key={id} className={`${dragging===id?'tb-drag-source ':''}${dragging&&dropSpot?.id===id&&dragging!==id?`tb-drop-${dropSpot.placement}`:''}`}
            data-tree-field={id} onPointerDown={event=>{
              if(event.pointerType==='touch'||event.target.closest('button,input,select,a,summary'))return;
              pointerStart(event,id);
            }}>
            <button className="tb-drag-handle" onPointerDown={event=>pointerStart(event,id)}
              aria-label={`Reorder ${field?.label || id}, level ${index+1}`} aria-describedby={dragHelpId}
              title="Drag to reorder · Alt + ↑ / ↓" onKeyDown={event=>{if(event.altKey&&['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();move(index,event.key==='ArrowUp'?-1:1);}}}>
              <GripVertical size={17}/></button><span className="tb-step-number">{index+1}</span><div className="tb-step-field">
            <strong title={field?.path || id}>{field?.components?'Combined settings':field?.label || id}</strong>
            {field?.components&&<div className="tb-joint-level">{field.components.map((key,index)=><span className={`joint-chip joint-color-${index%3}`} key={key}>{shortFieldLabel(fieldMap.get(key))}</span>)}</div>}
            <small>{level&&Number.isFinite(level.groups)?`${number(level.groups)} ${level.groups===1?'branch':'branches'}${field?.distinct_count!=null&&level.groups!==field.distinct_count?` · ${number(field.distinct_count)} values`:''}${level.missing_epochs?` · ${number(level.missing_epochs)} not recorded`:''}`:categoryLabel(field?.category) || 'Saved field'}{field?.components?' · all values match':''}</small>
          </div><div className="tb-step-actions">
            {field?.components&&<button aria-label={`Separate ${field.label} grouping`} title="Separate into individual levels" onClick={()=>{try{changeOrder(uncombineLevel(order,id));setLayoutError('');}catch(error){setLayoutError(error.message);}}}>Separate</button>}
            {showMoveControls&&<><button disabled={index===0} aria-label={`Move ${field?.label || id} earlier`} title="Move up one level" onClick={()=>move(index,-1)}><ArrowUp size={13}/></button>
            <button disabled={index===order.length-1} aria-label={`Move ${field?.label || id} later`} title="Move down one level" onClick={()=>move(index,1)}><ArrowDown size={13}/></button></>}
            <button aria-label={`Remove ${field?.label || id} grouping`} title="Remove level" onClick={()=>changeOrder(previous=>previous.filter(key=>key!==id))}><X size={13}/></button>
          </div></li>;
        })}
      </ol>
      {layoutError&&<p className="tb-error" role="alert">{layoutError}<button onClick={()=>setLayoutError('')}>Dismiss</button></p>}
      {order.length>1&&<button className="tb-move-controls-toggle" aria-pressed={showMoveControls} onClick={()=>setShowMoveControls(value=>!value)}><Keyboard size={13}/>{showMoveControls?'Hide move controls':'Show move controls'}</button>}
      {!order.length&&<div className="tb-flat"><span className="tb-flat-dot"/> All matching epochs in one list</div>}
      <JointGroupingEditor fields={fields} order={order} onChange={next=>{changeOrder(next);setOpen(false);setAnnouncement('Combined fields into one split. Every component must match.');}}/>
      <button ref={trigger} className="tb-add-split" aria-haspopup="dialog" aria-expanded={open} disabled={order.length>=8 || catalog.loading&&!catalog.data} onClick={()=>{setSearch('');setCategory(suggestions.length?'Suggested':'Common');setOpen(value=>!value);}}><Plus size={16}/>{order.length>=8?'Eight-level limit reached':'Add a split'}<ChevronDown size={14}/></button>
      <button className="tb-acquisition-preset" disabled={['date','cell','group','block'].some(id=>!fieldMap.has(id))} onClick={()=>usePreset({fields:['date','cell','group','block']})}><GitBranch size={14}/><span>Date → Cell → Epoch group → Block</span></button>
      <div className="tb-presets" aria-label="Tree presets">
        <label className="tb-quick-layout"><span>Quick layout</span>
          <select aria-label="Quick tree layout" value={presets.find(preset=>sameOrder(order,preset.fields))?.id || ''}
            onChange={event=>{const preset=presets.find(item=>item.id===event.target.value);if(preset)usePreset(preset);}}>
            <option value="">Choose a preset</option>
            {presets.map(preset=><option key={preset.id} value={preset.id}
              disabled={preset.fields.length>8||preset.fields.some(id=>!fieldMap.has(id))}>{preset.label}</option>)}
          </select>
        </label>
        <button className={!order.length?'active':''} onClick={()=>changeOrder([])}>Flat list</button>
      </div>
      {catalog.error&&<div className="tb-error" role="alert">{catalog.error}<button onClick={catalog.reload}>Retry fields</button></div>}
      {catalog.loading&&!catalog.data&&<p className="tb-note"><LoaderCircle size={12} className="spin"/> Reading available fields…</p>}
      <p className="tb-note">Source values only. Missing values remain in the tree.</p>
    </>}</div>
    <div className={`tb-preview-status ${error?'tb-error-status':''}`} role="status">
      {showPending?<LoaderCircle size={13} className="spin"/>:error?<X size={13}/>:<Check size={13}/>}
      <span>{showPending?'Updating tree…':error?'Tree could not be updated. Your data is unchanged.':`${number(preview?.count ?? catalog.data?.total)} matching epochs · tree preview`}</span>
    </div>
    <details className="tb-matlab-code"><summary><Code2 size={14}/> EpicTreeGUI code</summary>
      <p>Export this layout to EpicTreeGUI, then run this line from the extracted bundle with EpicTreeGUI on your MATLAB path.</p>
      {isCurrent&&!pending&&!error&&preview?.matlab_command?<pre>{preview.matlab_command}</pre>:<p role="status">Waiting for a valid tree preview…</p>}
      <button onClick={copyMatlab} disabled={!isCurrent||pending||!!error||!preview?.matlab_command}><Copy size={14}/> Copy EpicTree code</button>
      {copyMessage&&<p role={copyMessage.error?'alert':'status'}>{copyMessage.text}</p>}
    </details>
    {open&&position&&createPortal(<div ref={popup} className="tb-popup" role="dialog" aria-label="Add a split" style={{left:position.left,top:position.top,width:position.width,maxHeight:position.height}}
      onKeyDown={event=>{if(event.key==='Escape'){setOpen(false);trigger.current?.focus();}}}>
      <div className="tb-popup-title"><strong>Split on a recorded field</strong><button aria-label="Close split chooser" onClick={()=>{setOpen(false);trigger.current?.focus();}}><X size={14}/></button></div>
      <div className="tb-search-wrap tb-popup-search"><Search size={15}/><input ref={input} autoFocus role="combobox" aria-label="Find a split field" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown[active]?`${listId}-${active}`:undefined} placeholder="Find a field to split on…" value={search} onChange={event=>{setSearch(event.target.value);setCategory(event.target.value.trim()?'All':suggestions.length?'Suggested':'Common');}} onKeyDown={keys}/></div>
      <div className="tb-categories">{categories.map(name=><button key={name} className={category===name?'active':''}
        onMouseDown={event=>event.preventDefault()} onClick={()=>{setCategory(name);input.current?.focus();}}>{categoryLabel(name)}</button>)}</div>
      <div id={listId} role="listbox" aria-label="Available split fields" className="tb-options">
        {groups.map(group=><div role="group" aria-label={categoryLabel(group.category)} key={group.category}>
          {category!=='Common'&&<div className="tb-group-name">{categoryLabel(group.category)}</div>}
          {group.entries.map(({field,index})=><button id={`${listId}-${index}`} role="option" aria-selected={active===index} tabIndex={-1}
            className={`tb-option ${active===index?'active':''}`} key={field.id} title={field.path || field.id}
            onMouseDown={event=>event.preventDefault()} onMouseEnter={()=>setActive(index)} onClick={()=>add(field)}>
            <div><strong><Highlight text={field.label} term={search}/></strong><span>{field.recorded_distinct_count===1?(field.missing_count||field.null_count?'1 non-null value':'Constant'):`${number(field.distinct_count)} values`}</span></div>
            {(COMMON_TREE_FIELDS.includes(field.id)||field.grouping_hint)&&<small className="tb-field-hint">{treeFieldHint(field)}</small>}<small><Highlight text={sampleText(field) || 'No recorded values'} term={search}/></small>
            {field.missing_count>0&&<small>{number(field.missing_count)} epochs have no recorded value</small>}
          </button>)}
        </div>)}
        {!matches.length&&<div className="tb-no-results"><p>{catalog.error?'Fields could not be loaded.':search?'No fields match this search. Try a parameter name or source value.':'All fields in this category are already in the tree.'}</p><button onMouseDown={event=>event.preventDefault()} onClick={()=>{setCategory('All');setSearch('');input.current?.focus();}}>Browse all metadata fields</button></div>}
      </div>
      {matches.length>visible&&<button className="tb-more" onMouseDown={event=>event.preventDefault()} onClick={()=>setVisible(count=>count+40)}>Show 40 more fields</button>}
      {offerLayout&&!search&&<button className="tb-chooser-layout" onClick={()=>usePreset(suggestedLayout)} title={suggestedLayout.fields.map(id=>fieldMap.get(id)?.label || id).join(' → ')}><GitBranch size={14}/> Use suggested protocol layout</button>}
      <div className="tb-popup-footer">↑ ↓ to browse · Enter to add · Esc to close</div>
    </div>,document.body)}
  </section>;
}
