// Composite identities are recipes, not expressions. Values are grouped by the server.
export const jointId = components => {
  if (!Array.isArray(components) || components.length < 2 || components.length > 6 ||
      new Set(components).size !== components.length || components.some(id =>
        typeof id !== 'string' || !id || id.startsWith('joint/') || /[\r\n\0]/.test(id))) {
    throw new Error('Choose 2–6 different recorded fields.');
  }
  return 'joint/' + components.map(encodeURIComponent).join('+');
};

export function jointComponents(id) {
  if (!id?.startsWith('joint/')) return [];
  try {
    const parts = id.slice(6).split('+').map(decodeURIComponent);
    return jointId(parts) === id ? parts : [];
  } catch { return []; }
}

export const shortFieldLabel = field => (field?.label || field?.id || 'Field').replace(/ · mean \/ SD$/, '');

export function jointDefinition(id, fields) {
  const components = jointComponents(id), byId = new Map(fields.map(field => [field.id, field]));
  if (!components.length || components.some(key => !byId.has(key))) return null;
  return {id, components, label:components.map(key => shortFieldLabel(byId.get(key))).join(' + '),
    category:'Combinations', path:components.join(' + '), grouping_role:'primary',
    grouping_hint:'One branch only when every component matches. Missing values stay distinct.'};
}

export function combineLevels(order, components) {
  const id = jointId(components);
  const first = order.findIndex(key => components.includes(key) || key === id);
  const next = order.filter(key => !components.includes(key) && key !== id);
  const index = first < 0 ? next.length : order.slice(0, first).filter(key => !components.includes(key) && key !== id).length;
  next.splice(index, 0, id);
  if (next.length > 8) throw new Error('Remove a level first; the tree supports eight levels.');
  return next;
}

export function uncombineLevel(order,id){
  const components=jointComponents(id),index=order.indexOf(id);
  if(index<0||!components.length)throw new Error('Choose a combined level to separate.');
  const before=order.slice(0,index).filter(key=>!components.includes(key));
  const after=order.slice(index+1).filter(key=>!components.includes(key));
  const next=[...before,...components,...after];
  if(next.length>8)throw new Error('Remove a level first; separating these fields would exceed eight levels.');
  return next;
}
