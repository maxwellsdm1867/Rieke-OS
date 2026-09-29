import {useEffect,useState} from 'react';
import {Activity,ArrowLeft,ArrowUpRight,Check,Copy,Info,Layers,RefreshCw,Thermometer,Tag} from 'lucide-react';
import {humanize,number,useResource} from '../api.js';
import {Badge,Empty,Status} from './Common.jsx';
import Trace from './TraceViewer.jsx';
import MetadataPanel from './MetadataPanel.jsx';
import AnnotationTags from './AnnotationTags.jsx';
import TagExchangeControls from './TagExchangeControls.jsx';
import {datedCellLabel} from '../recordingIdentity.js';
import './CellQC.css';

const numeric=value=>typeof value==='number'&&Number.isFinite(value);
const display=value=>!numeric(value)?'—':value!==0&&(Math.abs(value)<0.001||Math.abs(value)>=1e6)?value.toExponential(3):new Intl.NumberFormat(undefined,{maximumSignificantDigits:5}).format(value);
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
    {[low,(low+high)/2,high].map(v=><g key={v}><line x1="58" x2="528" y1={20+(high-v)/(high-low)*104} y2={20+(high-v)/(high-low)*104} stroke="#ece7f0"/><text x="49" y={24+(high-v)/(high-low)*104} textAnchor="end">{display(v)}</text></g>)}
    <polyline points={xy.map(p=>p.join(',')).join(' ')} fill="none" stroke="#397b86" strokeWidth="1.7"/>
    {xy.map(([x,y],i)=><circle key={i} cx={x} cy={y} r="2.6" fill="#397b86"><title>{data[i].start_time} · {display(data[i][valueKey])} {units||''}</title></circle>)}
    <text x="58" y="147">First observation</text><text x="528" y="147" textAnchor="end">Last shown observation</text>
    <text transform="translate(13,74) rotate(-90)" textAnchor="middle">{units||'Recorded value'}</text>
  </svg>;
}

function BaselinePanel({cellUuid,revision,definition}){
  const [opened,setOpened]=useState(false);
  const result=useResource(opened?`/cells/${cellUuid}/qc/block-baselines`:null,revision);
  return <section className="qc-baseline"><header><div><h2><Activity size={17}/> Block-onset voltage</h2><p>Check baseline stability across the recording.</p></div><button onClick={()=>setOpened(!opened)} aria-expanded={opened}>{opened?'Hide measurements':'Measure block onsets'}</button></header>
    <p className="qc-method-note"><Info size={15}/>{definition?.reason || 'Block-onset measurements are separate from a validated resting-potential estimate.'}</p>
    {opened&&<Status {...result} retry={result.reload}>{result.data&&<><Trend points={result.data.anchors} valueKey="mean_mV" label="Chronological block-onset mean voltage" units="mV"/>
      <p className="qc-muted">Observations are equally spaced by recording order; the line is not an interpolated resting potential.</p>
      <div className="qc-scroll-table"><table><thead><tr><th>Block onset</th><th>Mean (mV)</th><th>Samples</th><th>Measurement flags</th></tr></thead><tbody>{(result.data.anchors||[]).map(anchor=><tr key={anchor.block_uuid}><td>{anchor.start_time}</td><td>{display(anchor.mean_mV)}</td><td>{number(anchor.sample_count)}</td><td>{flagged(anchor.flags).length?flagged(anchor.flags).map(v=>humanize(v).replace(/_/g,' ')).join(' · '):'No estimator flags'}</td></tr>)}</tbody></table></div>
      {!(result.data.anchors||[]).length&&<Empty title="No eligible block anchors">The recorded streams do not meet this method’s requirements.</Empty>}
      <details className="qc-method"><summary>Method, exclusions & provenance</summary><pre>{JSON.stringify({method:result.data.method,excluded_blocks:result.data.excluded_blocks,interpolation:result.data.interpolation},null,2)}</pre></details>
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
      {[ymin,(ymin+ymax)/2,ymax].filter((v,i,a)=>a.indexOf(v)===i).map(v=><g key={v}><line x1="65" x2="525" y1={y(v)} y2={y(v)} stroke="#eae5ef"/><text x="55" y={y(v)+4} textAnchor="end">{display(v)}</text></g>)}
      {points.map((p,i)=><circle key={p.condition_id} cx={x(xs[i])} cy={y(ys[i])} r="5" fill="#397b86"><title>{conditionLabel(p)} · {display(p.response_mean)} {p.units} · {p.used_epoch_count}/{p.epoch_count} trials</title></circle>)}
      {[xmin,xmax].filter((v,i,a)=>a.indexOf(v)===i).map(v=><text key={v} x={x(v)} y="181" textAnchor="middle">{display(v)}</text>)}
      <text x="295" y="204" textAnchor="middle">{xField?`${parameterLabel(xField)} (recorded value)`:'Condition order'}</text><text transform="translate(15,90) rotate(-90)" textAnchor="middle">Mean response ({units[0]})</text>
    </svg>:<p className="qc-muted">{units.length>1?'Different response units cannot share one axis.':'No complete stimulus windows available for this block.'}</p>}
    <p className="qc-muted">Each point uses up to three trials with identical parameters in this block. Raw signal features are retained; this is not a sensitivity or receptive-field estimate.</p>
    <div className="qc-scroll-table"><table><thead><tr><th>Recorded condition</th><th>Mean response</th><th>Trial coverage</th><th/></tr></thead><tbody>{(data.points||[]).map(p=><tr key={p.condition_id}><td>{conditionLabel(p)}</td><td>{display(p.response_mean)} {p.units}</td><td>{p.used_epoch_count} / {p.epoch_count}</td><td>{p.measurements?.[0]&&<button onClick={()=>onSelect(p.measurements[0].epoch_uuid)}>View trial</button>}</td></tr>)}</tbody></table></div>
    {!!data.skipped?.length&&<p className="qc-muted">{number(data.skipped.length)} trial measurements unavailable or beyond this preview’s sample budget.</p>}{data.truncated&&<p className="qc-muted">Showing a bounded subset of conditions.</p>}
    <details className="qc-method"><summary>Method & coverage details</summary><pre>{JSON.stringify({method:data.method,skipped:data.skipped,samples_read:data.samples_read},null,2)}</pre></details>
  </>}</Status>}</section>;
}

export default function CellQC({cellUuid,revision,onBack,initialEpochUuid,session,onSession,onAnnotationsChanged,onTagFilter}){
  const [refresh,setRefresh]=useState(0),[tagFocus,setTagFocus]=useState(0);
  function annotationsChanged(){setRefresh(value=>value+1);onAnnotationsChanged?.();}
  const qcRevision=`${revision}:${refresh}`;
  const result=useResource(`/cells/${cellUuid}/qc`,qcRevision);
  const data=result.data;
  const [family,setFamily]=useState(session?.family||''),[offset,setOffset]=useState(session?.offset||0),[selected,setSelected]=useState(session&&Object.hasOwn(session,'selected')?session.selected:(initialEpochUuid??null)),[copied,setCopied]=useState(false),[copyError,setCopyError]=useState(''),[showMetadata,setShowMetadata]=useState(session?.showMetadata||false);
  useEffect(()=>{onSession?.({family,offset,selected,showMetadata});},[family,offset,selected,showMetadata,onSession]);
  const available=(data?.families||[]).filter(item=>item.epoch_count>0);
  const active=family || available[0]?.id;
  const rowsPath=active?`/cells/${cellUuid}/qc/epochs?family=${encodeURIComponent(active)}&offset=${offset}&limit=40`:null;
  const rows=useResource(rowsPath,qcRevision);
  const epochs=rows.path===rowsPath?rows.data?.epochs||[]:[];
  const epochId=selected || epochs[0]?.epoch_uuid;
  const epoch=useResource(epochId?`/epochs/${epochId}`:null,qcRevision);
  const response=useResource(epochId?`/cells/${cellUuid}/qc/response?epoch_uuid=${epochId}&summary_only=true`:null,qcRevision);
  const catalog=useResource(showMetadata?'/explore/predicate-fields':null,qcRevision);
  const temperature=data?.temperature;
  const range=temperature?.range;
  const cellLabel=datedCellLabel(data?.cell||{},true);
  const rawEpoch=epoch.data?.cell_uuid===cellUuid&&epoch.data?.epoch_uuid===epochId?epoch.data:null;
  useEffect(()=>{if(!family&&initialEpochUuid&&rawEpoch){const match=available.find(item=>item.protocol_names?.includes(rawEpoch.protocol_name));if(match)setFamily(match.id);}},[family,initialEpochUuid,rawEpoch,data]);
  const measured=response.data?.epoch_uuid===epochId&&response.data?.cell_uuid===cellUuid?response.data:null;
  const stats=measured?.statistics;
  const summaryStream=rawEpoch?.streams?.find(stream=>stream.uuid===measured?.trace?.stream_uuid);
  async function copyIdentity(){try{await navigator.clipboard.writeText(cellUuid);setCopied(true);setCopyError('');}catch{setCopyError('Copy is unavailable. Select the UUID below to copy it.');}}
  function chooseFamily(id){setFamily(id);setOffset(0);setSelected(null);}
  return <div className="page cell-qc"><header className="qc-heading"><div><div className="eyebrow">CELL QUALITY WORKBENCH</div><h1>{data?cellLabel:'Cell quality'}</h1><p>Characterization recordings linked across the main project database.</p></div><div className="qc-heading-actions"><button onClick={onBack}><ArrowLeft size={15}/> Back to workspace</button><button onClick={()=>setRefresh(n=>n+1)} aria-label="Refresh cell quality"><RefreshCw size={16}/></button></div></header>
    <Status {...result} retry={result.reload}>{data&&<>
      <div className="qc-identity"><Badge>{humanize(data.cell?.cell_type)||'Unclassified'}</Badge><span>{number(data.counts?.epochs)} epochs · {number(data.counts?.blocks)} blocks</span><button className="qc-copy" onClick={copyIdentity} aria-label="Copy cell UUID">{copied?<Check size={13}/>:<Copy size={13}/>} Cell UUID</button><code>{cellUuid}</code>{copyError&&<span role="status">{copyError}</span>}</div>
      <section className="qc-metrics" aria-label="Cell quality measurements"><article><span><Thermometer size={16}/> Bath temperature</span><strong>{range&&numeric(range.min)?`${display(range.min)}${range.max!==range.min?` – ${display(range.max)}`:''}`:'Not recorded'}</strong><small>{temperature?.units || 'Unit not recorded'} · {number(temperature?.recorded_count)} observations</small></article><article><span><Activity size={16}/> Resistance</span><strong>{data.resistance?.measurements?.length?'Recorded measurements':'Not recorded'}</strong><small>Compensation settings are not resistance measurements.</small></article><article><span><Activity size={16}/> Resting voltage</span><strong>{data.resting_voltage?.status==='available'?display(data.resting_voltage.value):'Not established'}</strong><small>Block-onset measurements available separately.</small></article></section>
      <details className="qc-temperature"><summary><Thermometer size={15}/> Temperature & recording conditions <span>{(data.characteristics?.group_labels||[]).join(' · ')}</span></summary><Trend points={temperature?.points} label="Recorded bath temperature" units={temperature?.units}/><p className="qc-muted">{number(temperature?.missing_count)} epochs without a temperature entry. Values follow acquisition order; no pass/fail threshold is applied.{temperature?.truncated?' The preview is bounded; additional observations are not shown.':''}</p><details><summary>Recorded resistance & compensation fields</summary><pre>{JSON.stringify(data.resistance,null,2)}</pre></details></details>
      <section className="qc-characterization"><header><h2><Layers size={17}/> Characterization recordings</h2><span className="qc-muted">Availability is separate from cell quality.</span></header><nav className="qc-families" aria-label="Cell characterization protocols">{(data.families||[]).map(item=><button key={item.id} disabled={!item.epoch_count} aria-pressed={active===item.id} onClick={()=>chooseFamily(item.id)}><span>{item.label}</span><strong>{item.epoch_count?number(item.epoch_count):'Not recorded'}</strong></button>)}</nav>
      {!available.length?<Empty title="No characterization recordings">Source recordings remain available from the main catalog.</Empty>:<div className={`qc-recording-workbench ${showMetadata?'with-metadata':''}`}><aside className="qc-trials" aria-label="Characterization trials"><header><strong>{data.families.find(item=>item.id===active)?.label}</strong><small>{number(rows.data?.total)} trials</small></header><Status {...rows} retry={rows.reload}><div className="qc-trial-list">{epochs.map(row=><button key={row.epoch_uuid} aria-pressed={epochId===row.epoch_uuid} onClick={()=>setSelected(row.epoch_uuid)}><span>{row.start_time?.slice(11)||row.date} · Epoch {row.epoch_number}</span><strong>{conditionLabel(row)}</strong><small>{row.group_label || 'Group not labeled'}</small></button>)}</div></Status><footer><button disabled={!offset} onClick={()=>{setSelected(null);setOffset(Math.max(0,offset-40));}}>Previous</button><span>{offset+1}–{offset+epochs.length}</span><button disabled={!rows.data?.has_more} onClick={()=>{setSelected(null);setOffset(offset+40);}}>Next</button></footer></aside>
      <div className="qc-recording"><header><div><h3>Recorded response</h3><p>{rawEpoch?conditionLabel(rawEpoch):'Select a trial'}</p></div><button onClick={()=>{setShowMetadata(true);setTagFocus(value=>value+1);}}><Tag size={14}/> Tags</button><button aria-expanded={showMetadata} onClick={()=>setShowMetadata(!showMetadata)}>{showMetadata?'Hide':'Show'} metadata</button></header><Status {...epoch} retry={epoch.reload}>{rawEpoch&&<><Trace epoch={rawEpoch}/><div className="qc-trace-identity"><code title="Trial UUID">{rawEpoch.epoch_uuid}</code><button onClick={()=>setShowMetadata(true)}><ArrowUpRight size={14}/> Epoch details</button></div></>}</Status>
      <Status {...response} retry={response.reload}>{stats&&<><p className="qc-muted">Summary stream: {summaryStream?.device || measured?.trace?.stream_uuid} · {stats.units || 'unit unrecorded'}</p><div className="qc-response-stats"><div><span>Pre-stimulus mean</span><strong>{display(stats.pre?.mean)} <small>{stats.units}</small></strong></div><div><span>Stimulus-window mean</span><strong>{display(stats.stim?.mean)} <small>{stats.units}</small></strong></div><div><span>Change in mean</span><strong>{display(stats.delta_mean)} <small>{stats.units}</small></strong></div></div>{stats.status==='unavailable'&&<p className="qc-muted">{stats.reason}</p>}</>}</Status><p className="qc-method-note"><Info size={15}/> Recorded response summaries retain the raw signal. They are not firing rate, sensitivity, receptive-field fits, or resting voltage.</p><details className="qc-method"><summary>Response timing & measurement method</summary><pre>{JSON.stringify({timing:measured?.timing,method:measured?.method,statistics:stats},null,2)}</pre></details><ConditionSummary key={`${cellUuid}:${active}`} cellUuid={cellUuid} family={active} epoch={rawEpoch} revision={qcRevision} onSelect={setSelected}/></div>
      {showMetadata&&<MetadataPanel tags={rawEpoch&&<AnnotationTags epoch={rawEpoch} revision={qcRevision} disabled={epoch.loading} focusRequest={tagFocus} onChange={annotationsChanged} onFilter={onTagFilter} tools={<TagExchangeControls epoch={rawEpoch} disabled={epoch.loading} onChanged={annotationsChanged}/>}/>} epoch={rawEpoch} catalog={catalog} onClose={()=>setShowMetadata(false)}/>}</div>}
      </section><BaselinePanel key={cellUuid} cellUuid={cellUuid} revision={qcRevision} definition={data.resting_voltage}/>
      <details className="qc-analysis-status"><summary>Analysis availability & reconstruction</summary><div>{(data.analysis_capabilities||[]).map(item=><article key={item.id}><strong>{humanize(item.label||item.id).replace(/_/g,' ')}</strong><Badge>{humanize(item.status).replace(/_/g,' ')}</Badge><p>{item.reason}</p></article>)}</div><details><summary>Cell provenance</summary><pre>{JSON.stringify(data.characteristics,null,2)}</pre></details></details>
    </>}</Status>
  </div>;
}
