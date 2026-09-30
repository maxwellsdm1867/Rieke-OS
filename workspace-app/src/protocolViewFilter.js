const prefix='annotations/';
export function readTagRules(filters={}){
  if(filters.tag_predicate){
    const ast=JSON.parse(filters.tag_predicate),mode=ast.any?'any':'all',nodes=ast[mode];
    if(!Array.isArray(nodes))throw new Error('Unsupported saved tag filter');
    return {mode,rules:nodes.map(node=>{const condition=node.not||node;return {scope:condition.field.slice(prefix.length).split('/')[0],comparison:node.not?'is_not':'is',value:condition.value};})};
  }
  return {mode:'all',rules:[{scope:'effective',comparison:'is',value:filters.tag||''}]};
}
export function compileTagRules(mode,rules){
  if(!['all','any'].includes(mode)||!rules.length||rules.length>20)throw new Error('Choose 1–20 tag rules.');
  return {[mode]:rules.map(rule=>{
    if(!['effective','cell','epoch'].includes(rule.scope)||!['is','is_not'].includes(rule.comparison)||typeof rule.value!=='string'||!rule.value.trim())throw new Error('Choose a scope, comparison and tag for each rule.');
    const node={field:`annotations/${rule.scope}/tags`,operator:'contains',value:rule.value.trim()};
    return rule.comparison==='is_not'?{not:node}:node;
  })};
}
export function clearTagFilters(filters){const next={...filters};delete next.tag;delete next.tagged;delete next.tag_predicate;return next;}
export function tagFilterLabel(filters={}){
  if(filters.tag_predicate){try{const {mode,rules}=readTagRules(filters);return `${mode==='any'?'Any':'All'} of ${rules.length} tag ${rules.length===1?'rule':'rules'}`;}catch{return 'Tag filter';}}
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
