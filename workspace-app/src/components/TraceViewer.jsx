import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Activity,ArrowLeft,ArrowRight,Hand,LoaderCircle,MousePointer2,RotateCcw,ZoomIn,ZoomOut} from 'lucide-react';
import {number,useResource} from '../api.js';
import {clampWindow,dragWindow,finiteExtent,formatTick,MAX_TRACE_SAMPLES,sampleAtPixel,ticks,timeRange,zoomWindow} from './traceGeometry.js';
import './TraceViewer.css';
import {useNavigationLoading,useDelayedLoading} from './NavigationLoading.jsx';

function paintTrace(canvas,data){
  const rect=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio || 1;
  canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,rect.width,rect.height);
  if(!data||!rect.width)return null;
  const extent=finiteExtent(data.values),range=timeRange(data.start,data.values.length,data.sample_rate);
  if(!extent||!range)return null;
  const left=82,right=21,top=25,bottom=57,w=Math.max(1,rect.width-left-right),h=Math.max(1,rect.height-top-bottom);
  const ink=getComputedStyle(canvas).getPropertyValue('--ink-secondary').trim() || '#62566d';
  const x=index=>left+(data.values.length>1?index/(data.values.length-1):.5)*w;
  const y=value=>top+(extent.max-value)/(extent.max-extent.min)*h;
  ctx.font='12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';ctx.lineWidth=1;
  for(const value of ticks(extent.min,extent.max,5)){
    const at=y(value);ctx.strokeStyle='#e9e5ed';ctx.beginPath();ctx.moveTo(left,at);ctx.lineTo(left+w,at);ctx.stroke();
    ctx.fillStyle=ink;ctx.textAlign='right';ctx.textBaseline='middle';ctx.fillText(formatTick(value,extent.max-extent.min),left-10,at);
  }
  const xticks=range.span>0?ticks(range.first,range.last,Math.max(3,Math.min(7,Math.floor(w/110)))):[range.first];
  for(const value of xticks){
    const at=range.span>0?left+(value-range.first)/range.span*w:left+w/2;
    ctx.strokeStyle='#eeeaf2';ctx.beginPath();ctx.moveTo(at,top);ctx.lineTo(at,top+h);ctx.stroke();
    ctx.fillStyle=ink;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(formatTick(value,range.span || 1/data.sample_rate),at,top+h+10);
  }
  ctx.strokeStyle='#93869d';ctx.beginPath();ctx.moveTo(left,top);ctx.lineTo(left,top+h);ctx.lineTo(left+w,top+h);ctx.stroke();
  ctx.fillStyle=ink;ctx.font='13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText('Time from stream start (s)',left+w/2,rect.height-4);
  ctx.save();ctx.translate(16,top+h/2);ctx.rotate(-Math.PI/2);ctx.textBaseline='top';ctx.fillText(data.units?`Response (${data.units})`:'Response (unit not recorded)',0,0);ctx.restore();
  ctx.save();ctx.beginPath();ctx.rect(left-1,top-1,w+2,h+2);ctx.clip();ctx.strokeStyle='#306f83';ctx.lineWidth=1.1;ctx.beginPath();let runLength=0,runStart=0;const isolated=[];
  data.values.forEach((value,index)=>{if(typeof value!=='number'||!Number.isFinite(value)){if(runLength===1)isolated.push(runStart);runLength=0;return;}if(runLength)ctx.lineTo(x(index),y(value));else{ctx.moveTo(x(index),y(value));runStart=index;}runLength++;});ctx.stroke();
  if(runLength===1)isolated.push(runStart);
  ctx.fillStyle='#306f83';ctx.beginPath();for(const index of isolated){ctx.moveTo(x(index)+2.5,y(data.values[index]));ctx.arc(x(index),y(data.values[index]),2.5,0,Math.PI*2);}ctx.fill();
  ctx.restore();
  return {left,top,w,h,width:rect.width,height:rect.height,ratio,extent,range,x,y,data};
}

// Keep the canvas mounted while resetting stream/window state for each identity.
export default function Trace({epoch,revision=0}){return <TraceViewer epoch={epoch} revision={revision}/>;}
function TraceViewer({epoch,revision}){
  const streams=(epoch?.streams || []).filter(stream=>stream.kind==='responses'&&stream.sample_count>0);
  const [selection,setSelection]=useState({epoch:epoch?.epoch_uuid,stream:streams[0]?.uuid || ''});
  const sameEpoch=selection.epoch===epoch?.epoch_uuid;
  const selectedStream=sameEpoch?selection.stream:streams[0]?.uuid;
  const setSelectedStream=stream=>setSelection({epoch:epoch?.epoch_uuid,stream});
  const stream=streams.find(item=>item.uuid===selectedStream) || streams[0];
  const [viewport,setViewport]=useState(()=>clampWindow(0,MAX_TRACE_SAMPLES,stream?.sample_count));
  const [mode,setMode]=useState('zoom'),[entryStart,setEntryStart]=useState('0'),[entryCount,setEntryCount]=useState(String(viewport.count));
  const [entryError,setEntryError]=useState('');
  const bounded=clampWindow(sameEpoch?viewport.start:0,sameEpoch?viewport.count:MAX_TRACE_SAMPLES,stream?.sample_count);
  useEffect(()=>{if(!sameEpoch){setSelection({epoch:epoch?.epoch_uuid,stream:streams[0]?.uuid || ''});setViewport(clampWindow(0,MAX_TRACE_SAMPLES,streams[0]?.sample_count));setEntryError('');}},[epoch?.epoch_uuid,sameEpoch]);
  const requestPath=stream?`/epochs/${epoch.epoch_uuid}/trace?stream_uuid=${stream.uuid}&start=${bounded.start}&count=${bounded.count}`:null;
  const resource=useResource(requestPath,revision,0,{cache:true});
  const data=resource.path===requestPath&&resource.data?.epoch_uuid===epoch?.epoch_uuid&&resource.data?.stream_uuid===stream?.uuid&&resource.data?.start===bounded.start&&resource.data?.count===bounded.count?resource.data:null;
  const valid=data&&data.sample_rate>0&&Number.isFinite(data.sample_rate)&&data.values?.length===data.count;
  const base=useRef(null),overlay=useRef(null),geometry=useRef(null),cursor=useRef(null),drag=useRef(null),frame=useRef(null),readout=useRef(null),cursorInput=useRef(null),surface=useRef(null);
  const painted=useRef(false);
  const dataRef=useRef(null);dataRef.current=valid?data:null;
  const currentError=resource.path===requestPath?resource.error:null;
  const pending=!!stream&&!currentError&&(resource.loading||resource.path!==requestPath||!resource.data);
  const coordinated=useNavigationLoading(pending);
  const showLoading=useDelayedLoading(pending&&!coordinated);
  const invalidResponse=resource.path===requestPath&&resource.data&&(!data||!valid);
  const range=valid?timeRange(data.start,data.count,data.sample_rate):null;
  const gapCount=valid?data.values.filter(value=>typeof value!=='number'||!Number.isFinite(value)).length:0;
  const total=stream?.sample_count || 0;
  function moveWindow(next){
    const window=clampWindow(next.start,next.count,total);drag.current=null;cursor.current=null;setEntryError('');setViewport(window);
  }
  useEffect(()=>{setEntryStart(String(bounded.start));setEntryCount(String(bounded.count));},[bounded.start,bounded.count]);
  function scheduleOverlay(){
    if(frame.current!=null)return;
    frame.current=requestAnimationFrame(()=>{frame.current=null;drawOverlay();});
  }
  function drawOverlay(){
    const el=overlay.current,g=geometry.current,d=dataRef.current;if(!el)return;
    const ctx=el.getContext('2d');ctx.clearRect(0,0,el.width,el.height);
    if(!g||!d)return;
    ctx.setTransform(g.ratio,0,0,g.ratio,0,0);
    if(drag.current){
      const a=drag.current.origin,b=drag.current.current;
      ctx.fillStyle=mode==='zoom'?'rgba(103,68,125,.13)':'rgba(48,111,131,.08)';
      ctx.fillRect(g.left+Math.min(a,b),g.top,Math.max(1,Math.abs(b-a)),g.h);
      ctx.strokeStyle='#79568d';ctx.lineWidth=1;ctx.setLineDash([4,3]);
      for(const at of [a,b]){ctx.beginPath();ctx.moveTo(g.left+at,g.top);ctx.lineTo(g.left+at,g.top+g.h);ctx.stroke();}ctx.setLineDash([]);
    }
    if(cursor.current==null)return;
    const index=Math.max(0,Math.min(d.count-1,cursor.current)),value=d.values[index],x=g.x(index),finite=typeof value==='number'&&Number.isFinite(value);
    ctx.strokeStyle='#756080';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,g.top);ctx.lineTo(x,g.top+g.h);
    if(finite){const y=g.y(value);ctx.moveTo(g.left,y);ctx.lineTo(g.left+g.w,y);}ctx.stroke();ctx.setLineDash([]);
    if(finite){ctx.fillStyle='#306f83';ctx.beginPath();ctx.arc(x,g.y(value),3,0,Math.PI*2);ctx.fill();}
    const absolute=d.start+index,time=absolute/d.sample_rate;
    if(readout.current)readout.current.textContent=`Sample ${number(absolute)} · ${String(time)} s · ${finite?String(value):'Missing sample'}${finite&&d.units?` ${d.units}`:''}`;
    if(cursorInput.current&&document.activeElement!==cursorInput.current)cursorInput.current.value=String(absolute);
  }
  useLayoutEffect(()=>{
    if(!base.current||!overlay.current){painted.current=false;return;}
    cursor.current=null;drag.current=null;
    if(readout.current)readout.current.textContent='Move over the plot or use the sample cursor to read a recorded value.';
    if(cursorInput.current)cursorInput.current.value=valid?String(data.start):'';
    let resizedFrame;
    const draw=()=>{
      // A pending request keeps the previous bitmap visible but non-interactive.
      // Failed/invalid responses clear it; only validated samples get new axes.
      geometry.current=valid?paintTrace(base.current,data):pending?null:paintTrace(base.current,null);
      if(valid)painted.current=true;else if(!pending)painted.current=false;
      const rect=base.current.getBoundingClientRect(),ratio=window.devicePixelRatio || 1;
      overlay.current.width=Math.round(rect.width*ratio);overlay.current.height=Math.round(rect.height*ratio);
      scheduleOverlay();
    };
    const resize=()=>{cancelAnimationFrame(resizedFrame);resizedFrame=requestAnimationFrame(draw);};
    draw();const observer=new ResizeObserver(resize);observer.observe(base.current);window.addEventListener('resize',resize);
    return()=>{observer.disconnect();window.removeEventListener('resize',resize);cancelAnimationFrame(resizedFrame);if(frame.current!=null){cancelAnimationFrame(frame.current);frame.current=null;}};
  },[data,valid,pending]);
  function local(event){const rect=overlay.current.getBoundingClientRect(),g=geometry.current;return g?{x:Math.max(0,Math.min(g.w,event.clientX-rect.left-g.left)),inside:event.clientX-rect.left>=g.left&&event.clientX-rect.left<=g.left+g.w&&event.clientY-rect.top>=g.top&&event.clientY-rect.top<=g.top+g.h}:null;}
  function pointerMove(event){const at=local(event);if(!at||!dataRef.current)return;if(drag.current)drag.current.current=at.x;if(at.inside||drag.current)cursor.current=sampleAtPixel(at.x,geometry.current.w,dataRef.current.count);scheduleOverlay();}
  function pointerDown(event){const at=local(event);if(event.button!==0||pending||!dataRef.current||!at?.inside)return;surface.current.focus({preventScroll:true});event.currentTarget.setPointerCapture(event.pointerId);drag.current={origin:at.x,current:at.x};cursor.current=sampleAtPixel(at.x,geometry.current.w,data.count);scheduleOverlay();}
  function pointerUp(event){
    if(!drag.current)return;const current=drag.current;drag.current=null;
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    if(Math.abs(current.current-current.origin)>=5)moveWindow(dragWindow(bounded,total,current.origin,current.current,geometry.current.w,mode));else scheduleOverlay();
  }
  function zoom(factor){const anchor=cursor.current==null?undefined:bounded.start+cursor.current;moveWindow(zoomWindow(bounded,total,factor,anchor));}
  function keyDown(event){
    if(!valid||pending)return;
    if(event.key==='Escape'){drag.current=null;scheduleOverlay();return;}
    if(['ArrowLeft','ArrowRight'].includes(event.key)){
      event.preventDefault();const direction=event.key==='ArrowLeft'?-1:1;
      if(event.shiftKey)moveWindow({...bounded,start:bounded.start+direction*Math.max(1,Math.round(bounded.count/2))});
      else{cursor.current=Math.max(0,Math.min(data.count-1,(cursor.current??0)+direction));scheduleOverlay();}
    }else if(['+','=','-','Home'].includes(event.key)){event.preventDefault();if(event.key==='Home')moveWindow({start:0,count:MAX_TRACE_SAMPLES});else zoom(event.key==='-'?2:.5);}
  }
  function submitWindow(event){
    event.preventDefault();const start=Number(entryStart),count=Number(entryCount);
    if(!entryStart.trim()||!entryCount.trim()||!Number.isSafeInteger(start)||!Number.isSafeInteger(count)||start<0||start>=total||count<1||count>Math.min(total,MAX_TRACE_SAMPLES)){setEntryError(`Use a start index from 0 to ${number(total-1)} and 1–${number(Math.min(total,MAX_TRACE_SAMPLES))} samples.`);return;}
    moveWindow({start,count});
  }
  if(!streams.length)return <section className="trace-viewer trace-section"><h3><Activity size={16}/> Recorded response</h3><p className="tv-empty">This epoch has no indexed response stream.</p></section>;
  return <section className="trace-viewer trace-section" aria-label="Recorded response viewer">
    <div className="tv-tools"><div className="tv-modes" aria-label="Drag interaction"><button className={mode==='zoom'?'active':''} aria-pressed={mode==='zoom'} onClick={()=>setMode('zoom')}><MousePointer2 size={13}/> Drag to zoom</button><button className={mode==='pan'?'active':''} aria-pressed={mode==='pan'} onClick={()=>setMode('pan')}><Hand size={13}/> Pan</button></div><div className="tv-zoom-buttons"><button disabled={pending||bounded.count<=Math.min(2,total)} onClick={()=>zoom(.5)} title="Zoom in around cursor or window center" aria-label="Zoom in"><ZoomIn size={15}/></button><button disabled={pending||bounded.count>=Math.min(MAX_TRACE_SAMPLES,total)} onClick={()=>zoom(2)} title="Zoom out, up to 20,000 full-rate samples" aria-label="Zoom out"><ZoomOut size={15}/></button><button disabled={pending} onClick={()=>moveWindow({start:0,count:MAX_TRACE_SAMPLES})} title="Return to the first bounded window"><RotateCcw size={13}/> Reset</button></div><span>Y-axis auto-scales per window</span></div>
    <div ref={surface} className={`tv-plot tv-${mode}`} tabIndex={0} role="group" aria-label="Trace plot. Arrow keys move the sample cursor. Shift and arrows pan. Plus and minus zoom. Home resets." onKeyDown={keyDown}>
      <canvas ref={base} className="tv-base" aria-hidden="true"/><canvas ref={overlay} className="tv-overlay" aria-hidden="true" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{drag.current=null;scheduleOverlay();}}/>
      {valid&&gapCount===data.count&&<div className="tv-status" role="status">No finite samples in this window.</div>}
      {pending&&painted.current&&<span className="tv-previous-trace">Previous trace · inactive</span>}
      {showLoading&&<div className="tv-status tv-loading" role="status"><span><LoaderCircle size={16}/> Loading selected samples{painted.current?' · previous trace is inactive':'…'}</span></div>}
      {currentError&&<div className="tv-status tv-error" role="alert"><span>{currentError}</span><button onClick={resource.reload}>Retry trace</button></div>}
      {invalidResponse&&<div className="tv-status tv-error" role="alert">Trace identity, sample rate or window does not match the request. No plot is shown.<button onClick={resource.reload}>Retry trace</button></div>}
    </div>
    <div className="tv-readout"><output ref={readout} aria-live="off"/><label>Sample cursor<input ref={cursorInput} type="number" step="1" min={bounded.start} max={bounded.start+bounded.count-1} disabled={!valid||pending} aria-label="Exact sample index for cursor" onChange={event=>{const sample=Number(event.target.value);if(event.target.value!==''&&Number.isInteger(sample)&&sample>=bounded.start&&sample<bounded.start+bounded.count){cursor.current=sample-bounded.start;scheduleOverlay();}}}/></label></div>
    {gapCount>0&&<div className="tv-warning">{number(gapCount)} missing or non-finite samples appear as gaps; they are not plotted as zero.</div>}
    <div className="tv-window-navigation"><button disabled={pending||bounded.start===0} onClick={()=>moveWindow({...bounded,start:bounded.start-bounded.count})}><ArrowLeft size={14}/> Previous window</button><span>{range?`${formatTick(range.first,1/data.sample_rate)}–${formatTick(range.last,1/data.sample_rate)} s`:'—'}<small>Samples {number(bounded.start)}–{number(bounded.start+bounded.count-1)} · zero-based, inclusive</small></span><button disabled={pending||bounded.start+bounded.count>=total} onClick={()=>moveWindow({...bounded,start:bounded.start+bounded.count})}>Next window <ArrowRight size={14}/></button></div>
    <details className="tv-window-settings"><summary>Window coordinates & keyboard controls</summary><form onSubmit={submitWindow}><label>Start sample<input type="number" value={entryStart} min="0" max={total-1} step="1" onChange={event=>setEntryStart(event.target.value)}/></label><label>Sample count<input type="number" value={entryCount} min="1" max={Math.min(total,MAX_TRACE_SAMPLES)} step="1" onChange={event=>setEntryCount(event.target.value)}/></label><button disabled={pending} type="submit">Show window</button></form>{entryError&&<p className="tv-warning" role="alert">{entryError}</p>}<p>Focus the plot: ← / → moves one sample; Shift + ← / → pans; + / − zooms; Home resets. Dragging requests samples only on release. No filtering or resampling is applied.</p></details>
    <footer className="tv-recording-footer">
    <div className="tv-heading"><h3><Activity size={16}/> Recorded response</h3><label>Stream<select aria-label="Response stream" value={stream.uuid} onChange={event=>{setSelectedStream(event.target.value);const next=streams.find(item=>item.uuid===event.target.value);setViewport(clampWindow(0,MAX_TRACE_SAMPLES,next.sample_count));setEntryError('');drag.current=null;cursor.current=null;}}>{streams.map(item=><option key={item.uuid} value={item.uuid}>{item.device} · {item.units || 'unit not recorded'}</option>)}</select></label></div>
    <div className="tv-data-info"><span className="tv-full-rate">Full sample rate</span><span>{number(valid?data.sample_rate:stream.sample_rate)} Hz</span><span>{number(total)} samples in stream</span><span>{bounded.count===total?'Entire stream':'Bounded window · up to 20,000 samples'}</span></div>
    </footer>
  </section>;
}
