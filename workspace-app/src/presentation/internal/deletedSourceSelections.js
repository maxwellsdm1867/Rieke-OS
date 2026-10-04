// Remove deleted scientific identities from navigation drafts and selections.
export function pruneDeletedSourceSelections(value,removed){
  const ids=removed instanceof Set?removed:new Set(removed||[]);
  if(typeof value==='string')return ids.has(value)?null:value;
  if(Array.isArray(value))return value.filter(item=>typeof item!=='string'||!ids.has(item)).map(item=>pruneDeletedSourceSelections(item,ids));
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>!ids.has(key)).map(([key,item])=>[key,pruneDeletedSourceSelections(item,ids)]));
  return value;
}
