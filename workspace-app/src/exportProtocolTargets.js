import {isTypingProtocol} from './protocolOverviewModel.js';
export function exportProtocolGroups(protocols,preferences={},initialId=null){
  const pinned=[],other=[];
  for(const protocol of protocols){
    if(preferences[protocol.protocol_uuid]?.section==='pinned')pinned.push(protocol);
    else if(!isTypingProtocol(protocol)||protocol.protocol_uuid===initialId)other.push(protocol);
  }
  return [{label:'Pinned protocols',protocols:pinned},{label:'Other experiments · pin when updated',protocols:other}].filter(group=>group.protocols.length);
}
export function pinProtocolPreference(preferences,id){
  if(preferences[id]?.section==='pinned')return preferences;
  const ranks=Object.values(preferences).filter(item=>item?.section==='pinned').map(item=>item.rank).filter(Number.isFinite);
  return {...preferences,[id]:{...preferences[id],section:'pinned',rank:Math.max(-1,...ranks)+1}};
}
