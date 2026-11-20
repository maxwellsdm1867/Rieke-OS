import {useState} from 'react';
import {useResource} from '../../api.js';

// Keep physical records, including large acquisition arrays, off ordinary browsing requests.
export default function H5Attributes({source,epoch=null,revision=0}){
  const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[offset,setOffset]=useState(0);
  const [selected,setSelected]=useState(null);
  const params=new URLSearchParams({q:query,offset:String(offset),limit:'40'});
  if(epoch)params.set('epoch_uuid',epoch);
  const root='/h5-attributes/'+encodeURIComponent(source);
  const page=useResource(open?root+'?'+params:null,revision,100);
  const record=new URLSearchParams();
  if(epoch)record.set('epoch_uuid',epoch);
  if(selected){record.set('record',String(selected.id));record.set('inventory',selected.inventory);}
  const exact=useResource(open&&selected?root+'?'+record:null,revision);
  const title=epoch?'Recorded H5 attributes for this epoch':'Recorded H5 attributes for this recording';
  return <section className="metadata-panel-section"><button type="button" className="metadata-section-toggle"
    aria-expanded={open} onClick={()=>{setOpen(!open);setSelected(null);}}>{title}</button>
    {open&&<div className="h5-attribute-browser">
      <input type="search" aria-label="Search recorded H5 attributes" placeholder="Search names, paths or recorded values"
        maxLength={512} value={query} onChange={event=>{setQuery(event.target.value);setOffset(0);setSelected(null);}}/>
      {page.loading?<p role="status">Reading recorded attributes…</p>:page.error?<p role="alert">{page.error} <button onClick={page.reload}>Retry</button></p>:page.data&&<>
        <p>{page.data.total} matching {page.data.total===1?'attribute':'attributes'}</p>
        <dl className="metadata-table">{page.data.records.map(row=><div key={row.record_id}><dt>{row.label}</dt><dd>
          <small>{row.object_path} · {row.dtype}{row.shape?.length?' ['+row.shape.join(' × ')+']':''}</small>
          <div>{row.value_preview}{row.value_truncated?'…':''}</div>
          <button type="button" onClick={()=>setSelected({id:row.record_id,inventory:page.data.inventory})}>Inspect exact value</button>
          {selected?.id===row.record_id&&(exact.error?<p role="alert">{exact.error} <button onClick={exact.reload}>Retry</button></p>:exact.loading?<p role="status">Loading value…</p>:exact.data&&<details open><summary>Exact recorded JSON</summary>
            <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'18em',overflow:'auto'}}>{exact.data.value_json}</pre>
            {exact.data.value_sha256&&<p>Exact value signature <code>{exact.data.value_sha256}</code></p>}
          </details>)}
        </dd></div>)}</dl>
        {offset>0&&<button onClick={()=>{setOffset(Math.max(0,offset-40));setSelected(null);}}>Previous attributes</button>}
        {page.data.has_more&&<button onClick={()=>{setOffset(offset+40);setSelected(null);}}>Next attributes</button>}
      </>}
    </div>}
  </section>;
}
