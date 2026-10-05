const normalized=value=>String(value).toLowerCase().replace(/[^a-z0-9]/g,'');
export function predicateValueSuggestions(choices,query='',pinnedProtocols=[],isProtocol=false){
  const pins=new Map(pinnedProtocols.map((protocol,index)=>[protocol.acquisition_protocol,{name:protocol.name,rank:index}]));
  const seen=new Set();
  return choices.filter(choice=>choice.type==='string'&&typeof choice.value==='string').filter(choice=>{if(seen.has(choice.value))return false;seen.add(choice.value);return true;}).map(choice=>({...choice,pinned:isProtocol&&pins.has(choice.value),pinName:isProtocol?pins.get(choice.value)?.name:null,rank:isProtocol?(pins.get(choice.value)?.rank??Infinity):Infinity})).filter(choice=>normalized(`${choice.value} ${choice.pinName||''}`).includes(normalized(query))).sort((a,b)=>a.rank-b.rank||a.value.localeCompare(b.value)).slice(0,30);
}
