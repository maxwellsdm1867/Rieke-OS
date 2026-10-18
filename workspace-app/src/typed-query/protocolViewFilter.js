const prefix='annotations/';
const pad=value=>String(value).padStart(2,'0');
/** datetime-local text (viewer's local time) -> ISO UTC instant with Z. */
export function localInputToUtc(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value))throw new Error('Choose a complete date and time for tag-time rules.');
  const time=new Date(value);if(!Number.isFinite(time.getTime()))throw new Error('Choose a valid date and time for tag-time rules.');
  return time.toISOString().replace(/\.\d{3}Z$/,'Z');
}
/** ISO UTC instant -> datetime-local text in the viewer's local time. */
export function utcToLocalInput(value){
  const time=new Date(value);if(typeof value!=='string'||!Number.isFinite(time.getTime()))return '';
  return `${time.getFullYear()}-${pad(time.getMonth()+1)}-${pad(time.getDate())}T${pad(time.getHours())}:${pad(time.getMinutes())}`;
}
function readRule(node){
  const condition=node.not||node,[scope,kind]=condition.field.slice(prefix.length).split('/'),comparison=node.not?'is_not':'is';
  if(kind==='tag_times'){
    const rule={scope,comparison,value:condition.value?.tag??''};
    if(condition.value?.after)rule.after=utcToLocalInput(condition.value.after);
    if(condition.value?.before)rule.before=utcToLocalInput(condition.value.before);
    return rule;
  }
  return {scope,comparison,value:condition.value};
}
export function readTagRules(filters={}){
  if(filters.tag_predicate){
    const ast=JSON.parse(filters.tag_predicate),mode=ast.any?'any':'all',nodes=ast[mode];
    if(!Array.isArray(nodes))throw new Error('Unsupported saved tag filter');
    return {mode,rules:nodes.map(readRule)};
  }
  return {mode:'all',rules:[{scope:'effective',comparison:'is',value:filters.tag||''}]};
}
export function compileTagRules(mode,rules){
  if(!['all','any'].includes(mode)||!rules.length||rules.length>20)throw new Error('Choose 1–20 tag rules.');
  return {[mode]:rules.map(rule=>{
    if(!['effective','cell','epoch'].includes(rule.scope)||!['is','is_not'].includes(rule.comparison)||typeof rule.value!=='string'||!rule.value.trim())throw new Error('Choose a scope, comparison and tag for each rule.');
    // A time window turns the rule into a tag-time rule on the same tag:
    // after <= added time < before, in UTC. Without one it is plain membership.
    let node={field:`annotations/${rule.scope}/tags`,operator:'contains',value:rule.value.trim()};
    if(rule.after||rule.before){
      const value={tag:rule.value.trim()};
      if(rule.after)value.after=localInputToUtc(rule.after);
      if(rule.before)value.before=localInputToUtc(rule.before);
      if(value.after&&value.before&&Date.parse(value.after)>=Date.parse(value.before))throw new Error('Choose an “added after” time earlier than “added before”.');
      node={field:`annotations/${rule.scope}/tag_times`,operator:'contains',value};
    }
    return rule.comparison==='is_not'?{not:node}:node;
  })};
}
export function clearTagFilters(filters){const next={...filters};delete next.tag;delete next.tagged;delete next.tag_predicate;return next;}
function ruleLabel(rule){
  const window=[rule.after&&`added after ${rule.after.replace('T',' ')}`,rule.before&&`added before ${rule.before.replace('T',' ')}`].filter(Boolean).join(' and ');
  return `${rule.scope} ${rule.comparison==='is_not'?'is not':'is'} “${rule.value}”${window?` ${window}`:''}`;
}
export function tagFilterLabel(filters={}){
  if(filters.metadata_predicate){const tags={...filters};delete tags.metadata_predicate;return ['Metadata conditions',tagFilterLabel(tags)].filter(Boolean).join(' + ');}
  if(filters.tag_predicate){try{const {mode,rules}=readTagRules(filters);return `${mode==='any'?'Any':'All'} of ${rules.length} tag ${rules.length===1?'rule':'rules'}: ${rules.map(ruleLabel).join('; ')}`;}catch{return 'Tag filter';}}
  return filters.tag?`Tag: ${filters.tag}`:filters.tagged?'Tagged epochs':'';
}

// The same view filter narrows either saved membership or a search's base query.
// Clearing it returns the exact base query without rewriting saved searches.
export function predicateWithTagFilters(predicate,filters={}){
  const conditions=[];
  if(filters.tag_predicate)conditions.push(JSON.parse(filters.tag_predicate));
  if(filters.tag)conditions.push({field:'annotations/effective/tags',operator:'contains',value:filters.tag});
  if(filters.tagged)conditions.push({field:'annotations/effective/tags',operator:'ne',value:[]});
  return conditions.length?{all:[predicate,...conditions]}:predicate;
}

export function predicateWithProtocolFilters(predicate,filters={}){
 const fields={cell_uuid:'cell',cell_type:'cell type',group_label:'group label'};
 const conditions=Object.entries(filters).filter(([key,value])=>fields[key]&&value).map(([key,value])=>({field:fields[key],operator:'eq',value}));
 if(filters.metadata_predicate)conditions.push(JSON.parse(filters.metadata_predicate));
 return predicateWithTagFilters(conditions.length?{all:[predicate,...conditions]}:predicate,filters);
}
