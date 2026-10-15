// Versioned, bounded framing only. Request identity and scientific authority are
// still admitted by readWholeTrace after this decoder supplies exact sample views.
export const TRACE_BINARY_TYPE='application/vnd.disco.trace-f64le.v1';
const MAX_HEADER_BYTES=65536,MAX_SAMPLES=500000;
const littleEndian=new Uint8Array(new Uint16Array([1]).buffer)[0]===1;
const integer=(value,min,max)=>Number.isSafeInteger(value)&&value>=min&&value<=max;
const invalid=()=>{throw Error('Invalid binary trace response. No plot is shown.');};
export function decodeTraceBinary(buffer){
  if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<8||buffer.byteLength>8+MAX_HEADER_BYTES+7+MAX_SAMPLES*8)invalid();
  const bytes=new Uint8Array(buffer),view=new DataView(buffer);
  if(bytes[0]!==68||bytes[1]!==84||bytes[2]!==70||bytes[3]!==49)invalid();
  const headerLength=view.getUint32(4,true),payloadStart=Math.ceil((8+headerLength)/8)*8;
  if(!integer(headerLength,1,MAX_HEADER_BYTES)||payloadStart>buffer.byteLength)invalid();
  let header;
  try{header=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes.subarray(8,8+headerLength)));}catch{invalid();}
  if(!header||typeof header!=='object'||Array.isArray(header)||Object.hasOwn(header,'values')||
    !integer(header.start,0,Number.MAX_SAFE_INTEGER)||!integer(header.count,1,MAX_SAMPLES)||
    !integer(header.total_samples,1,Number.MAX_SAFE_INTEGER)||!Number.isSafeInteger(header.start+header.count)||
    header.start+header.count>header.total_samples||!Array.isArray(header.windows)||!integer(header.windows.length,1,5)||
    payloadStart+header.count*8!==buffer.byteLength)invalid();
  for(let index=8+headerLength;index<payloadStart;index++)if(bytes[index]!==0)invalid();
  let sampleOffset=0;
  for(const window of header.windows){
    if(!window||typeof window!=='object'||Array.isArray(window)||Object.hasOwn(window,'values')||
      !integer(window.count,1,100000)||window.start!==header.start+sampleOffset||
      window.byte_offset!==sampleOffset*8||window.byte_length!==window.count*8||sampleOffset+window.count>header.count)invalid();
    sampleOffset+=window.count;
  }
  if(sampleOffset!==header.count)invalid();
  const values=littleEndian?new Float64Array(buffer,payloadStart,header.count):new Float64Array(header.count);
  for(let index=0;index<values.length;index++){
    if(!littleEndian)values[index]=view.getFloat64(payloadStart+index*8,true);
    if(!Number.isFinite(values[index]))invalid();
  }
  return {...header,windows:header.windows.map(window=>({...window,values:values.subarray(window.byte_offset/8,(window.byte_offset+window.byte_length)/8)}))};
}
