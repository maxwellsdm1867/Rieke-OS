import {createContext,useContext,useMemo,useState} from 'react';

const Context=createContext(null);
export function normalizeTraceViewPreference(value){
  if(!['whole','sample'].includes(value?.kind)||!Number.isSafeInteger(value.start)||value.start<0||
     !Number.isSafeInteger(value.count)||value.count<1)
    return {kind:'whole',start:0,count:200};
  const selected=value.responseSelection;
  const validSelection=['epoch_uuid','stream_uuid'].every(key=>typeof selected?.[key]==='string'&&selected[key].length>0&&selected[key].length<=128&&selected[key].trim()===selected[key]);
  return {kind:value.kind,start:value.start,count:value.count,...(Number.isFinite(value.amplitude?.min)&&Number.isFinite(value.amplitude?.max)&&value.amplitude.min<value.amplitude.max?{amplitude:{min:value.amplitude.min,max:value.amplitude.max}}:{}),
    ...(validSelection?{responseSelection:{epoch_uuid:selected.epoch_uuid,stream_uuid:selected.stream_uuid}}:{})};
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
