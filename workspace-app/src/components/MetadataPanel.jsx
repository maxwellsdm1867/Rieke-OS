import {useMemo,useState} from 'react';
import {ChevronDown,PanelRightClose,Search,X} from 'lucide-react';
import {Metadata} from './Common.jsx';
import {metadataRows,registeredMetadataField} from './metadataValues.js';
import {groupingFieldRank} from '../treeFieldPresentation.js';
import './MetadataPanel.css';
import {matchesMetadataSearch,parseMetadataSearch} from '../metadataSearch.js';

const defined=object=>Object.fromEntries(Object.entries(object).filter(([,value])=>value!==undefined));
function withLabel(rows,prefix){return rows.map(row=>({...row,label:`${prefix}${row.label}`}));}
function PanelSection({section,query,fields,initialOpen=false}){
  const [open,setOpen]=useState(initialOpen);
  const shown=query?section.rows.filter(row=>matchesMetadataSearch(row,query,fields)):section.rows;
  if(query&&!shown.length)return null;
  return <section className="metadata-panel-section"><button className="metadata-section-toggle" aria-expanded={open||!!query} onClick={()=>setOpen(value=>!value)}><ChevronDown size={14} className={open||query?'expanded':''}/><span>{section.title}</span><small>{shown.length}</small></button>{(open||query)&&<Metadata title={null} rows={shown} fields={fields} copyable compact/>}</section>;
}
export default function MetadataPanel({epoch,catalog,onClose,context,connections,tags,selectionCell=null,selectedEpochs=[],onClearSelection}){
  const [tab,setTab]=useState('settings');
  const [search,setSearch]=useState(''),query=search.trim(),parsedSearch=parseMetadataSearch(query);
  const sections=useMemo(()=>{
    if(!epoch)return [];
    const identity=defined(Object.fromEntries(['epoch_uuid','cell_uuid','group_uuid','block_uuid','protocol_name','start_time','date','epoch_number','duration_seconds','cell_label','cell_type','group_label','block_start_time','block_end_time'].map(key=>[key,epoch[key]])));
    const fields=catalog?.data?.fields || [];
    const parameterRows=metadataRows(epoch.parameters,['parameters']).sort((a,b)=>{const left=registeredMetadataField(a.path,fields)||{},right=registeredMetadataField(b.path,fields)||{};return groupingFieldRank(left)-groupingFieldRank(right)||(left.grouping_priority??999)-(right.grouping_priority??999);});
    const technical=row=>registeredMetadataField(row.path,fields)?.grouping_role==='technical';
    const source=epoch.source_reference || defined({filename:epoch.source_filename,sha256:epoch.source_sha256,path:epoch.source_path});
    return [
      {id:'parameters',title:'Protocol settings',rows:parameterRows.filter(row=>!technical(row))},
      ...(parameterRows.some(technical)?[{id:'technical',title:'Acquisition details',rows:parameterRows.filter(technical)}]:[]),
      {id:'epoch',title:'Epoch',rows:[...metadataRows(identity),...withLabel(metadataRows(epoch.properties,['properties']),'properties.'),...withLabel(metadataRows(epoch.attributes,['attributes']),'attributes.'),...withLabel(metadataRows(epoch.metadata?.epoch,['metadata','epoch']),'source.')]},
      ...['cell','group','block','experiment'].filter(level=>epoch.metadata?.[level]).map(level=>({id:level,title:{cell:'Cell',group:'Epoch group',block:'Epoch block',experiment:'Experiment'}[level],rows:metadataRows(epoch.metadata[level],['metadata',level])})),
      {id:'source',title:'Source & provenance',rows:[...metadataRows(source,['source_reference']),...withLabel(metadataRows(epoch.catalog_ref,['catalog_ref']),'catalog.'),...metadataRows(defined({streams:epoch.streams,exports:epoch.exports}),[])]},
    ];
  },[epoch,catalog?.data]);
  const total=sections.reduce((sum,section)=>sum+section.rows.length,0);
  const visibleSections=tab==='settings'?sections.filter(section=>['parameters','technical'].includes(section.id)):sections;
  const matched=visibleSections.reduce((sum,section)=>sum+section.rows.filter(row=>matchesMetadataSearch(row,parsedSearch,catalog?.data?.fields || [])).length,0);
  if(selectionCell||selectedEpochs.length>0)return <aside id="epoch-metadata-sidebar" className="inspection-metadata" aria-label="Selection details">
    <header className="metadata-panel-header"><div><h2>{selectionCell?'Cell details':`${selectedEpochs.length} epochs`}</h2><span>{selectionCell?`${selectionCell.date} · ${selectionCell.label||selectionCell.cell_label}`:'Multiple selection'}</span></div><button onClick={onClose} aria-label="Hide metadata sidebar"><PanelRightClose size={17}/></button></header>
    {tags}
    <div className="metadata-panel-scroll">{selectionCell?<><dl className="metadata-key-facts"><div><dt>Cell type</dt><dd>{selectionCell.cell_type||'Not recorded'}</dd></div><div><dt>Matching epochs</dt><dd>{selectionCell.epochs}</dd></div></dl><Metadata title="Cell metadata" data={{cell_uuid:selectionCell.cell_uuid,...epoch?.metadata?.cell}} compact copyable/></>:<><p className="metadata-panel-note">Select an epoch to return to its individual details.</p><button onClick={onClearSelection}>Clear selection</button></>}</div>
  </aside>;
  return <aside id="epoch-metadata-sidebar" className="inspection-metadata" aria-label="Epoch metadata sidebar"><header className="metadata-panel-header"><div><h2>Epoch details</h2><span>{epoch?`${epoch.date} · ${epoch.cell_label}`:'Select an epoch'}</span></div><button onClick={onClose} aria-label="Hide metadata sidebar" title="Hide metadata sidebar"><PanelRightClose size={17}/></button></header>
    {epoch&&tags}
    <nav className="metadata-view-tabs" aria-label="Epoch detail views">{[['settings','Settings'],['summary','Summary'],['fields','All fields'],['links','Links']].map(([key,label])=><button key={key} className={tab===key?'active':''} aria-pressed={tab===key} onClick={()=>{setTab(key);setSearch('');}}>{label}</button>)}</nav>
    <label className="metadata-panel-search"><Search size={15}/><input value={search} onChange={event=>{setSearch(event.target.value);if(event.target.value.trim()&&tab!=='settings')setTab('fields');}} aria-label="Search focused epoch metadata" maxLength={512} placeholder={tab==='settings'?'Search settings or values…':'Field, value, or field = value'}/>{search&&<button onClick={()=>setSearch('')} aria-label="Clear metadata search"><X size={13}/></button>}</label>
    <div className="metadata-panel-scroll">{epoch?<>{tab==='summary'&&!query&&<><dl className="metadata-key-facts"><div><dt>Epoch in block</dt><dd>{epoch.epoch_number??'—'}</dd></div><div><dt>Recorded at</dt><dd>{epoch.start_time?.split(/[T ]/)[1]?.slice(0,8)||'—'}</dd></div><div><dt>Duration</dt><dd>{Number.isFinite(epoch.duration_seconds)?`${epoch.duration_seconds.toFixed(2)} s`:'—'}</dd></div><div><dt>Cell type</dt><dd>{epoch.cell_type||'Not recorded'}</dd></div></dl>{context}<button className="metadata-all-fields" onClick={()=>setTab('fields')}>Browse all {total} recorded fields</button></>}{tab==='links'&&!query&&connections}{catalog?.error&&<p className="metadata-panel-note">Predicate field catalog unavailable. Raw key/value copying is still available.</p>}{parsedSearch.error&&<p className="metadata-panel-note" role="alert">{parsedSearch.error}</p>}{query&&<p className="metadata-panel-note">{matched} matching {matched===1?'field':'fields'}</p>}{(tab==='settings'||tab==='fields'||query)&&visibleSections.map(section=><PanelSection key={section.id} section={section} query={query} fields={catalog?.data?.fields || []} initialOpen={tab==='settings'||section.id==='parameters'}/>)}{tab==='settings'&&<p className="metadata-panel-note">Click a name or value to copy.</p>}{tab==='settings'&&!visibleSections.some(section=>section.rows.length)&&<p className="metadata-panel-note">No protocol settings were recorded for this epoch.</p>}{tab==='fields'&&!query&&<p className="metadata-panel-note">Click a name or value to copy. Large source integers may be encoded as text.</p>}</>:<p className="metadata-panel-note">Select an epoch to inspect its recorded metadata.</p>}</div>
  </aside>;
}
