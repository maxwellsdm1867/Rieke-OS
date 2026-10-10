import {createContext,useContext,useMemo,useState} from 'react';
import {MAX_TRACE_SAMPLES} from './ui/traceGeometry.js';

const Context=createContext(null);
export function normalizeTraceViewPreference(value){
  if(!['whole','sample'].includes(value?.kind)||!Number.isSafeInteger(value.start)||value.start<0||
     !Number.isSafeInteger(value.count)||value.count<1||value.count>MAX_TRACE_SAMPLES)
    return {kind:'whole',start:0,count:MAX_TRACE_SAMPLES};
  return {kind:value.kind,start:value.start,count:value.count};
}

// Presentation only. Protocol owns persistence; trace read authority is separate.
export function TraceViewPreferenceProvider({value,onChange,children}){
  const preference=useMemo(()=>[value,onChange],[value,onChange]);
  return <Context.Provider value={preference}>{children}</Context.Provider>;
}
export function useTraceViewPreference(value,onChange){
  const inherited=useContext(Context);
  const local=useState(()=>normalizeTraceViewPreference());
  return value!==undefined&&onChange?[value,onChange]:inherited??local;
}
