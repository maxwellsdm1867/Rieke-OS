import {metadataValueSafe,metadataValueText,registeredMetadataField} from './components/metadataValues.js';

export function parseMetadataSearch(query){
  const text=String(query||'').trim(),pair=text.match(/^(.+?)\s*(>=|<=|!=|=|>|<)\s*(.*)$/);
  if(!pair)return {text};
  let value;
  try{value=JSON.parse(pair[3]);}catch{if(/^[\[{"]/.test(pair[3].trim()))return {text,error:'Use valid JSON for pairs, arrays, and quoted text.'};value=pair[3].trim();}
  if(!metadataValueSafe(value))return {text,error:'Numeric comparisons require an exactly representable value. Use quoted text for string identities.'};
  return {text,field:pair[1].trim().toLowerCase(),operator:pair[2],value};
}

function same(left,right){
  if(left===null||right===null)return left===right;
  if(typeof left!==typeof right||Array.isArray(left)!==Array.isArray(right))return false;
  if(Array.isArray(left))return left.length===right.length&&left.every((value,index)=>same(value,right[index]));
  if(typeof left==='object'){const keys=Object.keys(left).sort(),other=Object.keys(right).sort();return keys.length===other.length&&keys.every((key,index)=>key===other[index]&&same(left[key],right[key]));}
  return left===right;
}

export function matchesMetadataSearch(row,search,fields=[]){
  const parsed=typeof search==='string'?parseMetadataSearch(search):search;
  if(parsed.error)return false;
  if(!parsed.field)return `${row.label} ${row.path.join(' ')} ${metadataValueText(row.value)}`.toLowerCase().includes(parsed.text.toLowerCase());
  const field=registeredMetadataField(row.path,fields);
  const aliases=[row.key,row.label,row.path.join('/'),row.path.join('.'),field?.id,field?.label].filter(Boolean).map(value=>value.toLowerCase());
  if(!aliases.includes(parsed.field)||!metadataValueSafe(row.value))return false;
  if(parsed.operator==='=')return same(row.value,parsed.value);
  if(parsed.operator==='!=')return !same(row.value,parsed.value);
  if(typeof row.value!=='number'||typeof parsed.value!=='number')return false;
  return {'>':()=>row.value>parsed.value,'>=':()=>row.value>=parsed.value,'<':()=>row.value<parsed.value,'<=':()=>row.value<=parsed.value}[parsed.operator]();
}
