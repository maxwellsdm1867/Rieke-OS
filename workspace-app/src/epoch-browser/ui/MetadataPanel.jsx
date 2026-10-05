import {memo,useMemo,useState} from 'react';
import {ChevronDown,PanelRightClose,Search,X} from 'lucide-react';
import {Metadata} from '../../components/Common.jsx';
import {metadataRows,registeredMetadataField} from '../../components/metadataValues.js';
import {groupingFieldRank} from '../../tree-browser/treeFieldPresentation.js';
import './MetadataPanel.css';
import {matchesMetadataSearch,parseMetadataSearch} from '../../search-activation/metadataSearch.js';

const defined=object=>Object.fromEntries(Object.entries(object).filter(([,value])=>value!==undefined));
function withLabel(rows,prefix){return rows.map(row=>({...row,label:`${prefix}${row.label}`}));}
function PanelSection({section,query,fields,initialOpen=false}){
  const [open,setOpen]=useState(initialOpen);
  const shown=query?section.rows.filter(row=>matchesMetadataSearch(row,query,fields)):section.rows;
  if(query&&!shown.length)return null;
  return <section className="metadata-panel-section"><button className="metadata-section-toggle" aria-expanded={open||!!query} onClick={()=>setOpen(value=>!value)}><ChevronDown size={14} className={open||query?'expanded':''}/><span>{section.title}</span><small>{shown.length}</small></button>{(open||query)&&<Metadata title={null} rows={shown} fields={fields} copyable compact/>}</section>;
}
function FieldGroup({category,items,searching,onCopy}){
  const [open,setOpen]=useState(false),[limit,setLimit]=useState(80);
  return <details className="metadata-field-group" open={open||searching} onToggle={event=>setOpen(event.currentTarget.open)}><summary>{category}<small>{items.length}</small></summary>{(open||searching)&&<>{items.slice(0,limit).map(field=><button key={field.id} className="metadata-field-copy" onClick={()=>onCopy(field)} aria-label={`Copy field ID ${field.id}`} title="Copy field ID for filtering or grouping"><span>{field.label||field.id}</span><code>{field.id}</code>{field.type&&<small>{field.type}</small>}</button>)}{items.length>limit&&<button className="metadata-show-more" onClick={()=>setLimit(value=>value+80)}>Show next {Math.min(80,items.length-limit)} fields</button>}</>}</details>;
}
const FieldCatalog=memo(function FieldCatalog({catalog,query=''}){
  const [feedback,setFeedback]=useState('');
  const needle=query.trim().toLocaleLowerCase();
  const {fields,groups}=useMemo(()=>{
  const fields=(catalog?.data?.fields||[]).filter(field=>typeof field.id==='string'&&field.id&&(!needle||[field.id,field.label,field.category,field.grouping_role,field.type].some(value=>String(value||'').toLocaleLowerCase().includes(needle))));
  const groups=new Map();
  for(const field of fields){const category=field.category||'Other fields';if(!groups.has(category))groups.set(category,[]);groups.get(category).push(field);}
  return {fields,groups};
  },[catalog?.data,needle]);
  async function copy(field){try{if(!navigator?.clipboard?.writeText)throw Error('Clipboard unavailable. Select and copy the field ID.');await navigator.clipboard.writeText(field.id);setFeedback(`Copied field ID: ${field.id}`);}catch(error){setFeedback(error.message);}}
  return <section className="metadata-field-catalog" aria-label="Available metadata fields"><h3>Available fields</h3><p className="metadata-panel-note">Registered fields for filtering and grouping. Values for this epoch load on request.</p>
    {catalog?.scoped&&!catalog.data&&!catalog.loading&&!catalog.error&&<p className="metadata-panel-note">Field names have not been requested. <button onClick={catalog.load}>Load field names</button></p>}
    {catalog?.loading&&<p role="status" className="metadata-panel-note">Loading fields… {catalog.cancel&&<button onClick={catalog.cancel}>Cancel fields</button>}</p>}
    {catalog?.error&&<p role="alert" className="metadata-panel-note">Fields could not be loaded. {catalog.error} {catalog.reload&&<button onClick={catalog.reload}>Retry fields</button>}</p>}
    {feedback&&<p role="status" className="metadata-panel-note">{feedback}</p>}
    {[...groups].map(([category,items])=><FieldGroup key={category} category={category} items={items} searching={!!needle} onCopy={copy}/>)}
    {!(catalog?.scoped&&!catalog.data)&&!catalog?.loading&&!catalog?.error&&!fields.length&&<p className="metadata-panel-note">{needle?'No fields match this search.':'No registered fields are available.'}</p>}
  </section>;
},(before,after)=>before.query===after.query&&before.catalog?.data===after.catalog?.data&&before.catalog?.loading===after.catalog?.loading&&before.catalog?.error===after.catalog?.error&&before.catalog?.reload===after.catalog?.reload&&before.catalog?.scoped===after.catalog?.scoped&&before.catalog?.load===after.catalog?.load&&before.catalog?.cancel===after.catalog?.cancel);
export default function MetadataPanel({epoch,catalog,onClose,context,connections,tags,selectionCell=null,selectedEpochs=[],onClearSelection,loadingPolicy=null}){
  const [tab,setTab]=useState('settings');
  const [search,setSearch]=useState(''),query=search.trim(),parsedSearch=parseMetadataSearch(query);
  const valueEpoch=loadingPolicy?loadingPolicy.values.data:epoch;
  const fieldsOnly=!!loadingPolicy&&!valueEpoch;
  const sections=useMemo(()=>{
    if(!valueEpoch)return [];
    const identity=defined(Object.fromEntries(['epoch_uuid','cell_uuid','group_uuid','block_uuid','protocol_name','start_time','date','epoch_number','duration_seconds','cell_label','cell_type','group_label','block_start_time','block_end_time'].map(key=>[key,valueEpoch[key]])));
    const fields=catalog?.data?.fields || [];
    const parameterRows=metadataRows(valueEpoch.parameters,['parameters']).sort((a,b)=>{const left=registeredMetadataField(a.path,fields)||{},right=registeredMetadataField(b.path,fields)||{};return groupingFieldRank(left)-groupingFieldRank(right)||(left.grouping_priority??999)-(right.grouping_priority??999);});
    const technical=row=>registeredMetadataField(row.path,fields)?.grouping_role==='technical';
    const source=valueEpoch.source_reference || defined({filename:valueEpoch.source_filename,sha256:valueEpoch.source_sha256,path:valueEpoch.source_path});
    return [
      {id:'parameters',title:'Protocol settings',rows:parameterRows.filter(row=>!technical(row))},
      ...(parameterRows.some(technical)?[{id:'technical',title:'Acquisition details',rows:parameterRows.filter(technical)}]:[]),
      {id:'epoch',title:'Epoch',rows:[...metadataRows(identity),...withLabel(metadataRows(valueEpoch.properties,['properties']),'properties.'),...withLabel(metadataRows(valueEpoch.attributes,['attributes']),'attributes.'),...withLabel(metadataRows(valueEpoch.metadata?.epoch,['metadata','epoch']),'source.')]},
      ...['cell','group','block','experiment'].filter(level=>valueEpoch.metadata?.[level]).map(level=>({id:level,title:{cell:'Cell',group:'Epoch group',block:'Epoch block',experiment:'Experiment'}[level],rows:metadataRows(valueEpoch.metadata[level],['metadata',level])})),
      {id:'source',title:'Source & provenance',rows:[...metadataRows(source,['source_reference']),...withLabel(metadataRows(valueEpoch.catalog_ref,['catalog_ref']),'catalog.'),...metadataRows(defined({streams:valueEpoch.streams,exports:valueEpoch.exports}),[])]},
    ];
  },[valueEpoch,catalog?.data]);
  const total=sections.reduce((sum,section)=>sum+section.rows.length,0);
  const visibleSections=tab==='settings'?sections.filter(section=>['parameters','technical'].includes(section.id)):sections;
  const matched=visibleSections.reduce((sum,section)=>sum+section.rows.filter(row=>matchesMetadataSearch(row,parsedSearch,catalog?.data?.fields || [])).length,0);
  const controls=loadingPolicy&&<div className="metadata-loading-controls"><div><label className="metadata-live-switch"><input type="checkbox" role="switch" aria-label="Live metadata" checked={loadingPolicy.live} onChange={event=>{setSearch('');loadingPolicy.onLiveChange(event.target.checked);}}/><span className="metadata-switch-track" aria-hidden="true"/><span>Live metadata</span><strong className="metadata-switch-status">{loadingPolicy.live?'On':'Off'}</strong></label><button disabled={!loadingPolicy.canLoad||loadingPolicy.values.loading&&loadingPolicy.requested} onClick={loadingPolicy.load}>{loadingPolicy.requested&&loadingPolicy.values.loading?'Loading…':loadingPolicy.values.error?'Retry values':valueEpoch?'Refresh values':'Load values'}</button></div>
    <p>{loadingPolicy.live?'Values follow the selected epoch.':'Trace and tags stay live. Values load only when requested.'}</p>
    {loadingPolicy.requested&&loadingPolicy.values.error&&<p role="alert">Metadata values could not be loaded: {loadingPolicy.values.error}</p>}
  </div>;
  if(selectionCell||selectedEpochs.length>0)return <aside id="epoch-metadata-sidebar" className="inspection-metadata" aria-label="Selection details">
    <header className="metadata-panel-header"><div><h2>{selectionCell?'Cell details':`${selectedEpochs.length} epochs`}</h2><span>{selectionCell?`${selectionCell.date} · ${selectionCell.label||selectionCell.cell_label}`:'Multiple selection'}</span></div><button onClick={onClose} aria-label="Hide metadata sidebar"><PanelRightClose size={17}/></button></header>
    {controls}{tags}
    <div className="metadata-panel-scroll">{selectionCell?<><dl className="metadata-key-facts"><div><dt>Cell type</dt><dd>{selectionCell.cell_type||'Not recorded'}</dd></div><div><dt>Matching epochs</dt><dd>{selectionCell.epochs}</dd></div></dl>{fieldsOnly?<FieldCatalog catalog={catalog} query={query}/>:<Metadata title="Cell metadata" data={{cell_uuid:selectionCell.cell_uuid,...valueEpoch?.metadata?.cell}} compact copyable/>}</>:<><p className="metadata-panel-note">Select an epoch to return to its individual details.</p><button onClick={onClearSelection}>Clear selection</button></>}</div>
  </aside>;
  return <aside id="epoch-metadata-sidebar" className="inspection-metadata" aria-label="Epoch metadata sidebar"><header className="metadata-panel-header"><div><h2>Epoch details</h2><span>{epoch?`${epoch.date} · ${epoch.cell_label}`:'Select an epoch'}</span></div><button onClick={onClose} aria-label="Hide metadata sidebar" title="Hide metadata sidebar"><PanelRightClose size={17}/></button></header>
    {controls}{epoch&&tags}
    {!fieldsOnly&&<nav className="metadata-view-tabs" aria-label="Epoch detail views">{[['settings','Settings'],['summary','Summary'],['fields','All fields'],['links','Links']].map(([key,label])=><button key={key} className={tab===key?'active':''} aria-pressed={tab===key} onClick={()=>{setTab(key);setSearch('');}}>{label}</button>)}</nav>}
    <label className="metadata-panel-search"><Search size={15}/><input value={search} onChange={event=>{setSearch(event.target.value);if(event.target.value.trim()&&tab!=='settings')setTab('fields');}} aria-label={fieldsOnly?"Search metadata fields":"Search focused epoch metadata"} maxLength={512} placeholder={fieldsOnly?'Search field names or IDs…':tab==='settings'?'Search settings or values…':'Field, value, or field = value'}/>{search&&<button onClick={()=>setSearch('')} aria-label="Clear metadata search"><X size={13}/></button>}</label>
    <div className="metadata-panel-scroll">{fieldsOnly?<FieldCatalog catalog={catalog} query={query}/>:epoch?<>{tab==='summary'&&!query&&<><dl className="metadata-key-facts"><div><dt>Epoch in block</dt><dd>{epoch.epoch_number??'—'}</dd></div><div><dt>Recorded at</dt><dd>{epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'—'}</dd></div><div><dt>Duration</dt><dd>{Number.isFinite(epoch.duration_seconds)?`${epoch.duration_seconds.toFixed(2)} s`:'—'}</dd></div><div><dt>Cell type</dt><dd>{epoch.cell_type||'Not recorded'}</dd></div></dl>{context}<button className="metadata-all-fields" onClick={()=>setTab('fields')}>Browse all {total} recorded fields</button></>}{tab==='links'&&!query&&connections}{catalog?.error&&<p className="metadata-panel-note">Predicate field catalog unavailable. Raw key/value copying is still available.</p>}{parsedSearch.error&&<p className="metadata-panel-note" role="alert">{parsedSearch.error}</p>}{query&&<p className="metadata-panel-note">{matched} matching {matched===1?'field':'fields'}</p>}{(tab==='settings'||tab==='fields'||query)&&visibleSections.map(section=><PanelSection key={section.id} section={section} query={query} fields={catalog?.data?.fields || []} initialOpen={tab==='settings'||section.id==='parameters'}/>)}{tab==='settings'&&<p className="metadata-panel-note">Click a name or value to copy.</p>}{tab==='settings'&&!visibleSections.some(section=>section.rows.length)&&<p className="metadata-panel-note">No protocol settings were recorded for this epoch.</p>}{tab==='fields'&&!query&&<p className="metadata-panel-note">Click a name or value to copy. Large source integers may be encoded as text.</p>}</>:<p className="metadata-panel-note">Select an epoch to inspect its recorded metadata.</p>}</div>
  </aside>;
}
