export const MAX_TRACE_SAMPLES=20000;
export function clampWindow(start,count,total,limit=MAX_TRACE_SAMPLES){
  if(!Number.isSafeInteger(total)||total<1)return {start:0,count:0};
  const size=Math.max(1,Math.min(total,limit,Math.floor(Number.isFinite(count)?count:MAX_TRACE_SAMPLES)));
  return {start:Math.max(0,Math.min(total-size,Math.round(Number.isFinite(start)?start:0))),count:size};
}
export function zoomWindow(window,total,factor,anchor=window.start+(window.count-1)/2,limit=MAX_TRACE_SAMPLES){
  const count=Math.max(Math.min(2,total),Math.round(window.count*factor));
  const bounded=clampWindow(0,count,total,limit);
  const fraction=window.count>1?Math.max(0,Math.min(1,(anchor-window.start)/(window.count-1))):.5;
  return clampWindow(anchor-fraction*(bounded.count-1),bounded.count,total,limit);
}
export function dragWindow(window,total,from,to,width,mode='zoom',limit=MAX_TRACE_SAMPLES){
  if(!(width>0)||window.count<1)return window;
  const a=Math.max(0,Math.min(width,from)),b=Math.max(0,Math.min(width,to));
  if(mode==='pan')return clampWindow(window.start-Math.round((b-a)/width*(window.count-1)),window.count,total,limit);
  const first=window.start+Math.round(Math.min(a,b)/width*(window.count-1));
  const last=window.start+Math.round(Math.max(a,b)/width*(window.count-1));
  return clampWindow(first,Math.max(Math.min(2,total),last-first+1),total,limit);
}
export function sampleAtPixel(x,width,count){
  return count>0&&width>0?Math.max(0,Math.min(count-1,Math.round(x/width*(count-1)))):null;
}
export function timeRange(start,count,sampleRate){
  if(!(sampleRate>0)||!Number.isFinite(sampleRate)||count<1)return null;
  return {first:start/sampleRate,last:(start+count-1)/sampleRate,span:(count-1)/sampleRate};
}
export function finiteExtent(values){
  let min=Infinity,max=-Infinity,finiteCount=0;
  for(const value of values || [])if(typeof value==='number'&&Number.isFinite(value)){min=Math.min(min,value);max=Math.max(max,value);finiteCount++;}
  if(!finiteCount)return null;
  const pad=max===min?Math.max(Math.abs(min)*.05,1e-6):(max-min)*.08;
  return {min:min-pad,max:max+pad,finiteCount,missingCount:values.length-finiteCount};
}
export function finiteSegments(values){
  const segments=[];let current=[];
  values.forEach((value,index)=>{if(typeof value==='number'&&Number.isFinite(value))current.push({index,value});else if(current.length){segments.push(current);current=[];}});
  if(current.length)segments.push(current);return segments;
}
// Display geometry only: exact source samples remain owned by the viewer.
// Each physical pixel column retains its first/last and both extrema, emitted
// in recorded time order. A missing sample always ends a connected segment.
export function traceDisplaySegments(values,physicalWidth){
  const count=values?.length||0,columns=Math.ceil(physicalWidth);
  const reduced=Number.isFinite(physicalWidth)&&physicalWidth>0&&count>4*columns;
  const segments=[];
  let segment=[],column=-1,first=-1,last=-1,min=-1,max=-1;
  const flush=()=>{
    if(first<0)return;
    let previous=-1;
    for(const index of [first,min,max,last].sort((a,b)=>a-b))if(index!==previous){segment.push(index);previous=index;}
    first=-1;
  };
  for(let index=0;index<count;index++){
    const value=values[index];
    if(typeof value!=='number'||!Number.isFinite(value)){
      flush();if(segment.length)segments.push(segment);segment=[];column=-1;continue;
    }
    if(!reduced){segment.push(index);continue;}
    const next=Math.min(columns-1,Math.floor(index/(count-1)*physicalWidth));
    if(first<0||next!==column){flush();column=next;first=last=min=max=index;}
    else{last=index;if(value<values[min])min=index;if(value>values[max])max=index;}
  }
  flush();if(segment.length)segments.push(segment);
  return segments;
}
export function ticks(min,max,target=5){
  if(!Number.isFinite(min)||!Number.isFinite(max)||max<min)return [];
  if(max===min)return [min];
  const raw=(max-min)/Math.max(1,target-1),power=10**Math.floor(Math.log10(raw));
  const ratio=raw/power,step=(ratio<=1?1:ratio<=2?2:ratio<=5?5:10)*power;
  const start=Math.ceil(min/step)*step,values=[];
  for(let i=0;i<100;i++){const value=start+i*step;if(value>max+step*1e-9)break;values.push(Math.abs(value)<step*1e-9?0:Number(value.toPrecision(12)));}
  return values;
}
export function formatTick(value,span){
  if(value===0)return '0';
  if(Math.abs(value)>=1e6 || Math.abs(value)<1e-4)return value.toExponential(2);
  const decimals=Math.max(0,Math.min(9,-Math.floor(Math.log10(Math.abs(span)||1))+2));
  return Number(value.toFixed(decimals)).toString();
}
