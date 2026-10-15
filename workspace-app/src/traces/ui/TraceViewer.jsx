import {useSemanticReset} from '../../useSemanticReset.js';
import {normalizeTraceViewPreference,useTraceViewPreference} from '../traceViewPreference.jsx';
import {useWorkspaceRequestScope} from '../../workspaceRequest.js';
import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Activity,ArrowLeft,ArrowRight,Hand,LoaderCircle,MousePointer2,ZoomIn,ZoomOut} from 'lucide-react';
import {api,number,useResource,requestTraceWindow} from '../../api.js';
import {clampWindow,dragWindow,finiteExtent,formatTick,MAX_TRACE_SAMPLES,sampleAtPixel,ticks,timeRange,traceDisplaySegments,zoomWindow} from './traceGeometry.js';
import './TraceViewer.css';
import {readWholeTrace,MAX_WHOLE_TRACE_CHUNK_SAMPLES} from '../readWholeTrace.js';
import {traceRequestPath,traceCacheRevision,traceResponseMatches} from '../traceReadContext.js';
import {useNavigationLoading,useDelayedLoading} from '../../components/NavigationLoading.jsx';

function paintTrace(canvas,data,amplitude){
  const rect=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio || 1;
  canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,rect.width,rect.height);
  if(!data||!rect.width)return null;
  const autoExtent=finiteExtent(data.values),extent=autoExtent&&amplitude?{...autoExtent,...amplitude}:autoExtent,range=timeRange(data.start,data.values.length,data.sample_rate);
  if(!extent||!range)return null;
  const left=82,right=21,top=25,bottom=57,w=Math.max(1,rect.width-left-right),h=Math.max(1,rect.height-top-bottom);
  const style=getComputedStyle(canvas),color=name=>style.getPropertyValue(name).trim();
  const ink=color('--plot-ink'),grid=color('--plot-grid'),axis=color('--plot-axis'),trace=color('--plot-trace');
  const x=index=>left+(data.values.length>1?index/(data.values.length-1):.5)*w;
  const y=value=>top+(extent.max-value)/(extent.max-extent.min)*h;
  ctx.font='12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';ctx.lineWidth=1;
  for(const value of ticks(extent.min,extent.max,5)){
    const at=y(value);ctx.strokeStyle=grid;ctx.beginPath();ctx.moveTo(left,at);ctx.lineTo(left+w,at);ctx.stroke();
    ctx.fillStyle=ink;ctx.textAlign='right';ctx.textBaseline='middle';ctx.fillText(formatTick(value,extent.max-extent.min),left-10,at);
  }
  const xticks=range.span>0?ticks(range.first,range.last,Math.max(3,Math.min(7,Math.floor(w/110)))):[range.first];
  for(const value of xticks){
    const at=range.span>0?left+(value-range.first)/range.span*w:left+w/2;
    ctx.strokeStyle=grid;ctx.beginPath();ctx.moveTo(at,top);ctx.lineTo(at,top+h);ctx.stroke();
    ctx.fillStyle=ink;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(formatTick(value,range.span || 1/data.sample_rate),at,top+h+10);
  }
  ctx.strokeStyle=axis;ctx.beginPath();ctx.moveTo(left,top);ctx.lineTo(left,top+h);ctx.lineTo(left+w,top+h);ctx.stroke();
  ctx.fillStyle=ink;ctx.font='13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText('Time from stream start (s)',left+w/2,rect.height-4);
  ctx.save();ctx.translate(16,top+h/2);ctx.rotate(-Math.PI/2);ctx.textBaseline='top';ctx.fillText(data.units?`Response (${data.units})`:'Response (unit not recorded)',0,0);ctx.restore();
  ctx.save();ctx.beginPath();ctx.rect(left-1,top-1,w+2,h+2);ctx.clip();ctx.strokeStyle=trace;ctx.lineWidth=1.1;ctx.beginPath();const isolated=[];
  for(const segment of traceDisplaySegments(data.values,w*ratio)){
    const first=segment[0];ctx.moveTo(x(first),y(data.values[first]));
    for(let position=1;position<segment.length;position++){const index=segment[position];ctx.lineTo(x(index),y(data.values[index]));}
    if(segment.length===1)isolated.push(first);
  }
  ctx.stroke();
  ctx.fillStyle=getComputedStyle(ctx.canvas).getPropertyValue('--plot-trace').trim();ctx.beginPath();for(const index of isolated){ctx.moveTo(x(index)+2.5,y(data.values[index]));ctx.arc(x(index),y(data.values[index]),2.5,0,Math.PI*2);}ctx.fill();
  ctx.restore();
  return {left,top,w,h,width:rect.width,height:rect.height,ratio,extent,range,x,y,data};
}

// Keep the canvas mounted; retain the page preference while changing epoch identity.
export default function Trace({epoch,revision=0,readContext=null,viewPreference,onViewPreference}){
  const owner=useWorkspaceRequestScope();
  const [preference,setPreference]=useTraceViewPreference(viewPreference,onViewPreference);
  return <TraceViewer viewPreference={preference} onViewPreference={setPreference} epoch={epoch} revision={revision} readContext={readContext??(owner?epoch?.trace_read_context??owner.traceReadContext:null)??null}/>;
}
Trace.supportsFrozenReadContext=true;
function TraceViewer({epoch,revision,readContext,viewPreference,onViewPreference}){
  const owner=useWorkspaceRequestScope();
  const preference=viewPreference;
  const setPreference=onViewPreference;
  const whole=preference.kind==='whole';
  const imported=['imported_snapshot','imported_cell_snapshot'].includes(readContext?.kind);
  const streams=(epoch?.streams || []).filter(stream=>stream.kind==='responses'&&stream.sample_count>0);
  const savedSelection=preference.responseSelection;
  const preferredStream=savedSelection?.epoch_uuid===epoch?.epoch_uuid&&streams.some(item=>item.uuid===savedSelection.stream_uuid)?savedSelection.stream_uuid:streams[0]?.uuid||'';
  const [selection,setSelection]=useState({epoch:epoch?.epoch_uuid,stream:preferredStream});
  const sameEpoch=selection.epoch===epoch?.epoch_uuid;
  const selectedStream=sameEpoch&&streams.some(item=>item.uuid===selection.stream)?selection.stream:preferredStream;
  const setSelectedStream=stream=>{
    if(!streams.some(item=>item.uuid===stream))return;
    setSelection({epoch:epoch?.epoch_uuid,stream});
    setPreference(normalizeTraceViewPreference({...preference,responseSelection:{epoch_uuid:epoch?.epoch_uuid,stream_uuid:stream}}));
  };
  const setWindowPreference=next=>setPreference(normalizeTraceViewPreference({...next,responseSelection:preference.responseSelection}));
  const stream=streams.find(item=>item.uuid===selectedStream) || streams[0];
  const bounded=whole?{start:0,count:stream?.sample_count||0}:clampWindow(preference.start,preference.count,stream?.sample_count,stream?.sample_count);
  const [mode,setMode]=useState('zoom'),[entryStart,setEntryStart]=useState('0'),[entryCount,setEntryCount]=useState(String(bounded.count));
  const [entryError,setEntryError]=useState('');
  useEffect(()=>{if(!sameEpoch){setSelection({epoch:epoch?.epoch_uuid,stream:preferredStream});setEntryError('');}},[epoch?.epoch_uuid,sameEpoch,preferredStream]);
  const contextKey=traceCacheRevision(revision,readContext);
  // Keep one loaded interval for this mounted viewer. Presentation changes inside
  // it reuse exact samples; identity/authority changes replace the read lifetime.
  const identity=JSON.stringify([contextKey,epoch?.epoch_uuid,epoch?.source_sha256,stream?.uuid,stream?.sample_count,stream?.sample_rate,stream?.units]);
  const [retainedRead,setRetainedRead]=useState(()=>({identity,owner,...bounded}));
  const covered=retainedRead.identity===identity&&retainedRead.owner===owner&&bounded.start>=retainedRead.start&&bounded.start+bounded.count<=retainedRead.start+retainedRead.count;
  const readWindow=covered?retainedRead:{identity,owner,...bounded};
  if(!covered)setRetainedRead(readWindow);
  const chunked=readWindow.count>MAX_TRACE_SAMPLES;
  const requestPath=traceRequestPath(epoch?.epoch_uuid,stream,clampWindow(readWindow.start,readWindow.count,stream?.sample_count),readContext);
  const requestPort=useMemo(()=>{
    if(chunked)return {request:(_path,{signal})=>readWholeTrace({request:owner?.request??api,epochUuid:epoch.epoch_uuid,sourceSha256:epoch.source_sha256,stream,readContext,signal,window:{start:readWindow.start,count:readWindow.count},maxChunkSamples:readWindow.start===0&&readWindow.count===stream.sample_count?MAX_WHOLE_TRACE_CHUNK_SAMPLES:MAX_TRACE_SAMPLES})};
    if(owner||imported||!stream)return undefined;
    return {request:(path,{signal})=>requestTraceWindow(path,{revision:contextKey,signal,epoch,stream,window:readWindow})};
  },[chunked,owner,epoch?.epoch_uuid,epoch?.source_sha256,stream?.uuid,stream?.sample_count,stream?.sample_rate,stream?.units,contextKey,readWindow.start,readWindow.count,imported]);
  const resource=useResource(requestPath,identity,0,{cache:false,requestPort});
  const loaded=traceResponseMatches(resource.data,readContext)&&resource.path===requestPath&&resource.data?.epoch_uuid===epoch?.epoch_uuid&&resource.data?.stream_uuid===stream?.uuid&&resource.data?.start===readWindow.start&&resource.data?.count===readWindow.count&&resource.data?.values?.length===readWindow.count?resource.data:null;
  const data=useMemo(()=>loaded?bounded.start===loaded.start&&bounded.count===loaded.count?loaded:{...loaded,start:bounded.start,count:bounded.count,values:loaded.values instanceof Float64Array?loaded.values.subarray(bounded.start-loaded.start,bounded.start-loaded.start+bounded.count):loaded.values.slice(bounded.start-loaded.start,bounded.start-loaded.start+bounded.count)}:null,[loaded,bounded.start,bounded.count]);
  const getLoadedExtent=useMemo(()=>{let measured;return()=>{if(measured===undefined)measured=finiteExtent(loaded?.values);return measured;};},[loaded]);
  const valid=data&&data.sample_rate>0&&Number.isFinite(data.sample_rate)&&(!imported||data.sample_rate===stream?.sample_rate&&(typeof stream?.units==='string'||stream?.units===null)&&data.units===stream.units)&&data.values?.length===data.count;
  const base=useRef(null),overlay=useRef(null),geometry=useRef(null),cursor=useRef(null),drag=useRef(null),frame=useRef(null),sampleReadout=useRef(null),timeReadout=useRef(null),responseReadout=useRef(null),cursorInput=useRef(null),surface=useRef(null);
  const cursorHelp=useId();
  const authorityKey=traceCacheRevision('paint',readContext);
  const painted=useRef(false),paintedAuthority=useRef(authorityKey);
  const canRetainPaint=painted.current&&paintedAuthority.current===authorityKey;
  const dataRef=useRef(null);dataRef.current=valid?data:null;
  const currentError=resource.path===requestPath?resource.error:null;
  const pending=!!stream&&!currentError&&(resource.loading||resource.path!==requestPath||!resource.data);
  const coordinated=useNavigationLoading(pending);
  const showLoading=useDelayedLoading(pending&&!coordinated);
  const invalidResponse=resource.path===requestPath&&resource.data&&(!data||!valid);
  const range=valid?timeRange(data.start,data.count,data.sample_rate):null;
  const gapCount=useMemo(()=>valid?data.values.reduce((count,value)=>count+(typeof value!=='number'||!Number.isFinite(value)?1:0),0):0,[valid,data]);
  const total=stream?.sample_count || 0;
  const amplitude=whole?null:preference.amplitude;
  const canPan=bounded.count<total||!!amplitude;
  function moveWindow(next,nextAmplitude=amplitude){
    const window=clampWindow(next.start,next.count,total,total);drag.current=null;cursor.current=null;setEntryError('');setWindowPreference({kind:'sample',...window,...(nextAmplitude?{amplitude:nextAmplitude}:{})});
  }
  function resetWhole(){setMode('zoom');setEntryError('');drag.current=null;cursor.current=null;setWindowPreference({kind:'whole',start:preference.start,count:preference.count});}

  const entryWindow=JSON.stringify([epoch?.epoch_uuid,stream?.uuid,bounded.start,bounded.count]);
  useSemanticReset(entryWindow,()=>{setEntryStart(String(bounded.start));setEntryCount(String(bounded.count));});
  function scheduleOverlay(){
    if(frame.current!=null)return;
    frame.current=requestAnimationFrame(()=>{frame.current=null;drawOverlay();});
  }
  function drawOverlay(){
    const el=overlay.current,g=geometry.current,d=dataRef.current;if(!el)return;
    const ctx=el.getContext('2d');ctx.clearRect(0,0,el.width,el.height);
    if(!g||!d||mode==='pan')return;
    ctx.setTransform(g.ratio,0,0,g.ratio,0,0);
    if(drag.current?.kind==='zoom'){
      const a=drag.current.origin,b=drag.current.current;
      const x=g.left+Math.min(a.x,b.x),y=g.top+Math.min(a.y,b.y),w=Math.max(1,Math.abs(b.x-a.x)),h=Math.max(1,Math.abs(b.y-a.y));
      ctx.fillStyle=getComputedStyle(ctx.canvas).getPropertyValue(mode==='zoom'?'--plot-selection':'--plot-pan').trim();
      ctx.fillRect(x,y,w,h);
      ctx.strokeStyle=getComputedStyle(ctx.canvas).getPropertyValue('--plot-cursor').trim();ctx.lineWidth=1;ctx.setLineDash([4,3]);
      ctx.strokeRect(x,y,w,h);ctx.setLineDash([]);
    }
    if(cursor.current==null)return;
    const index=Math.max(0,Math.min(d.count-1,cursor.current)),value=d.values[index],x=g.x(index),finite=typeof value==='number'&&Number.isFinite(value);
    ctx.strokeStyle=getComputedStyle(ctx.canvas).getPropertyValue('--plot-cursor').trim();ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,g.top);ctx.lineTo(x,g.top+g.h);
    if(finite&&value>=g.extent.min&&value<=g.extent.max){const y=g.y(value);ctx.moveTo(g.left,y);ctx.lineTo(g.left+g.w,y);}ctx.stroke();ctx.setLineDash([]);
    if(finite&&value>=g.extent.min&&value<=g.extent.max){ctx.fillStyle=getComputedStyle(ctx.canvas).getPropertyValue('--plot-trace').trim();ctx.beginPath();ctx.arc(x,g.y(value),3,0,Math.PI*2);ctx.fill();}
    const absolute=d.start+index,time=absolute/d.sample_rate;
    if(sampleReadout.current)sampleReadout.current.textContent=number(absolute);
    if(timeReadout.current)timeReadout.current.textContent=`${String(time)} s`;
    if(responseReadout.current)responseReadout.current.textContent=`${finite?String(value):'Missing sample'}${finite&&d.units?` ${d.units}`:''}`;
    if(cursorInput.current&&document.activeElement!==cursorInput.current)cursorInput.current.value=String(absolute);
  }
  useLayoutEffect(()=>{
    if(!base.current||!overlay.current){painted.current=false;return;}
    cursor.current=null;
    if(drag.current?.kind!=='pan'||drag.current.identity!==identity||drag.current.owner!==owner||pending)drag.current=null;
    for(const ref of [sampleReadout,timeReadout,responseReadout])if(ref.current)ref.current.textContent='—';
    if(cursorInput.current)cursorInput.current.value=valid?String(data.start):'';
    let resizedFrame,lastSize;
    const draw=()=>{
      // A pending window keeps its bitmap only within the same frozen authority.
      // Failed/invalid responses clear it; only validated samples get new axes.
      geometry.current=valid?paintTrace(base.current,data,amplitude):pending&&paintedAuthority.current===authorityKey?null:paintTrace(base.current,null);
      if(valid){painted.current=true;paintedAuthority.current=authorityKey;}else if(!pending||paintedAuthority.current!==authorityKey){painted.current=false;paintedAuthority.current=authorityKey;}
      const rect=base.current.getBoundingClientRect(),ratio=window.devicePixelRatio || 1;
      lastSize={width:rect.width,height:rect.height,ratio};
      overlay.current.width=Math.round(rect.width*ratio);overlay.current.height=Math.round(rect.height*ratio);
      scheduleOverlay();
    };
    const resize=()=>{cancelAnimationFrame(resizedFrame);resizedFrame=requestAnimationFrame(draw);};
    const resizeIfChanged=(immediate=false)=>{
      const rect=base.current.getBoundingClientRect(),ratio=window.devicePixelRatio || 1;
      if(lastSize?.width!==rect.width||lastSize?.height!==rect.height||lastSize?.ratio!==ratio){
        if(immediate){cancelAnimationFrame(resizedFrame);draw();}else resize();
      }
    };
    // observe() delivers an initial notification even though draw() already
    // painted this size. Data and appearance changes still always repaint.
    const windowResize=()=>resizeIfChanged();
    draw();const observer=new ResizeObserver(()=>resizeIfChanged(true));observer.observe(base.current);window.addEventListener('resize',windowResize);window.addEventListener('disco:appearance',resize);
    return()=>{observer.disconnect();window.removeEventListener('resize',windowResize);window.removeEventListener('disco:appearance',resize);cancelAnimationFrame(resizedFrame);if(frame.current!=null){cancelAnimationFrame(frame.current);frame.current=null;}};
  },[data,valid,pending,authorityKey,amplitude,identity,owner]);
  function local(event){const rect=overlay.current.getBoundingClientRect(),g=geometry.current;return g?{rawX:event.clientX-rect.left-g.left,rawY:event.clientY-rect.top-g.top,x:Math.max(0,Math.min(g.w,event.clientX-rect.left-g.left)),y:Math.max(0,Math.min(g.h,event.clientY-rect.top-g.top)),inside:event.clientX-rect.left>=g.left&&event.clientX-rect.left<=g.left+g.w&&event.clientY-rect.top>=g.top&&event.clientY-rect.top<=g.top+g.h}:null;}
  function panTo(gesture,at){
    if(gesture.identity!==identity||gesture.owner!==owner)return;
    const shiftX=(at.rawX-gesture.origin.rawX)/gesture.width*(gesture.window.count-1);
    const next=clampWindow(gesture.window.start-Math.round(shiftX),gesture.window.count,total,total);
    const shiftY=(at.rawY-gesture.origin.rawY)/gesture.height*(gesture.amplitude.max-gesture.amplitude.min);
    const nextAmplitude={min:gesture.amplitude.min+shiftY,max:gesture.amplitude.max+shiftY};
    cursor.current=null;setEntryError('');
    setWindowPreference({kind:'sample',...next,amplitude:nextAmplitude});
  }
  useEffect(()=>{cursor.current=null;drag.current=null;if(overlay.current)scheduleOverlay();},[mode]);
  function pointerMove(event){
    const at=local(event);if(!at||!dataRef.current)return;
    if(drag.current){drag.current.current=at;if(drag.current.kind==='pan'){panTo(drag.current,at);return;}}
    if(mode==='pan')return;
    if(at.inside||drag.current)cursor.current=sampleAtPixel(at.x,geometry.current.w,dataRef.current.count);scheduleOverlay();
  }
  function pointerDown(event){
    const at=local(event);if(event.button!==0||pending||!dataRef.current||!at?.inside||mode==='pan'&&!canPan)return;
    surface.current.focus({preventScroll:true});event.currentTarget.setPointerCapture(event.pointerId);
    const g=geometry.current;
    drag.current={kind:mode,origin:at,current:at,identity,owner,window:{...bounded},amplitude:{min:g.extent.min,max:g.extent.max},width:g.w,height:g.h};
    cursor.current=mode==='pan'?null:sampleAtPixel(at.x,g.w,data.count);scheduleOverlay();
  }
  function pointerUp(event){
    if(!drag.current)return;const current=drag.current;drag.current=null;
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    const g=geometry.current,from=current.origin,to=local(event)||current.current;
    if(current.kind==='pan'){panTo(current,to);scheduleOverlay();return;}
    const dx=Math.abs(to.x-from.x),dy=Math.abs(to.y-from.y);
    if(dx<5&&dy<5){scheduleOverlay();return;}
    const next=dx>=5?dragWindow(bounded,total,from.x,to.x,g.w,mode,total):bounded;
    let nextAmplitude=amplitude;
    if(mode==='zoom'&&dy>=5){
      const at=y=>g.extent.max-y/g.h*(g.extent.max-g.extent.min);
      nextAmplitude={min:at(Math.max(from.y,to.y)),max:at(Math.min(from.y,to.y))};
    }else if(mode==='pan'&&amplitude){
      const shift=(to.y-from.y)/g.h*(amplitude.max-amplitude.min);
      nextAmplitude={min:amplitude.min+shift,max:amplitude.max+shift};
    }
    moveWindow(next,nextAmplitude);
  }

  function zoom(factor){
    const anchor=cursor.current==null?undefined:bounded.start+cursor.current;
    let nextAmplitude=amplitude;
    if(amplitude){
      const center=amplitude.min/2+amplitude.max/2,half=(amplitude.max-amplitude.min)*factor/2;
      nextAmplitude={min:center-half,max:center+half};
      const full=getLoadedExtent();
      if(!Number.isFinite(nextAmplitude.min)||!Number.isFinite(nextAmplitude.max)||factor>1&&full&&nextAmplitude.min<=full.min&&nextAmplitude.max>=full.max)nextAmplitude=null;
    }
    moveWindow(zoomWindow(bounded,total,factor,anchor,total),nextAmplitude);
  }
  function keyDown(event){
    if(!valid||pending)return;
    if(event.key==='Escape'){drag.current=null;scheduleOverlay();return;}
    if(['ArrowLeft','ArrowRight'].includes(event.key)){
      event.preventDefault();const direction=event.key==='ArrowLeft'?-1:1;
      if(event.shiftKey&&canPan)moveWindow({...bounded,start:bounded.start+direction*Math.max(1,Math.round(bounded.count/2))});
      else{cursor.current=Math.max(0,Math.min(data.count-1,(cursor.current??0)+direction));scheduleOverlay();}
    }else if(['+','=','-','Home'].includes(event.key)){event.preventDefault();if(event.key==='Home')resetWhole();else if(event.key!=='-'||!whole)zoom(event.key==='-'?2:.5);}
  }
  function submitWindow(event){
    event.preventDefault();const start=Number(entryStart),count=Number(entryCount);
    if(!entryStart.trim()||!entryCount.trim()||!Number.isSafeInteger(start)||!Number.isSafeInteger(count)||start<0||start>=total||count<1||count>total){setEntryError(`Use a start index from 0 to ${number(total-1)} and 1–${number(total)} samples.`);return;}
    moveWindow({start,count});
  }
  return <section className="trace-viewer trace-section" aria-label="Recorded response viewer">
    <header className="tv-controls" aria-label="Response and viewing controls">
      <div className="tv-response-line">
        <h3 title="All recorded samples are retained. The display follows screen resolution; cursor values remain exact."><Activity size={14}/> Response</h3>
        <div className="tv-streams" aria-label="Response stream">
          {streams.length===1?<span>{stream.device} · {stream.units||'unit not recorded'}</span>:streams.map((item,index)=><button key={item.uuid} aria-pressed={stream?.uuid===item.uuid} aria-label={`Response ${index+1}: ${item.device} · ${item.units||'unit not recorded'}`} title={item.uuid} onClick={()=>{setSelectedStream(item.uuid);setEntryError('');drag.current=null;cursor.current=null;}}>{item.device}{streams.filter(other=>other.device===item.device).length>1?` ${index+1}`:''} · {item.units||'unit not recorded'}</button>)}
        </div>
        <span className="tv-recording-info">{stream?`${number(valid?data.sample_rate:stream.sample_rate)} Hz`:'No response stream'}</span>
      </div>
      <div className="tv-window-controls">
        <div className="tv-modes" aria-label="Trace extent"><button aria-pressed={whole} className={whole?'active':''} onClick={resetWhole}>Whole epoch</button><button aria-pressed={!whole} className={!whole?'active':''} onClick={()=>moveWindow({start:0,count:200},null)}>Sample</button></div>
        {!whole&&<form className="tv-window-fields" onSubmit={submitWindow}>
          <label>Start<input aria-label="Start sample" disabled={!stream} type="number" value={entryStart} min="0" max={Math.max(0,total-1)} step="1" onChange={event=>setEntryStart(event.target.value)}/></label>
          <label>Count<input aria-label="Sample count" disabled={!stream} type="number" value={entryCount} min="1" max={total} step="1" onChange={event=>setEntryCount(event.target.value)}/></label>
          <button disabled={!stream||pending} type="submit">Apply</button>
        </form>}
        {!whole&&<div className="tv-window-step"><button aria-label="Previous window" title="Previous window" disabled={!stream||pending||bounded.start===0} onClick={()=>moveWindow({...bounded,start:bounded.start-bounded.count})}><ArrowLeft size={14}/></button><button aria-label="Next window" title="Next window" disabled={!stream||pending||bounded.start+bounded.count>=total} onClick={()=>moveWindow({...bounded,start:bounded.start+bounded.count})}><ArrowRight size={14}/></button></div>}
        <div className="tv-modes" aria-label="Drag interaction"><button className={mode==='zoom'?'active':''} aria-pressed={mode==='zoom'} disabled={!stream||pending||!valid} onClick={()=>setMode('zoom')} title="Drag to zoom"><MousePointer2 size={13}/> Zoom</button><button className={mode==='pan'?'active':''} aria-pressed={mode==='pan'} disabled={!stream||pending||!valid||!canPan} onClick={()=>setMode('pan')}><Hand size={13}/> Pan</button></div>
        <div className="tv-zoom-buttons"><button disabled={!stream||pending||!valid||bounded.count<=Math.min(2,total)} onClick={()=>whole?setMode('zoom'):zoom(.5)} title={whole?'Drag on the trace to choose a zoom window':'Zoom in around cursor or window center'} aria-label="Zoom in"><ZoomIn size={15}/></button><button disabled={!stream||pending||!valid||whole||bounded.count>=total&&!amplitude} onClick={()=>zoom(2)} title="Zoom out toward the whole epoch" aria-label="Zoom out"><ZoomOut size={15}/></button></div>
      </div>
      {entryError&&<p className="tv-warning" role="alert">{entryError}</p>}
    </header>
    <div ref={surface} data-epoch-arrows="ignore" className={`tv-plot tv-${mode}`} tabIndex={0} role="group" aria-label="Trace plot. Left/Right move the sample cursor. Shift and Left/Right pan. Plus and minus zoom. Home resets." onKeyDown={keyDown}>
      <canvas ref={base} className="tv-base" aria-hidden="true"/><canvas ref={overlay} className="tv-overlay" aria-hidden="true" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{drag.current=null;scheduleOverlay();}}/>
      {!stream&&<div className="tv-status">This epoch has no indexed response stream.</div>}
      {valid&&gapCount===data.count&&<div className="tv-status" role="status">No finite samples in this window.</div>}
      {pending&&canRetainPaint&&<span className="tv-previous-trace">Previous trace · inactive</span>}
      {showLoading&&<div className="tv-status tv-loading" role="status"><span><LoaderCircle size={16}/> Loading selected samples{canRetainPaint?' · previous trace is inactive':'…'}</span></div>}
      {currentError&&<div className="tv-status tv-error" role="alert">{currentError}<button onClick={resource.reload}>Retry trace</button></div>}
      {invalidResponse&&<div className="tv-status tv-error" role="alert">Trace identity, sample rate, units or window does not match the request. No plot is shown.<button onClick={resource.reload}>Retry trace</button></div>}
    </div>
    <div className="tv-readout"><output aria-live="off" aria-label="Recorded sample readout" aria-describedby={cursorHelp}><span className="tv-measure"><small>Sample</small><span className="tv-value" ref={sampleReadout} tabIndex={0} aria-label="Recorded sample index">—</span></span><span className="tv-measure"><small>Time</small><span className="tv-value" ref={timeReadout} tabIndex={0} aria-label="Time from stream start in seconds">—</span></span><span className="tv-measure"><small>Response</small><span className="tv-value" ref={responseReadout} tabIndex={0} aria-label="Recorded response and scientific units">—</span></span></output><label>Sample cursor<input ref={cursorInput} type="number" step="1" min={bounded.start} max={bounded.start+bounded.count-1} disabled={!valid||pending} aria-label="Exact sample index for cursor" onChange={event=>{const sample=Number(event.target.value);if(event.target.value!==''&&Number.isInteger(sample)&&sample>=bounded.start&&sample<bounded.start+bounded.count){cursor.current=sample-bounded.start;scheduleOverlay();}}}/></label></div>
    <div className="tv-footer"><div className="tv-range" tabIndex={0} aria-label="Available trace window" title={stream?`Samples ${number(bounded.start)}–${number(bounded.start+bounded.count-1)} · zero-based, inclusive`:undefined}><span>{range?`${formatTick(range.first,1/data.sample_rate)}–${formatTick(range.last,1/data.sample_rate)} s`:'—'}</span><small>{stream?`${number(bounded.count)} / ${number(total)} samples`:'—'}</small>{stream&&<span aria-label="Selected sample bounds">Start {number(bounded.start)} · Stop {number(bounded.start+bounded.count-1)} (inclusive)</span>}{amplitude&&<span aria-label="Selected response bounds">{formatTick(amplitude.min,amplitude.max-amplitude.min)}–{formatTick(amplitude.max,amplitude.max-amplitude.min)} {data?.units||stream?.units||''}</span>}</div><span className="tv-shortcuts">← → cursor · Shift ← → pan · + / − zoom · Home whole</span></div>
    <p id={cursorHelp} className="tv-cursor-help">Drag a rectangle to zoom. Move over the plot or use the sample cursor to read an exact recorded value.</p>
    <div className="tv-gap-notice" role="status" tabIndex={gapCount>0?0:undefined}>{gapCount>0?`${number(gapCount)} missing or non-finite samples appear as gaps; they are not plotted as zero.`:''}</div>
  </section>;
}
