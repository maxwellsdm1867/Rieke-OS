// Labels are presentation only. Node keys/field IDs remain untouched for grouping.
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const opaque=value=>typeof value==='string'&&(uuid.test(value)||value.startsWith('joint/'));
const text=value=>JSON.stringify(value);
const compactTime=value=>String(value).replace(/(\d{2}:\d{2}:\d{2})[:.]\d{3,9}$/, '$1');
export function readableField(label,field){
  if(label&&!opaque(label)&&label!==field)return label;
  if(field?.startsWith('joint/'))return 'Combined fields';
  const standard={cell:'Cell',group:'Epoch group',block:'Epoch block',protocol:'Acquisition protocol',date:'Recording date'};
  if(standard[field])return standard[field];
  if(!field)return label || 'Recorded field';
  try{return decodeURIComponent(field.split('/').at(-1)).replace(/~1/g,'/').replace(/~0/g,'~').replace(/([a-z0-9])([A-Z])/g,'$1 $2');}
  catch{return 'Recorded field';}
}
export function componentLabel(part){return readableField(part.label,part.field).replace(/ · mean \/ SD$/,'');}
export function componentValue(part){
  if(part.missing)return 'Not recorded';
  if(part.display_value!=null&&!opaque(part.display_value))return String(part.display_value);
  if(part.value===null)return 'null (recorded)';
  if(opaque(part.value))return `${readableField(null,part.field)} · label not recorded`;
  return text(part.value) ?? 'Not recorded';
}
export function branchLabel(node,parentField){
  if(node.components?.length)return node.components.map(part=>`${componentLabel(part)}: ${componentValue(part)}`).join(' · ');
  if(node.missing)return 'Not recorded';
  if(node.label!=null&&!opaque(node.label))return parentField==='block'?compactTime(node.label):String(node.label);
  if(opaque(node.value))return `${readableField(null,parentField)} · label not recorded`;
  if(node.value===null)return 'null (recorded)';
  if(node.value!==undefined&&typeof node.value!=='object')return text(node.value);
  if(Array.isArray(node.value))return JSON.stringify(node.value);
  return node.value!==undefined?'Recorded value':'All epochs';
}
export function branchTooltip(node,parentField){
  if(node.components?.length)return node.components.map(part=>`${part.field}: ${part.missing?'not recorded':text(part.value)}`).join('\n');
  return [parentField&&`Field: ${parentField}`,parentField==='block'&&node.label&&`Recorded label: ${node.label}`,node.value!==undefined&&`Source value: ${text(node.value)}`].filter(Boolean).join('\n');
}
export function epochLeafLabel(epoch){
  if(epoch.label&&!opaque(epoch.label)&&epoch.label!==epoch.epoch_uuid?.slice(0,8))return compactTime(epoch.label).replace(/^Epoch\s+/i,'');
  const ordinal=epoch.epoch_number!=null?String(epoch.epoch_number):'—';
  const time=epoch.start_time?.split(/[ T]/)[1]?.slice(0,8);
  return `${ordinal}${time?` · ${time}`:''}`;
}
