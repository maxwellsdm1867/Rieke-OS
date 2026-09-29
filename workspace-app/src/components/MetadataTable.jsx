import {useEffect,useRef,useState} from 'react';
import {Check} from 'lucide-react';
import {metadataClipboard,metadataHasEncodedInteger,metadataValueSafe,metadataValueText,registeredMetadataField} from './metadataValues.js';
import './MetadataPanel.css';

export default function MetadataTable({data,title='Metadata',badgeLabel,rows:providedRows,fields=[],copyable=false,compact=false}){
  const [feedback,setFeedback]=useState(null),[limit,setLimit]=useState(80),timer=useRef(null);
  const rows=providedRows || Object.entries(data || {}).map(([key,value])=>({key,label:key,path:[key],value}));
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  useEffect(()=>{setFeedback(null);setLimit(80);},[data,providedRows]);
  async function copy(row,kind,field){
    try{
      if(!globalThis.navigator?.clipboard?.writeText)throw new Error('Clipboard access is unavailable. Select the visible text and copy it manually.');
      const text=metadataClipboard(row,kind,field);await navigator.clipboard.writeText(text);
      setFeedback({message:`Copied ${kind==='setting'?'setting + value':kind==='pair'?'key + value':kind==='predicate'?'predicate JSON':kind==='field'?'field ID':['value','text'].includes(kind)?'value':'key'}: ${row.key}`,error:false});
    }catch(error){setFeedback({message:error.message || 'Clipboard access was denied. Select and copy the visible text manually.',error:true});}
    clearTimeout(timer.current);timer.current=setTimeout(()=>setFeedback(null),6000);
  }
  return <section className={`section metadata metadata-copyable ${compact?'metadata-compact':''}`}>{title&&<div className="section-heading"><h3>{title}</h3>{badgeLabel&&<span className="badge">{badgeLabel}</span>}</div>}
    {feedback&&<div className={`metadata-copy-feedback ${feedback.error?'copy-error':''}`} role={feedback.error?'alert':'status'}>{!feedback.error&&<Check size={13}/>}<span>{feedback.message}</span></div>}
    <dl>{rows.slice(0,limit).map((row,index)=>{
      const field=registeredMetadataField(row.path,fields),safe=metadataValueSafe(row.value),complex=typeof row.value==='object'&&row.value!==null;
      const encodedInteger=metadataHasEncodedInteger(row.value);
      return <div key={JSON.stringify(row.path)+index} className="metadata-value-row"><dt title={row.path.join(' → ')}>{copyable?<button className="metadata-name-copy" onClick={()=>copy(row,'key',field)} aria-label={`Copy setting name ${row.label || row.key}`} title="Click to copy name">{row.label || row.key}</button>:row.label || row.key}</dt><dd>
        {copyable?<button className="metadata-value-copy" disabled={!safe} onClick={()=>copy(row,'text',field)} aria-label={`Copy setting value ${row.label || row.key}`} title={`Click to copy value: ${metadataValueText(row.value)}`}>{complex?JSON.stringify(row.value):metadataValueText(row.value)}</button>:complex?<details className="metadata-complex-value"><summary>{Array.isArray(row.value)?`${row.value.length} items`:`${Object.keys(row.value).length} fields`}{!safe&&' · precision warning'}</summary><pre>{metadataValueText(row.value)}</pre></details>:<span className="metadata-scalar">{metadataValueText(row.value)}</span>}
        {!safe&&row.value!==undefined&&<span className="metadata-precision-warning">This value cannot be copied exactly from the browser.</span>}
        {copyable&&encodedInteger&&<span className="metadata-precision-warning">Large integer encoded as text.</span>}
      </dd></div>;
    })}</dl>{rows.length>limit&&<button className="metadata-show-more" onClick={()=>setLimit(value=>value+80)}>Show next {Math.min(80,rows.length-limit)} fields</button>}
  </section>;
}
