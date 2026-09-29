export function importReadiness({suggestions=[],protocols=[],preferences={}}){
  const byProtocol=new Map(suggestions.filter(item=>['pending','stale','applied'].includes(item.status)).map(item=>[item.protocol_uuid,item]));
  const ordered=[...protocols].sort((a,b)=>(preferences[a.protocol_uuid]?.rank??999)-(preferences[b.protocol_uuid]?.rank??999));
  const pinned=ordered.filter(p=>preferences[p.protocol_uuid]?.section==='pinned').map(p=>({protocol:p,suggestion:byProtocol.get(p.protocol_uuid)}));
  const pinnedIds=new Set(pinned.map(row=>row.protocol.protocol_uuid));
  const other=[...byProtocol.values()].filter(s=>!pinnedIds.has(s.protocol_uuid)).sort((a,b)=>({pending:0,stale:1,applied:2}[a.status])-({pending:0,stale:1,applied:2}[b.status]));
  return {pinned,other,ready:suggestions.filter(s=>s.status==='pending').length,added:suggestions.filter(s=>s.status==='applied').length,stale:suggestions.filter(s=>s.status==='stale').length};
}

export function suggestionDates(suggestion){
  const changes=suggestion.diff_summary?.cell_changes||{};
  return [...new Set(['added','updated','removed'].flatMap(key=>(changes[key]||[]).map(cell=>cell.date).filter(Boolean)))].sort();
}
