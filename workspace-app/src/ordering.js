// UI order only. Drop helpers never add or remove identities.
export function reorderIds(ids, sourceId, targetId, placement = 'before') {
  if (!Array.isArray(ids) || new Set(ids).size !== ids.length || !ids.includes(sourceId) ||
      !['before', 'after'].includes(placement) || (targetId !== null && !ids.includes(targetId)) || sourceId === targetId) return ids;
  const next = ids.filter(id => id !== sourceId);
  const index = targetId === null ? next.length : next.indexOf(targetId) + (placement === 'after' ? 1 : 0);
  next.splice(index, 0, sourceId);
  return next.every((id, i) => id === ids[i]) ? ids : next;
}

export function moveShortcut(groups, sourceId, section, targetId = null, placement = 'before') {
  const sections = ['pinned', 'main', 'support'];
  if (!sections.includes(section) || !sections.every(key => Array.isArray(groups[key])) || !['before', 'after'].includes(placement)) return groups;
  const ids = sections.flatMap(key => groups[key]);
  if (new Set(ids).size !== ids.length || !ids.includes(sourceId) ||
      (targetId !== null && !groups[section].includes(targetId)) || sourceId === targetId) return groups;
  const next = Object.fromEntries(sections.map(key => [key, groups[key].filter(id => id !== sourceId)]));
  const at = targetId === null ? next[section].length : next[section].indexOf(targetId) + (placement === 'after' ? 1 : 0);
  next[section].splice(at, 0, sourceId);
  return sections.every(key => next[key].length === groups[key].length && next[key].every((id, i) => id === groups[key][i])) ? groups : next;
}

export function protocolShortcutSection(protocol, preferences={}) {
  const section=preferences[protocol.protocol_uuid]?.section;
  if(['pinned','main','support'].includes(section))return section;
  return /^(SingleSpot|ExpandingSpots|SplitFieldCentering)$/i.test((protocol.name||'').split('.').pop().replace(/\s+/g,''))?'support':'main';
}

export function protocolShortcutGroups(protocols, preferences={}) {
  const defaults=new Map(protocols.map((protocol,index)=>[protocol.protocol_uuid,index]));
  const rank=protocol=>Number.isFinite(preferences[protocol.protocol_uuid]?.rank)?preferences[protocol.protocol_uuid].rank:defaults.get(protocol.protocol_uuid);
  const ordered=[...protocols].sort((first,second)=>rank(first)-rank(second));
  return Object.fromEntries(['pinned','main','support'].map(section=>[section,
    ordered.filter(protocol=>protocolShortcutSection(protocol,preferences)===section).map(protocol=>protocol.protocol_uuid)]));
}

export function moveProtocolPreference(preferences, protocols, sourceId, section, targetId=null, placement='before') {
  const groups=protocolShortcutGroups(protocols,preferences);
  const moved=moveShortcut(groups,sourceId,section,targetId,placement);
  if(moved===groups)return preferences;
  const next={...preferences};
  for(const [group,ids] of Object.entries(moved))ids.forEach((id,rank)=>{next[id]={section:group,rank};});
  return next;
}
