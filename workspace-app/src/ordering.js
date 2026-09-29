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
