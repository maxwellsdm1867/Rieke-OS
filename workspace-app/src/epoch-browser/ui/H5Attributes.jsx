import {useState} from 'react';
import {useSemanticReset} from '../../useSemanticReset.js';
import {useResource} from '../../api.js';
import {h5AttributeField} from '../../components/metadataValues.js';
import './H5Attributes.css';

function groupsOnPage(records){
  const groups=new Map();
  for(const row of records){
    const field=h5AttributeField(row.field_id);
    const key=field?.parentId||row.object_path;
    if(!groups.has(key))groups.set(key,{key,header:field?.header||row.object_path,rows:[]});
    groups.get(key).rows.push({row,name:field?.name||row.attribute_name||row.label});
  }
  return [...groups.values()];
}

// Keep physical records, including large acquisition arrays, off ordinary browsing requests.
export default function H5Attributes({source,epoch=null,revision=0,search=''}){
  const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[offset,setOffset]=useState(0);
  const [selected,setSelected]=useState(null);
  useSemanticReset(search,()=>{setOffset(0);setSelected(null);});
  const expanded=open||!!search;
  const params=new URLSearchParams({q:search||query,offset:String(offset),limit:'40'});
  if(epoch)params.set('epoch_uuid',epoch);
  const root='/h5-attributes/'+encodeURIComponent(source);
  const page=useResource(expanded?root+'?'+params:null,revision,100);
  const record=new URLSearchParams();
  if(epoch)record.set('epoch_uuid',epoch);
  if(selected){record.set('record',String(selected.id));record.set('inventory',selected.inventory);}
  const exact=useResource(expanded&&selected?root+'?'+record:null,revision);
  const title=epoch?'Recorded H5 attributes for this epoch':'Recorded H5 attributes for this recording';
  return <section className="metadata-panel-section">{search?<h3 className="metadata-section-toggle">{title}</h3>:<button type="button" className="metadata-section-toggle"
    aria-expanded={open} onClick={()=>{setOpen(!open);setSelected(null);}}>{title}</button>}
    {expanded&&<div className="h5-attribute-browser">
      {!search&&<input type="search" aria-label="Search recorded H5 attributes" placeholder="Search names, paths or recorded values"
        maxLength={512} value={query} onChange={event=>{setQuery(event.target.value);setOffset(0);setSelected(null);}}/>}
      {page.loading?<p role="status">Reading recorded attributes…</p>:page.error?<p role="alert">{page.error} <button onClick={page.reload}>Retry</button></p>:page.data&&<>
        <p>{page.data.total} matching {page.data.total===1?'attribute':'attributes'}</p>
        {groupsOnPage(page.data.records).map(({key,header,rows})=><section key={key} className="h5-field-group" aria-label={header}>
          <h4>{header}</h4><dl>{rows.map(({row,name})=><div key={row.record_id}><dt title={row.field_id}>{name}</dt><dd>
          <small>{row.dtype}{row.shape?.length?' ['+row.shape.join(' × ')+']':''}</small>
          {!epoch&&<small>{row.object_path}</small>}
          <div>{row.value_preview}{row.value_truncated?'…':''}</div>
          <button type="button" onClick={()=>setSelected({id:row.record_id,inventory:page.data.inventory})}>Inspect exact value</button>
          {selected?.id===row.record_id&&(exact.error?<p role="alert">{exact.error} <button onClick={exact.reload}>Retry</button></p>:exact.loading?<p role="status">Loading value…</p>:exact.data&&<details open><summary>Exact recorded JSON</summary>
            {epoch&&<small>{row.object_path}</small>}
            <pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'18em',overflow:'auto'}}>{exact.data.value_json}</pre>
            {exact.data.value_sha256&&<p>Exact value signature <code>{exact.data.value_sha256}</code></p>}
          </details>)}
        </dd></div>)}</dl></section>)}
        {offset>0&&<button onClick={()=>{setOffset(Math.max(0,offset-40));setSelected(null);}}>Previous attributes</button>}
        {page.data.has_more&&<button onClick={()=>{setOffset(offset+40);setSelected(null);}}>Next attributes</button>}
      </>}
    </div>}
  </section>;
}
