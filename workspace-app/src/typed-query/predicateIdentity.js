// Object key order is not part of predicate meaning; array order stays explicit.
export function predicateIdentity(value){
  if(Array.isArray(value))return `[${value.map(predicateIdentity).join(',')}]`;
  if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${predicateIdentity(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
