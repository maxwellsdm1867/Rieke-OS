// Presentation only: keep recorded labels and UUID identity intact.
export function recordedCellType(cell={}) {
  const value=cell.cell_type || cell.type;
  return value!=null && String(value).trim() ? String(value) : 'Unclassified';
}
export function isUnclassifiedType(type) {
  return /^(unclassified|unknown|not recorded|unknown cell type)$/i.test(type.trim());
}
export function distinctCells(cells=[]) {
  const seen=new Set();
  return cells.filter(cell=>{
    const id=cell.cell_uuid || cell.uuid;
    if(!id)return true;
    if(seen.has(id))return false;
    seen.add(id);return true;
  });
}
// Exact presentation aliases only; never infer a type from a cell name or candidate label.
const neutral=shape=>({shape,color:shape==='generic'?'var(--cell-unknown)':'var(--ink-muted)'});
const normalizeTypePart=value=>value.trim().toLowerCase().replace(/[ _-]+/g,'-').replace(/-cells?$/,'');
const families={rgc:'ganglion',ganglion:'ganglion','retinal-ganglion':'ganglion',bipolar:'bipolar',bc:'bipolar',amacrine:'amacrine',ac:'amacrine',horizontal:'horizontal',hc:'horizontal',photoreceptor:'photoreceptor',photoreceptors:'photoreceptor'};
const polarized=(shape,polarity,variant)=>({shape,polarity,color:`var(--cell-${polarity})`,...(variant?{variant}:{})});
function ganglionPresentation(key) {
  const match=/^(on|off)-(midget|parasol)$/.exec(key);
  if(match)return polarized(match[2]==='midget'?'midget':'ganglion',match[1]);
  if(key==='small-bistratified')return {shape:'bistratified',color:'var(--cell-bistratified)'};
  return null;
}
function bipolarPresentation(key,qualified=false) {
  if(qualified && /^(on|off)$/.test(key))return polarized('bipolar',key);
  const generic=/^(on|off)-bipolar$/.exec(key);
  if(generic)return polarized('bipolar',generic[1]);
  const subtype=/^(on|off)-(midget|diffuse)(-bipolar)?$/.exec(key);
  // Bare ON/OFF midget retains its established RGC meaning. The family path disambiguates it.
  if(subtype && (qualified || subtype[3] || subtype[2]==='diffuse'))return polarized('bipolar',subtype[1],subtype[2]);
  // Rod bipolar is a recognized ON type; bare rod remains a photoreceptor.
  if(key==='rod-bipolar' || (qualified && key==='rod'))return polarized('bipolar','on','rod');
  if(/^(bipolar|generic-bipolar|untyped-bipolar|unspecified-bipolar|unspecified-type-bipolar)$/.test(key))return neutral('bipolar');
  return null;
}
function amacrinePresentation(key) {
  const subtype=key.replace(/-amacrine$/,'');
  if(['aii','a17','starburst'].includes(subtype))return {shape:'amacrine',color:'var(--cell-amacrine)',variant:subtype};
  if(/^(amacrine|generic-amacrine|untyped-amacrine|unspecified-amacrine|unspecified-type-amacrine|ac)$/.test(key))return neutral('amacrine');
  return null;
}
function photoreceptorPresentation(key) {
  const receptor=key.replace(/s$/,'');
  if(receptor==='cone')return neutral('cone');
  if(receptor==='rod')return {shape:'rod',color:'var(--cell-outer)'};
  const cone=/^([sml])-cone$/.exec(receptor);
  if(cone)return {shape:'cone',color:`var(--cell-cone-${cone[1]})`};
  if(['photoreceptor','photoreceptors','generic-photoreceptor','unspecified-photoreceptor'].includes(key))return neutral('photoreceptor');
  return null;
}
export function cellTypePresentation(type) {
  const parts=String(type || '').split(/[\\/]+/).map(normalizeTypePart);
  const key=parts.pop(),prefix=parts.join('/'),family=families[prefix];
  if(prefix) {
    // Preserve a recorded family even when its subtype has no icon; never guess a subtype.
    if(family==='ganglion')return ganglionPresentation(key) || neutral('ganglion');
    if(family==='bipolar')return bipolarPresentation(key,true) || neutral('bipolar');
    if(family==='amacrine')return amacrinePresentation(key) || neutral('amacrine');
    if(family==='photoreceptor')return photoreceptorPresentation(key) || neutral('photoreceptor');
    if(family==='horizontal')return neutral('horizontal');
    return neutral('generic');
  }
  if(['rgc','ganglion','retinal-ganglion','generic-ganglion','unspecified-ganglion'].includes(key))return neutral('ganglion');
  if(key==='bc')return neutral('bipolar');
  if(['horizontal','hc'].includes(key))return {shape:'horizontal',color:'var(--cell-outer)'};
  return ganglionPresentation(key) || bipolarPresentation(key) || amacrinePresentation(key) || photoreceptorPresentation(key) || neutral('generic');
}
export function cellTypeColor(type) {
  return cellTypePresentation(type).color;
}

// Short QC headings are display aliases; tags and recorded metadata keep their source text.
export function cellTypeQCLabel(type) {
  const raw=type==null?'':String(type);
  if(!raw.trim())return 'Unclassified';
  const parts=raw.split(/[\\/]+/).map(normalizeTypePart);
  const key=parts.pop(),prefix=parts.join('/'),family=families[prefix];
  if(prefix&&!family)return raw;
  const ganglion={'on-parasol':'ON parasol','off-parasol':'OFF parasol','on-midget':'ON midget','off-midget':'OFF midget','small-bistratified':'Small bistratified'};
  const bipolar={'on-diffuse':'ON diffuse bipolar','off-diffuse':'OFF diffuse bipolar','on-midget':'ON midget bipolar','off-midget':'OFF midget bipolar','rod':'Rod bipolar','on':'ON bipolar','off':'OFF bipolar'};
  const amacrine={aii:'AII amacrine',a17:'A17 amacrine',starburst:'Starburst amacrine'};
  const receptor={'s-cone':'S cone','m-cone':'M cone','l-cone':'L cone',rod:'Rod',cone:'Cone'};
  if(family==='ganglion')return ganglion[key]||raw;
  if(family==='bipolar')return bipolar[key.replace(/-bipolar$/,'')]||raw;
  if(family==='amacrine')return amacrine[key.replace(/-amacrine$/,'')]||raw;
  if(family==='photoreceptor')return receptor[key]||raw;
  if(family==='horizontal')return key==='horizontal'?'Horizontal':raw;
  return ganglion[key]||amacrine[key.replace(/-amacrine$/,'')]||receptor[key]||
    (/-bipolar$/.test(key)?bipolar[key.replace(/-bipolar$/,'')]:null)||
    ({horizontal:'Horizontal',unclassified:'Unclassified',unknown:'Unclassified'}[key])||raw;
}


export function recordingRigLabel(cell={}) {
  const rigs=Array.isArray(cell.recording_rigs)?cell.recording_rigs.filter(value=>typeof value==='string'&&value.trim()):[];
  return rigs.length?[...rigs,...(cell.recording_rig_missing?['Not recorded']:[])].join(', '):'Not recorded';
}
