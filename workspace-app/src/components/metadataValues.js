export function metadataHasEncodedInteger(value){
  if(typeof value==='string'&&/^-?\d+$/.test(value)){try{return BigInt(value)>BigInt(Number.MAX_SAFE_INTEGER)||BigInt(value)<BigInt(Number.MIN_SAFE_INTEGER);}catch{return false;}}
  if(Array.isArray(value))return value.some(metadataHasEncodedInteger);
  if(value&&typeof value==='object')return Object.values(value).some(metadataHasEncodedInteger);
  return false;
}
export function metadataValueSafe(value){
  if(value===undefined)return false;
  if(typeof value==='number')return Number.isFinite(value)&&(!Number.isInteger(value)||Number.isSafeInteger(value));
  if(Array.isArray(value))return value.every(metadataValueSafe);
  if(value&&typeof value==='object')return Object.values(value).every(metadataValueSafe);
  return true;
}
export function metadataValueText(value){
  if(value===undefined)return 'Not recorded';
  if(value===null)return 'null';
  if(value==='')return '"" (empty text)';
  if(typeof value==='object')return JSON.stringify(value,null,2);
  return String(value);
}
export function metadataRows(value,path=[]){
  if(!value||typeof value!=='object'||Array.isArray(value))return [];
  const base=path.length;
  function walk(object,prefix){return Object.entries(object).flatMap(([key,child])=>{
    const keys=[...prefix,key];
    if(child&&typeof child==='object'&&!Array.isArray(child)&&Object.keys(child).length)return walk(child,keys);
    return [{key,path:keys,label:keys.slice(base).join('.'),value:child}];
  });}
  return walk(value,path);
}
function predicateLiteralText(value){return Array.isArray(value)?`[${value.map(predicateLiteralText).join(', ')}]`:JSON.stringify(value);}
export function metadataPredicateValueSupported(value,depth=0){
  if(depth>6||!metadataValueSafe(value)||metadataHasEncodedInteger(value))return false;
  const supported=Array.isArray(value)?value.length<=100&&value.every(item=>metadataPredicateValueSupported(item,depth+1)):value===null||['string','number','boolean'].includes(typeof value);
  return supported&&predicateLiteralText(value).length<=4096;
}

export function registeredMetadataField(path,fields=[]){
  return fields.find(field=>{
    if(!field.id.includes('/'))return path.length===1&&field.path===path[0];
    try{
      const parts=field.id.split('/').map(part=>decodeURIComponent(part).replace(/~1/g,'/').replace(/~0/g,'~'));
      return parts.length===path.length&&parts.every((part,index)=>part===path[index]);
    }catch{return false;}
  });
}
export function metadataClipboard(row,kind,field){
  if(kind==='key')return row.key;
  if(kind==='field'){if(!field)throw new Error('This metadata key has no registered predicate field.');return field.id;}
  if(!metadataValueSafe(row.value))throw new Error('This value cannot be copied exactly from the browser. Inspect the original source metadata.');
  if(kind==='text')return typeof row.value==='string'?row.value:JSON.stringify(row.value,null,2);
  if(kind==='value')return JSON.stringify(row.value,null,2);
  if(kind==='pair')return JSON.stringify({[row.key]:row.value},null,2);
  if(kind==='setting')return `${field?.id || row.path?.join('.') || row.key} = ${JSON.stringify(row.value)}`;
  if(kind==='predicate'){
    if(!field)throw new Error('This metadata key has no registered predicate field.');
    if(!metadataPredicateValueSupported(row.value))throw new Error('This value is not supported in source predicates.');
    return JSON.stringify(row.value===null?{field:field.id,operator:'is_null'}:{field:field.id,operator:'eq',value:row.value},null,2);
  }
  throw new Error('Unknown clipboard action.');
}
