// Facts belong only to exact locally decoded sample views. Wire metadata never
// supplies these facts. No samples are retained here: WeakMap keys share the
// admitted response lifetime, and ordinary/custom arrays are always scanned.
const decodedStatistics=new WeakMap();

function scan(values,finiteOnly=false){
  let min=Infinity,max=-Infinity,finiteCount=0;
  for(let index=0;index<(values?.length||0);index++){
    const value=values[index];
    if(typeof value==='number'&&Number.isFinite(value)){
      min=Math.min(min,value);max=Math.max(max,value);finiteCount++;
    }else if(finiteOnly)throw Error('Invalid binary trace response. No plot is shown.');
  }
  return Object.freeze({min,max,finiteCount,missingCount:(values?.length||0)-finiteCount});
}

// Only the binary decoder calls this after constructing a transport-owned response view.
// Admitted views are treated as read-only by trace owners; no producer-owned or
// JSON array gets persistent statistics merely because it is a Float64Array.
export function validateDecodedTraceValues(values){
  const statistics=scan(values,true);
  decodedStatistics.set(values,statistics);
}

// readWholeTrace calls this after it has admitted each contiguous window and
// either joined its exact samples or made the single-buffer whole-interval view.
export function combineDecodedTraceStatistics(values,parts){
  let min=Infinity,max=-Infinity,finiteCount=0,missingCount=0;
  for(const part of parts){
    const facts=decodedStatistics.get(part);
    if(!facts)return;
    min=Math.min(min,facts.min);max=Math.max(max,facts.max);
    finiteCount+=facts.finiteCount;missingCount+=facts.missingCount;
  }
  if(finiteCount+missingCount!==values.length)return;
  decodedStatistics.set(values,Object.freeze({min,max,finiteCount,missingCount}));
}

export function traceSampleStatistics(values){return decodedStatistics.get(values)||scan(values);}
export function traceStatisticsExtent({min,max,finiteCount,missingCount}){
  if(!finiteCount)return null;
  const pad=max===min?Math.max(Math.abs(min)*.05,1e-6):(max-min)*.08;
  return {min:min-pad,max:max+pad,finiteCount,missingCount};
}
