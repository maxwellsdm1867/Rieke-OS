import {cellTypeQCLabel,recordingRigLabel} from '../cellTypes.js';
import CellTypeIcon from '../../components/CellTypeIcon.jsx';
import {useEffect,useMemo,useRef,useState} from 'react';
import {Activity,FlaskConical,Monitor,ArrowLeft,ArrowUpRight,Check,Copy,Info,Layers,RefreshCw,Thermometer,Tag} from 'lucide-react';
import {api,humanize,number,useResource} from "../../api.js";
import {Badge,Empty,Status} from "../../components/Common.jsx";
import Trace from "../../traces/ui/TraceViewer.jsx";
import StableContent from "../../components/StableContent.jsx";
import MetadataPanel from "../../epoch-browser/ui/MetadataPanel.jsx";
import AnnotationTags from "../../annotations/ui/AnnotationTags.jsx";
import TagExchangeControls from "../../annotations/ui/TagExchangeControls.jsx";
import {datedCellLabel,recordingDate} from "../../recording-import/recordingIdentity.js";
import {epochResourceCache} from '../../resourceCache.js';
import {useRetainedView} from '../../retainedWorkspaceViews.js';
import {tagStore} from "../../annotations/tagStore.js";
import {useDeferredTagVersion} from "../../annotations/useTagStore.js";
import './CellQC.css';

const numeric=value=>typeof value==='number'&&Number.isFinite(value);
const display=value=>!numeric(value)?'—':value!==0&&(Math.abs(value)<0.001||Math.abs(value)>=1e6)?value.toExponential(3):new Intl.NumberFormat(undefined,{maximumSignificantDigits:5}).format(value);
const temperatureUnit=units=>{
  const key=String(units||'').trim().toLowerCase().replace(/[°\s_-]/g,'');
  // bathTemperature is Celsius by acquisition convention when units are omitted.
  if(!key)return '°C';
  if(['c','degc','celsius','degreecelsius','degreescelsius'].includes(key))return '°C';
  if(['f','degf','fahrenheit','degreefahrenheit','degreesfahrenheit'].includes(key))return '°F';
  if(['k','kelvin'].includes(key))return 'K';
  return units||null;
};
const temperatureLow=(value,units)=>{
  const unit=temperatureUnit(units);
  return numeric(value)&&(unit==='°C'?value<25:unit==='°F'?value<77:unit==='K'?value<298.15:false);
};
function TemperatureValue({value,units,missing=false}){
  const unit=temperatureUnit(units),unmeasured=missing||!numeric(value);
  return <span className={unmeasured||!unit||temperatureLow(value,unit)?'qc-temperature-warning':undefined} title={unmeasured?'No reading available':!unit?`Recorded value: ${display(value)}; unit not recorded`:undefined}>{unmeasured?'Unknown':!unit?'Unknown':`${display(value)} ${unit}`}</span>;
}
function TemperatureSummary({temperature}){
  const range=temperature?.range,unit=temperatureUnit(temperature?.units),count=temperature?.recorded_count||0;
  const missing=temperature?.missing_count||0;
  const warning=!count||missing>0||(range&&temperatureLow(range.min,unit));
  const label=!count?'Unknown':range&&unit?`${display(range.min)}${range.max!==range.min?` – ${display(range.max)}`:''} ${unit}`:'See trials';
  return <strong className={warning?'qc-temperature-warning':undefined}>{label}</strong>;
}
function solutionText(value){
  if(value==null||value===false)return '';
  if(Array.isArray(value))return value.map(solutionText).filter(Boolean).join(', ');
  if(typeof value==='string'){
    const text=value.trim();
    if(text.startsWith('[')||text.startsWith('{')){try{return solutionText(JSON.parse(text));}catch{/* Retain non-JSON recorded descriptions verbatim. */}}
    if(/^(n\/?a|not applicable)$/i.test(text))return 'N/A';
    return /^(none|no additions?|not recorded|null)$/i.test(text)?'':text;
  }
  if(typeof value==='object'){
    if('quantity' in value)return value.quantity==null?'':`${solutionText(value.quantity)}${value.units?` ${value.units}`:''}`;
    return Object.entries(value).map(([key,item])=>{const text=solutionText(item);return text?`${key}: ${text}`:'';}).filter(Boolean).join(', ');
  }
  return String(value);
}
function conditionSummary(groups=[]){
  const summarize=(field,label)=>({label,
    values:[...new Set(groups.map(row=>solutionText(row[field])).filter(Boolean))],
    missing:groups.filter(row=>!solutionText(row[field])).length,
    provenance:groups.map(row=>`${row.group_label||row.group_uuid}: ${solutionText(row[field])||'Not recorded'}`).join('\n')});
  return {pipette:summarize('pipette_solution','Pipette solution'),
    additions:[summarize('internal_additions','Internal additions'),summarize('external_additions','External additions')].filter(item=>item.values.length)};
}
function SolutionMetric({item}){
  return <article className="qc-solution" aria-label={item.label} title={item.provenance}><span><FlaskConical size={16}/>{item.label}</span><strong>{item.values.join(' / ')||'Not recorded'}</strong><small>{item.values.length&&item.missing?'Not recorded in some groups':'Recorded group metadata'}</small></article>;
}
const flagged=flags=>Array.isArray(flags)?flags:Object.entries(flags||{}).filter(([,value])=>value===true).map(([key])=>key);
const parameterNames=['currentSpotSize','contrast','spotContrast','amplitude','currentAmplitude','frequencyCutoff'];
const parameterLabel=key=>({currentSpotSize:'Spot size',contrast:'Contrast',spotContrast:'Spot contrast',currentAmplitude:'Current amplitude',amplitude:'Amplitude',frequencyCutoff:'Frequency cutoff'}[key]||humanize(key));
function conditionLabel(row){const values=parameterNames.filter(key=>row.parameters?.[key]!==undefined).map(key=>`${parameterLabel(key)}: ${JSON.stringify(row.parameters[key])}`);return values.join(' · ') || humanize(row.protocol_name?.split('.').at(-1)) || 'Recorded trial';}

function Trend({points=[],valueKey='value',label,units}){
  const data=points.filter(p=>numeric(p[valueKey]));
  if(!data.length)return <p className="qc-muted">No recorded values.</p>;
  const min=Math.min(...data.map(p=>p[valueKey])),max=Math.max(...data.map(p=>p[valueKey]));
  const pad=Math.max((max-min)*.12,Math.max(Math.abs(min),Math.abs(max))*.001,Number.EPSILON),low=min-pad,high=max+pad;
  const xy=data.map((p,i)=>[58+(data.length===1?.5:i/(data.length-1))*470,20+(high-p[valueKey])/(high-low)*104]);
  return <svg viewBox="0 0 550 166" className="qc-trend" role="img" aria-label={`${label}. ${data.length} observations, range ${display(min)} to ${display(max)} ${units||''}.`}>
    {[low,(low+high)/2,high].map(v=><g key={v}><line x1="58" x2="528" y1={20+(high-v)/(high-low)*104} y2={20+(high-v)/(high-low)*104} stroke="var(--plot-grid)"/><text x="49" y={24+(high-v)/(high-low)*104} textAnchor="end">{display(v)}</text></g>)}
    <polyline points={xy.map(p=>p.join(',')).join(' ')} fill="none" stroke="var(--plot-trace)" strokeWidth="1.7"/>
    {xy.map(([x,y],i)=><circle key={i} cx={x} cy={y} r="2.6" fill="var(--plot-trace)"><title>{data[i].start_time} · {display(data[i][valueKey])} {units||''}</title></circle>)}
    <text x="58" y="147">First observation</text><text x="528" y="147" textAnchor="end">Last shown observation</text>
    <text transform="translate(13,74) rotate(-90)" textAnchor="middle">{units||'Recorded value'}</text>
  </svg>;
}

function TemperaturePanel({cellUuid,revision,opened,onToggle,temperature,groupLabels=[]}){
  const [offset,setOffset]=useState(0),[selected,setSelected]=useState(null);
  const path=opened?`/cells/${cellUuid}/qc/temperature?offset=${offset}&limit=50`:null;
  const result=useResource(path,revision);
  const data=result.path===path?result.data:null;
  const epoch=useResource(opened&&selected?`/epochs/${selected}`:null,revision);
  const catalog=useResource(opened&&selected?'/explore/predicate-fields':null,revision);
  const source=epoch.data?.epoch_uuid===selected&&epoch.data?.cell_uuid===cellUuid?epoch.data:null;
  if(!opened)return null;
  return <section id={`qc-temperature-${cellUuid}`} className="qc-temperature" aria-label="Temperature and recording conditions"><header><h2><Thermometer size={16}/> Temperature & recording conditions</h2><button onClick={onToggle}>Close temperature details</button></header>
    <p className="qc-muted">Recording conditions: {groupLabels.length?groupLabels.join(' · '):'Not recorded'}</p>
    {temperature?.range?<Trend points={temperature.points} label="Recorded bath temperature" units={temperatureUnit(temperature.units)}/>:<p className="qc-muted">No comparable temperature range. Recorded values and units are listed below.</p>}
    <h3>Readings by epoch</h3>
    <Status {...result} retry={result.reload}>{data&&<><div className="qc-scroll-table"><table><thead><tr><th>Order / epoch</th><th>Recording time</th><th>Value</th><th>Units</th><th>Source epoch</th></tr></thead><tbody>{data.observations.map(row=><tr key={row.epoch_uuid}><td>{row.recording_order} / {row.epoch_number??'Unrecorded'}</td><td>{row.start_time||'Time not recorded'}</td><td><TemperatureValue value={row.value} units={row.units} missing={row.status!=='recorded'}/></td><td>{row.status==='recorded'?temperatureUnit(row.units):<span className="qc-temperature-warning">No reading available</span>}</td><td><button aria-pressed={selected===row.epoch_uuid} onClick={()=>setSelected(row.epoch_uuid)}>Inspect epoch</button><code>{row.epoch_uuid}</code></td></tr>)}</tbody></table></div><footer className="qc-observation-pages"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><span>{data.total?`${offset+1}–${offset+data.observations.length}`:'0'} of {number(data.total)} epochs</span><button disabled={!data.has_more} onClick={()=>setOffset(offset+50)}>Next</button></footer></>}</Status>
    {selected&&<Status {...epoch} retry={epoch.reload}>{source&&<div className="qc-temperature-source"><h3>Source epoch <code>{selected}</code></h3><Trace epoch={source}/><MetadataPanel epoch={source} catalog={catalog} onClose={()=>setSelected(null)}/></div>}</Status>}
  </section>;
}

function BaselinePanel({cellUuid,definition,revision}){
  const [opened,setOpened]=useState(false),[preparing,setPreparing]=useState(false),[error,setError]=useState('');
  const result=useResource(opened?`/cells/${cellUuid}/qc/block-baselines`:null,revision);
  const data=result.data?.cell_uuid===cellUuid?result.data:null;
  async function prepare(){setPreparing(true);setError('');try{const prepared=await api(`/cells/${cellUuid}/qc/prepare-baselines`,{method:'POST',body:{}});if(prepared.preparation_status==='failed')setError(prepared.reason);result.reload();}catch(error){setError(error.message);}finally{setPreparing(false);}}
  return <section className="qc-baseline"><header><div><h2><Activity size={17}/> Resting voltage supporting measurements</h2><p>Prepared first-epoch block-onset estimates, in recording time.</p></div><button onClick={()=>setOpened(!opened)} aria-expanded={opened}>{opened?'Hide estimates':'View prepared estimates'}</button></header>
    <p className="qc-method-note"><Info size={15}/>{definition?.reason || 'These raw block-onset estimates have not been validated as a resting-voltage curve.'}</p>
    {opened&&<Status {...result} retry={result.reload}>{data&&<>
      <p className="qc-muted">Preparation: {humanize(data?.preparation_status||'not_prepared').replace(/_/g,' ')}. Validated resting-voltage curve: unavailable. {data?.interpolation?.reason}</p>
      {(data?.preparation_status!=='complete'||error)&&<><button disabled={preparing} onClick={prepare}>{preparing?'Preparing supporting voltage…':'Prepare / retry supporting voltage'}</button>{data?.reason&&<p role="status" className="qc-muted">{data.reason}</p>}</>}
      {error&&<p role="alert">{error}</p>}
      {(data?.recordings||[]).map(recording=>{const anchors=(data.anchors||[]).filter(anchor=>anchor.source_sha256===recording.source_sha256);return <div key={recording.source_sha256}><h3>Recording from {recording.start_time}</h3><p className="qc-muted">Source <code>{recording.source_sha256}</code>. {recording.time_basis} Recorded epoch span: {display(recording.duration_seconds)} s.</p>
        <div className="qc-scroll-table"><table><thead><tr><th>Recording time (s)</th><th>Block onset / source</th><th>Raw 1 ms mean (mV)</th><th>Samples</th><th>Measurement flags</th></tr></thead><tbody>{anchors.map(anchor=><tr key={`${anchor.block_uuid}:${anchor.epoch_uuid}`}><td>{numeric(anchor.recording_time_seconds)?display(anchor.recording_time_seconds):'Time unavailable'}</td><td>{anchor.start_time}<br/><small>Epoch <code>{anchor.epoch_uuid}</code><br/>Block <code>{anchor.block_uuid}</code></small></td><td>{display(anchor.mean_mV)}</td><td>{number(anchor.sample_count)}</td><td>{flagged(anchor.flags).length?flagged(anchor.flags).map(v=>humanize(v).replace(/_/g,' ')).join(' · '):'No estimator flags'}</td></tr>)}</tbody></table></div>
        {!anchors.length&&<p className="qc-muted">No eligible voltage anchors in this recording.</p>}
      </div>;})}
      {!(data?.anchors||[]).length&&data?.preparation_status==='complete'&&<Empty title="Supporting voltage unavailable">{data.reason}</Empty>}
      <details className="qc-method"><summary>Method, exclusions & provenance</summary><pre>{JSON.stringify({method:data?.method,anchors:data?.anchors,excluded_blocks:data?.excluded_blocks,interpolation:data?.interpolation,prepared_at:data?.prepared_at},null,2)}</pre></details>
    </>}</Status>}
  </section>;
}

function ConditionSummary({cellUuid,family,epoch,revision,onSelect}){
  const [open,setOpen]=useState(false);
  const resource=useResource(open&&epoch?.block_uuid?`/cells/${cellUuid}/qc/response-summary?family=${family}&block_uuid=${epoch.block_uuid}`:null,revision);
  const data=resource.data?.cell_uuid===cellUuid&&resource.data?.family===family&&resource.path?.includes(`block_uuid=${epoch?.block_uuid}`)?resource.data:null,points=(data?.points||[]).filter(p=>numeric(p.response_mean));
  const units=[...new Set(points.map(p=>p.units))];
  const xField=['currentSpotSize','contrast','spotContrast','currentAmplitude','amplitude'].find(key=>points.length&&points.every(p=>numeric(p.parameters?.[key]))&&new Set(points.map(p=>p.parameters[key])).size>1);
  const xs=points.map((p,i)=>xField?p.parameters[xField]:i+1),ys=points.map(p=>p.response_mean);
  const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),pad=Math.max((ymax-ymin)*.15,Math.max(Math.abs(ymin),Math.abs(ymax))*.001,Number.EPSILON);
  const y=v=>20+(ymax+pad-v)/(ymax-ymin+2*pad)*140,x=v=>65+(xmax===xmin?.5:(v-xmin)/(xmax-xmin))*460;
  if(!['expanding_spots','split_field','single_spot','current_step'].includes(family))return null;
  return <section className="qc-condition-summary"><header><h3>Condition comparison</h3><button onClick={()=>setOpen(!open)} aria-expanded={open}>{open?'Hide comparison':'Compare conditions in this block'}</button></header>{open&&<Status {...resource} retry={resource.reload}>{data&&<>
    {points.length&&units.length===1?<svg viewBox="0 0 560 212" role="img" aria-label={`Recorded stimulus-window mean response by ${xField||'condition order'}, ${points.length} conditions. Includes spikes, not firing rate.`}>
      {[ymin,(ymin+ymax)/2,ymax].filter((v,i,a)=>a.indexOf(v)===i).map(v=><g key={v}><line x1="65" x2="525" y1={y(v)} y2={y(v)} stroke="var(--plot-grid)"/><text x="55" y={y(v)+4} textAnchor="end">{display(v)}</text></g>)}
      {points.map((p,i)=><circle key={p.condition_id} cx={x(xs[i])} cy={y(ys[i])} r="5" fill="var(--plot-trace)"><title>{conditionLabel(p)} · {display(p.response_mean)} {p.units} · {p.used_epoch_count}/{p.epoch_count} trials</title></circle>)}
      {[xmin,xmax].filter((v,i,a)=>a.indexOf(v)===i).map(v=><text key={v} x={x(v)} y="181" textAnchor="middle">{display(v)}</text>)}
      <text x="295" y="204" textAnchor="middle">{xField?`${parameterLabel(xField)} (recorded value)`:'Condition order'}</text><text transform="translate(15,90) rotate(-90)" textAnchor="middle">Mean response ({units[0]})</text>
    </svg>:<p className="qc-muted">{units.length>1?'Different response units cannot share one axis.':'No complete stimulus windows available for this block.'}</p>}
    <p className="qc-muted">Each point uses up to three trials with identical parameters in this block. Raw signal features are retained; this is not a sensitivity or receptive-field estimate.</p>
    <div className="qc-scroll-table"><table><thead><tr><th>Recorded condition</th><th>Mean response</th><th>Trial coverage</th><th/></tr></thead><tbody>{(data.points||[]).map(p=><tr key={p.condition_id}><td>{conditionLabel(p)}</td><td>{display(p.response_mean)} {p.units}</td><td>{p.used_epoch_count} / {p.epoch_count}</td><td>{p.measurements?.[0]&&<button onClick={()=>onSelect(p.measurements[0].epoch_uuid)}>View trial</button>}</td></tr>)}</tbody></table></div>
    {!!data.skipped?.length&&<p className="qc-muted">{number(data.skipped.length)} trial measurements unavailable or beyond this preview’s sample budget.</p>}{data.truncated&&<p className="qc-muted">Showing a bounded subset of conditions.</p>}
    <details className="qc-method"><summary>Method & coverage details</summary><pre>{JSON.stringify({method:data.method,skipped:data.skipped,samples_read:data.samples_read},null,2)}</pre></details>
  </>}</Status>}</section>;
}

export default function CellQC({cellUuid,revision,structureRevision=revision,annotationRevision=revision,onBack,initialEpochUuid,session,onSession,onAnnotationsChanged,onTagFilter}){
  const viewActive=useRetainedView()?.active!==false;
  const [refresh,setRefresh]=useState(0),[tagRefresh,setTagRefresh]=useState(0),[tagFocus,setTagFocus]=useState(0),[temperatureOpen,setTemperatureOpen]=useState(false);
  // Confirmed tags live in the tag store and are shown in place: one write, no
  // reread. Other annotation changes (imports, unverified saves) renew the epoch.
  const tagVersion=useDeferredTagVersion();
  function annotationsChanged(result,confirmed){
    if(onAnnotationsChanged)onAnnotationsChanged(result,confirmed);else if(!confirmed)setTagRefresh(value=>value+1);
  }
  // Samples, QC summaries and recorded metadata do not depend on tags. Only the
  // epoch detail (which carries annotations) and tag controls follow tag edits.
  const qcRevision=`${structureRevision}:${refresh}`,liveRevision=`${annotationRevision}:${refresh}:${tagRefresh}`;
  const result=useResource(`/cells/${cellUuid}/qc?projection=display`,qcRevision,0,{cache:true});
  const data=result.data;
  const [family,setFamily]=useState(session?.family==='other'?'':session?.family||''),[offset,setOffset]=useState(session?.family==='other'?0:session?.offset||0),[selected,setSelected]=useState(session&&Object.hasOwn(session,'selected')?session.selected:(initialEpochUuid??null)),[copied,setCopied]=useState(false),[copyError,setCopyError]=useState(''),[showMetadata,setShowMetadata]=useState(session?.showMetadata||false);
  useEffect(()=>{onSession?.({family,offset,selected,showMetadata});},[family,offset,selected,showMetadata,onSession]);
  const available=(data?.families||[]).filter(item=>item.epoch_count>0);
  // Default-family resolution belongs to the bounded page read, so a first
  // trial can load while the independent cell-wide summary is still pending.
  const anchorEpoch=!family&&initialEpochUuid?(selected||initialEpochUuid):null;
  const rowsPath=`/cells/${cellUuid}/qc/epochs?family=${encodeURIComponent(family||'default')}&offset=${offset}&limit=40${anchorEpoch?`&anchor_epoch_uuid=${encodeURIComponent(anchorEpoch)}`:''}`;
  const rows=useResource(rowsPath,qcRevision,0,{cache:true});
  const active=family || rows.data?.family || (!anchorEpoch?available[0]?.id:null);
  const epochs=rows.path===rowsPath?rows.data?.epochs||[]:[];
  const epochId=selected || epochs[0]?.epoch_uuid;
  const trialList=useRef(null),selectedTrial=useRef(null);
  const epoch=useResource(epochId?`/epochs/${epochId}`:null,liveRevision,0,{cache:true});
  const response=useResource(epochId?`/cells/${cellUuid}/qc/response?epoch_uuid=${epochId}&summary_only=true`:null,qcRevision,0,{cache:true});
  const catalog=useResource(showMetadata?'/explore/predicate-fields':null,qcRevision);
  const temperature=data?.temperature;
  const conditions=conditionSummary(data?.recording_conditions);
  const cellLabel=datedCellLabel(data?.cell||{},true);
  const cellDate=recordingDate(data?.cell||{});
  const recordedName=data?.cell?.cell_label||data?.cell?.label||'Cell label not recorded';
  const cellName=String(recordedName).startsWith(`${cellDate} · `)?String(recordedName).slice(cellDate.length+3):recordedName;
  const typeLabel=cellTypeQCLabel(data?.cell?.cell_type);
  const sourceEpoch=epoch.data?.cell_uuid===cellUuid&&epoch.data?.epoch_uuid===epochId?epoch.data:null;
  // Tag receipts change only annotation display; the trace keeps the source
  // epoch object so a tag save never repaints recorded samples.
  const rawEpoch=useMemo(()=>sourceEpoch&&tagStore.apply(sourceEpoch),[sourceEpoch,tagVersion]);
  useEffect(()=>{
    if(family)return;
    if(anchorEpoch){
      if(rows.path===rowsPath&&rows.data?.anchor_epoch_uuid===anchorEpoch){setFamily(rows.data.family);setOffset(rows.data.offset);}
    }else if(selected&&rawEpoch){
      const match=available.find(item=>item.protocol_names?.includes(rawEpoch.protocol_name));if(match)setFamily(match.id);
    }
  },[family,anchorEpoch,rows.path,rows.data,rowsPath,selected,rawEpoch,data]);
  useEffect(()=>{
    const list=trialList.current,trial=selectedTrial.current;
    if(!viewActive||!initialEpochUuid||epochId!==initialEpochUuid||!list?.clientHeight||!trial)return;
    // Reveal only inside the trial list; do not move the outer workspace or focus.
    const top=trial.getBoundingClientRect().top-list.getBoundingClientRect().top+list.scrollTop;
    const bottom=top+trial.offsetHeight;
    if(top<list.scrollTop)list.scrollTop=top;
    else if(bottom>list.scrollTop+list.clientHeight)list.scrollTop=bottom-list.clientHeight;
  },[viewActive,initialEpochUuid,epochId,rows.path,rows.data]);
  const measured=response.data?.epoch_uuid===epochId&&response.data?.cell_uuid===cellUuid?response.data:null;
  const stats=measured?.statistics;
  const summaryStream=rawEpoch?.streams?.find(stream=>stream.uuid===measured?.trace?.stream_uuid);
  async function copyIdentity(){try{await navigator.clipboard.writeText(cellUuid);setCopied(true);setCopyError('');}catch{setCopyError('Copy is unavailable. Select the UUID below to copy it.');}}
  function refreshQC(){epochResourceCache.invalidate(`/cells/${cellUuid}/qc`,{related:true});setRefresh(n=>n+1);}
  function chooseFamily(id){if(id===active&&!anchorEpoch)return;setFamily(id);setOffset(0);setSelected(null);}
  return <div className="page cell-qc"><header className="qc-toolbar" aria-label="Cell quality controls"><button onClick={onBack} aria-label="Back to workspace"><ArrowLeft size={15}/> Back</button><div className="qc-toolbar-details">{data&&<span>{number(data.counts?.epochs)} epochs · {number(data.counts?.blocks)} blocks</span>}<button className="qc-copy" onClick={copyIdentity} aria-label="Copy cell UUID" title={cellUuid}>{copied?<Check size={14}/>:<Copy size={14}/>} UUID</button><button onClick={refreshQC} aria-label="Refresh cell quality" title="Refresh cell quality"><RefreshCw size={16}/></button></div></header>
    {copyError&&<div className="qc-copy-error" role="status">{copyError} <code>{cellUuid}</code></div>}
    <Status {...result} retry={result.reload}>{data&&<>
      <section className={`qc-metrics${conditions.additions.length?' qc-with-additions':''}`} style={{'--qc-condition-columns':3+conditions.additions.length}} aria-label="Cell quality measurements"><article className="qc-cell-type" aria-label="Cell identity" title={cellLabel}><strong title={data.cell?.cell_type||'Unclassified'}>{typeLabel.toLowerCase()==='bipolar'?'Bipolar cell':typeLabel}</strong><div className="qc-cell-type-icon"><CellTypeIcon type={data.cell?.cell_type} size={42}/></div><h1>{cellName}</h1><span className="qc-cell-date">{cellDate}</span>{data.cell?.identity_qualifier&&<span className="qc-cell-qualifier">{data.cell.identity_qualifier}</span>}</article><article><button className="qc-temperature-metric" aria-controls={`qc-temperature-${cellUuid}`} aria-expanded={temperatureOpen} onClick={()=>setTemperatureOpen(value=>!value)}><span><Thermometer size={16}/> Bath temperature</span><TemperatureSummary temperature={temperature}/></button></article><article><span><Monitor size={16}/> Rig</span><strong>{recordingRigLabel(data.cell)}</strong><small>Recorded acquisition rig</small></article><SolutionMetric item={conditions.pipette}/>{conditions.additions.map(item=><SolutionMetric key={item.label} item={item}/>)}</section>
      <TemperaturePanel key={`${cellUuid}:temperature`} cellUuid={cellUuid} revision={qcRevision} opened={temperatureOpen} onToggle={()=>setTemperatureOpen(false)} temperature={temperature} groupLabels={data.characteristics?.group_labels}/>
      <section className="qc-characterization"><header><h2><Layers size={17}/> Characterization recordings</h2><span className="qc-muted">Availability is separate from cell quality.</span></header><nav className="qc-families" aria-label="Cell characterization protocols">{(data.families||[]).map(item=><button key={item.id} disabled={!item.epoch_count} aria-pressed={active===item.id} onClick={()=>chooseFamily(item.id)}><span>{item.label}</span><strong>{item.epoch_count?number(item.epoch_count):'Not recorded'}</strong></button>)}</nav>
      {!available.length?<Empty title="No characterization recordings">Source recordings remain available from the main catalog.</Empty>:<div className={`qc-recording-workbench ${showMetadata?'with-metadata':''}`}><aside className="qc-trials" aria-label="Characterization trials"><header><strong>{data.families.find(item=>item.id===active)?.label}</strong><small>{rows.data?number(rows.data.total):'…'} trials</small></header><div className="qc-trial-list" ref={trialList}><Status {...rows} retry={rows.reload}>{epochs.map(row=><button key={row.epoch_uuid} ref={epochId===row.epoch_uuid?selectedTrial:null} aria-pressed={epochId===row.epoch_uuid} onClick={()=>setSelected(row.epoch_uuid)}><span>{row.start_time?.slice(11)||row.date} · Epoch {row.epoch_number}</span><strong>{conditionLabel(row)}</strong><small>{row.group_label || 'Group not labeled'}</small></button>)}</Status></div><footer><button disabled={!offset} onClick={()=>{setSelected(null);setOffset(Math.max(0,offset-40));}}>Previous</button><span>{offset+1}–{offset+epochs.length}</span><button disabled={!rows.data?.has_more} onClick={()=>{setSelected(null);setOffset(offset+40);}}>Next</button></footer></aside>
      <StableContent className="qc-recording-frame" scope={`${cellUuid}:${qcRevision}`} data={rawEpoch} loading={rows.loading||epoch.loading} error={rows.error||epoch.error} label="Loading selected trial" retry={()=>{rows.reload();epoch.reload();response.reload();}}><div className="qc-recording"><header><div><h3>Recorded response</h3><p>{rawEpoch?conditionLabel(rawEpoch):'Select a trial'}</p></div><button onClick={()=>{setShowMetadata(true);setTagFocus(value=>value+1);}}><Tag size={14}/> Tags</button><button aria-expanded={showMetadata} onClick={()=>setShowMetadata(!showMetadata)}>{showMetadata?'Hide':'Show'} metadata</button></header><Status {...epoch} retry={epoch.reload}>{rawEpoch&&<><Trace epoch={sourceEpoch} revision={qcRevision}/><div className="qc-trace-identity"><code title="Trial UUID">{rawEpoch.epoch_uuid}</code><button onClick={()=>setShowMetadata(true)}><ArrowUpRight size={14}/> Epoch details</button></div></>}</Status>
      <Status {...response} retry={response.reload}>{stats&&<><p className="qc-muted">Summary stream: {summaryStream?.device || measured?.trace?.stream_uuid} · {stats.units || 'unit unrecorded'}</p><div className="qc-response-stats"><div><span>Pre-stimulus mean</span><strong>{display(stats.pre?.mean)} <small>{stats.units}</small></strong></div><div><span>Stimulus-window mean</span><strong>{display(stats.stim?.mean)} <small>{stats.units}</small></strong></div><div><span>Change in mean</span><strong>{display(stats.delta_mean)} <small>{stats.units}</small></strong></div></div>{stats.status==='unavailable'&&<p className="qc-muted">{stats.reason}</p>}</>}</Status><p className="qc-method-note"><Info size={15}/> Recorded response summaries retain the raw signal. They are not firing rate, sensitivity, receptive-field fits, or resting voltage.</p><details className="qc-method"><summary>Response timing & measurement method</summary><pre>{JSON.stringify({timing:measured?.timing,method:measured?.method,statistics:stats},null,2)}</pre></details><ConditionSummary key={`${cellUuid}:${active}`} cellUuid={cellUuid} family={active} epoch={rawEpoch} revision={qcRevision} onSelect={setSelected}/></div></StableContent>
      {showMetadata&&<MetadataPanel tags={rawEpoch&&<AnnotationTags reconcileReceipt refreshWithEpoch epoch={rawEpoch} revision={liveRevision} disabled={epoch.loading} focusRequest={tagFocus} onChange={annotationsChanged} onFilter={onTagFilter} tools={<TagExchangeControls epoch={rawEpoch} disabled={epoch.loading} onChanged={annotationsChanged}/>}/>} epoch={sourceEpoch} catalog={catalog} onClose={()=>setShowMetadata(false)}/>}</div>}
      </section><BaselinePanel key={cellUuid} cellUuid={cellUuid} definition={data.resting_voltage} revision={qcRevision}/>
      <details className="qc-analysis-status"><summary>Analysis availability & reconstruction</summary><div>{(data.analysis_capabilities||[]).map(item=><article key={item.id}><strong>{humanize(item.label||item.id).replace(/_/g,' ')}</strong><Badge>{humanize(item.status).replace(/_/g,' ')}</Badge><p>{item.reason}</p></article>)}</div><details><summary>Cell provenance</summary><pre>{JSON.stringify(data.characteristics,null,2)}</pre></details></details>
    </>}</Status>
  </div>;
}
