import PredicateValueInput from './PredicateValueInput.jsx';
import {predicateFieldLabel as fieldLabel,predicateFieldGroup,predicateFieldRank,predicateFieldSearch} from '../predicateFieldPresentation.js';
import {useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ChevronDown,FolderPlus,MessageCircle,Info,MoreHorizontal,Plus,Search,Trash2,X} from 'lucide-react';
import {humanize} from '../api.js';
import {newCondition,newGroup} from './predicateState.js';
import {blankValue,fieldCondition,isTagField,canUseDateInput,fieldCategory,groupChoice,operatorChoices,preferredValueType,recordedValueChoices,setGroupChoice,valueTypes} from './predicateEditor.js';
import './PredicateBuilder.css';

const labels={eq:'is',ne:'is not',in:'is one of',not_in:'is not one of',contains:'contains',gt:'is greater than',gte:'is at least',lt:'is less than',lte:'is at most',exists:'is recorded',missing:'is missing',is_null:'is null'};
const displayValue=value=>typeof value==='string'?`“${value}”`:JSON.stringify(value);
const categoryOrder=['Common fields','Recording','Experiment','Cell','Epoch group','Epoch block','Epoch','Protocol settings','Conditions'];
const categoryRank=value=>categoryOrder.includes(value)?categoryOrder.indexOf(value):99;
function FieldPicker({fields,value,onChange,disabled}){
  const [open,setOpen]=useState(false),[search,setSearch]=useState(''),[category,setCategory]=useState('All fields'),[limit,setLimit]=useState(50),[active,setActive]=useState(0),[position,setPosition]=useState(null);
  const wrap=useRef(null),popup=useRef(null),trigger=useRef(null),input=useRef(null),listId=useId();
  const selected=fields.find(field=>field.id===value);
  const categories=[...new Set(fields.map(predicateFieldGroup))].sort((a,b)=>categoryRank(a)-categoryRank(b)||a.localeCompare(b));
  const tokens=search.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const available=fields.filter(field=>{
    const group=predicateFieldGroup(field);if(category!=='All fields'&&group!==category)return false;
    const text=predicateFieldSearch(field);
    return tokens.every(token=>text.includes(token));
  }).sort((a,b)=>categoryRank(predicateFieldGroup(a))-categoryRank(predicateFieldGroup(b))||predicateFieldRank(a)-predicateFieldRank(b)||predicateFieldGroup(a).localeCompare(predicateFieldGroup(b))||fieldLabel(a).localeCompare(fieldLabel(b)));
  const shown=available.slice(0,limit);
  useEffect(()=>{setActive(0);setLimit(50);},[search,category]);
  useEffect(()=>{if(disabled)setOpen(false);},[disabled]);
  useEffect(()=>{
    if(!open)return;
    const reposition=()=>{
      const box=trigger.current?.getBoundingClientRect();if(!box)return;
      const width=Math.min(450,window.innerWidth-24),below=window.innerHeight-box.bottom-14,above=box.top-14;
      const lower=below>=280||below>=above,height=Math.min(425,Math.max(150,lower?below:above));
      setPosition({left:Math.max(12,Math.min(box.left,window.innerWidth-width-12)),width,top:lower?box.bottom+5:Math.max(8,box.top-height-5),height});
    };
    const outside=event=>{if(!wrap.current?.contains(event.target)&&!popup.current?.contains(event.target))setOpen(false);};
    reposition();window.addEventListener('resize',reposition);window.addEventListener('scroll',reposition,true);document.addEventListener('pointerdown',outside);
    return()=>{window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);document.removeEventListener('pointerdown',outside);};
  },[open]);
  useEffect(()=>{if(open&&position)input.current?.focus();},[open,!!position]);
  useEffect(()=>{if(open)document.getElementById(`${listId}-${active}`)?.scrollIntoView({block:'nearest'});},[open,active,listId]);
  function close(){setOpen(false);trigger.current?.focus();}
  function select(field){if(disabled)return;onChange(field);close();setSearch('');}
  return <div className="pb-field-picker" ref={wrap}><button type="button" ref={trigger} className="pb-field-button" disabled={disabled} onClick={()=>setOpen(value=>!value)} onKeyDown={event=>{if(event.key==='ArrowDown'){event.preventDefault();setOpen(true);}}} aria-expanded={open} aria-haspopup="listbox" title={selected?`${selected.label}\n${selected.path}`:value}><span>{fieldLabel(selected) || value || 'Choose field'}</span><ChevronDown size={12}/></button>
    {open&&position&&createPortal(<div ref={popup} className="pb-field-popup pb-field-portal" style={{left:position.left,top:position.top,width:position.width,maxHeight:position.height}}><label className="pb-field-search"><Search size={14}/><input ref={input} value={search} placeholder="Search fields or recorded values" role="combobox" aria-label="Find predicate field" aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown[active]?`${listId}-${active}`:undefined} onChange={event=>setSearch(event.target.value)} onKeyDown={event=>{
      if(event.key==='Escape'){close();event.preventDefault();}
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();setActive(index=>Math.max(0,Math.min(shown.length-1,index+(event.key==='ArrowDown'?1:-1))));}
      if(event.key==='Enter'){event.preventDefault();if(shown[active])select(shown[active]);}
    }}/></label><div className="pb-field-categories"><label>Field group<select value={category} onChange={event=>setCategory(event.target.value)} aria-label="Predicate field group"><option>All fields</option>{categories.map(group=><option key={group}>{group}</option>)}</select></label><span>{available.length} {available.length===1?'field':'fields'}</span></div>
      <div id={listId} className="pb-field-options" role="listbox" aria-label="Predicate fields">{shown.map((field,index)=><div key={field.id} role="presentation">{(index===0||predicateFieldGroup(shown[index-1])!==predicateFieldGroup(field))&&<div className="pb-field-category-heading" role="presentation">{predicateFieldGroup(field)}</div>}<button id={`${listId}-${index}`} type="button" tabIndex={-1} className={index===active?'active':''} role="option" aria-selected={index===active} title={field.path} onMouseEnter={()=>setActive(index)} onClick={()=>select(field)}><span><strong>{fieldLabel(field)}</strong><small>{(field.examples||[]).slice(0,3).join(' · ') || 'No non-null example recorded'}</small></span><em>{field.distinct_count ?? '—'} {field.distinct_count===1?'value':'values'}</em></button></div>)}{!shown.length&&<p>No recorded fields match.</p>}</div>
      <div className="pb-picker-footer"><span>↑ ↓ to browse · Enter to choose</span>{available.length>limit&&<button type="button" onClick={()=>setLimit(value=>value+50)}>Show more</button>}</div>
    </div>,wrap.current?.closest('dialog') || document.body)}
  </div>;
}
function ValueEditor({node,field,onChange,pinnedProtocols,disabled}){
  const unary=['exists','missing','is_null'].includes(node.operator),list=['in','not_in'].includes(node.operator);
  const inputType=canUseDateInput(node)?'date':'text';
  const choices=recordedValueChoices(field,node.operator);
  const protocolAlias=node.field==='protocol'&&['eq','ne'].includes(node.operator)&&node.valueType==='string'&&field?.choices?.some(choice=>choice.type==='string'&&choice.value===node.valueText)?humanize(node.valueText.split('.').at(-1)):null;
  function chooseValue(choice){
    const value=choice.value;if(!valueTypes.includes(choice.type))return;
    if(list){let values=[];try{const parsed=JSON.parse(node.valueText);if(Array.isArray(parsed))values=parsed;}catch{}if(values.length>=100)return;if(!values.some(item=>JSON.stringify(item)===JSON.stringify(value)))values.push(value);onChange({...node,valueType:'array',valueText:JSON.stringify(values)});}
    else onChange({...node,valueType:choice.type,valueText:typeof value==='string'?value:JSON.stringify(value)});
  }
  if(unary)return <div className="pb-no-value">No value needed</div>;
  if(!list&&node.valueType==='string'&&inputType==='text'&&['contains','eq','ne'].includes(node.operator))return <PredicateValueInput node={node} choices={choices} pinnedProtocols={pinnedProtocols} disabled={disabled} onChange={onChange}/>;
  return <div className="pb-value-control">{node.valueType==='boolean'&&!list?<select aria-label="Condition value" value={node.valueText} onChange={event=>onChange({...node,valueText:event.target.value})}><option value="true">true</option><option value="false">false</option></select>:node.valueType==='null'&&!list?<span className="pb-null">null</span>:<input className={protocolAlias?'pb-protocol-raw':undefined} aria-label="Condition value" type={inputType} inputMode={node.valueType==='number'&&!list?'decimal':undefined} value={node.valueText} title={node.valueText} placeholder={list?'[25, 100]':node.valueType==='number'?'Number':inputType==='date'?'YYYY-MM-DD':node.field==='protocol'?'e.g. VariableMeanNoise':'Enter value'} onChange={event=>onChange({...node,valueText:event.target.value})}/>}
    {protocolAlias&&<span className="pb-protocol-alias" aria-hidden="true">{protocolAlias}</span>}
    {!!choices.length&&<select className="pb-recorded-values" aria-label="Choose a recorded value" title="Recorded values · preserves source types" value="" onChange={event=>{if(event.target.value!=='')chooseValue(choices[Number(event.target.value)]);}}><option value="">⌄</option>{choices.slice(0,100).map((choice,index)=><option key={index} value={index} disabled={!valueTypes.includes(choice.type)}>{!valueTypes.includes(choice.type)?'[Unsupported object] ':''}{node.field==='protocol'&&typeof choice.value==='string'?humanize(choice.value.split('.').at(-1)):displayValue(choice.value)} · {choice.type} · {choice.example_only?'recorded example':`${choice.count} ${choice.count===1?'epoch':'epochs'}`}</option>)}</select>}
  </div>;
}
function Condition({node,fields,onChange,onRemove,onAdd,canAdd,disabled,pinnedProtocols}){
  const [options,setOptions]=useState(false),field=fields.find(item=>item.id===node.field);
  const operators=operatorChoices(field,labels,node.operator),list=['in','not_in'].includes(node.operator);
  function changeField(next){onChange({...node,...fieldCondition(next)});}
  function changeOperator(operator){
    const wasList=['in','not_in'].includes(node.operator),isList=['in','not_in'].includes(operator),type=preferredValueType(field,operator);
    const needsReset=wasList!==isList||(operator==='contains'&&node.valueType==='array')||(['gt','gte','lt','lte'].includes(operator)&&node.valueType!=='number');
    onChange({...node,operator,...(needsReset?{valueType:type,valueText:blankValue(type)}:{})});
  }
  return <div className={`pb-condition ${node.negated?'condition-negated':''}`}><div className="pb-condition-main">{node.negated&&<span className="pb-condition-not" title="NOT applies to this entire condition">NOT</span>}<FieldPicker fields={fields} value={node.field} onChange={changeField} disabled={disabled}/><select className="pb-operator" aria-label="Condition operator" value={node.operator} onChange={event=>changeOperator(event.target.value)}>{operators.map(operator=><option key={operator} value={operator}>{labels[operator] || operator}</option>)}</select><ValueEditor pinnedProtocols={pinnedProtocols} disabled={disabled} node={node} field={field} onChange={onChange}/><div className="pb-row-actions"><button type="button" className={options?'active':''} aria-expanded={options} aria-label="Condition options" title="Value type, NOT and source field" onClick={()=>setOptions(value=>!value)}><MoreHorizontal size={14}/></button><button type="button" disabled={!canAdd} aria-label="Add condition below" title="Add condition below" onClick={onAdd}><Plus size={14}/></button><button type="button" aria-label="Remove condition" title="Remove condition" onClick={onRemove}><X size={14}/></button></div></div>
    {isTagField(field)&&node.operator==='contains'&&<small className="pb-tag-hint">{node.field==='annotations/effective/tags'?'Matches this tag on the epoch or its cell.':'Matches one exact tag.'}</small>}
    {options&&<div className="pb-condition-advanced"><label>Value type<select aria-label="Value type" value={list?'array':node.valueType} disabled={list} onChange={event=>onChange({...node,valueType:event.target.value,valueText:blankValue(event.target.value)})}>{valueTypes.map(type=><option key={type} value={type}>{type==='array'?'JSON list':type}</option>)}</select></label><label className="pb-negation-option"><input type="checkbox" checked={node.negated} onChange={event=>onChange({...node,negated:event.target.checked})}/> Negate condition (NOT)</label><span title={field?.path}>{field?.path || 'No source field selected'}</span></div>}
  </div>;
}
function Group({node,fields,onChange,onRemove,depth=0,disabled,pinnedProtocols}){
  function update(index,value){onChange({...node,children:node.children.map((child,i)=>i===index?value:child)});}
  function insert(index){if(node.children.length<100)onChange({...node,children:[...node.children.slice(0,index+1),newCondition(),...node.children.slice(index+1)]});}
  const choice=groupChoice(node),full=node.children.length>=100,tagField=fields.find(field=>field.id==='annotations/effective/tags');
  return <section className={`pb-group ${depth?'pb-nested-group':''} ${node.negated?'negated':''}`}><div className="pb-group-header"><select aria-label={depth?'Nested group logic':'Root group logic'} value={choice} onChange={event=>onChange(setGroupChoice(node,event.target.value))}><option value="all">All</option><option value="any">Any</option><option value="none">None</option>{choice==='not_all'&&<option value="not_all">Not all</option>}</select><span>of the following are true</span><div className="pb-group-header-actions">{tagField&&<button type="button" disabled={full} title="Search shared cell and epoch tags" onClick={()=>onChange({...node,children:[...node.children,{...newCondition(),...fieldCondition(tagField)}]})}><MessageCircle size={13}/> Tag</button>}<button type="button" disabled={full} onClick={()=>onChange({...node,children:[...node.children,newCondition()]})}><Plus size={13}/> Condition</button><button type="button" disabled={depth>=5||full} onClick={()=>onChange({...node,children:[...node.children,newGroup()]})}><FolderPlus size={13}/> Group</button>{onRemove&&<button type="button" className="pb-remove-group" onClick={onRemove} aria-label="Remove nested group" title="Remove nested group"><Trash2 size={13}/></button>}</div></div>
    <div className="pb-children">{node.children.map((child,index)=>child.kind==='group'?<Group pinnedProtocols={pinnedProtocols} key={child.id} node={child} fields={fields} depth={depth+1} disabled={disabled} onChange={value=>update(index,value)} onRemove={()=>onChange({...node,children:node.children.filter((_,i)=>i!==index)})}/>:<Condition pinnedProtocols={pinnedProtocols} key={child.id} node={child} fields={fields} disabled={disabled} onChange={value=>update(index,value)} onAdd={()=>insert(index)} canAdd={!full} onRemove={()=>onChange({...node,children:node.children.filter((_,i)=>i!==index)})}/>)}{!node.children.length&&<p className="pb-empty">{choice==='all'?(depth?'No conditions: this group is true.':'No conditions: all query-eligible source epochs match.'):choice==='none'?'No alternatives: this None group is true.':choice==='not_all'?'No conditions: this Not all group is false.':'No alternatives: this Any group is false.'}</p>}</div>

  </section>;
}
export default function PredicateBuilder({draft,fields,onChange,disabled=false,pinnedProtocols=[]}){
  return <fieldset disabled={disabled} className="predicate-builder"><Group pinnedProtocols={pinnedProtocols} node={draft} fields={fields} onChange={onChange} disabled={disabled}/><details className="pb-semantics"><summary><Info size={13}/> Matching rules</summary><p>All means AND; Any means OR; None means NOT(Any). A loaded Not all group keeps NOT(All). Missing, null, empty text and numeric values are distinct. “Is not” excludes missing fields; NOT(is) includes them. Units come from the source, not inferred labels.</p></details></fieldset>;
}
