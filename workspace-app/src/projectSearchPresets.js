export function searchPresetPayload({name,description='',predicate,splits='',pinned=false},existing=null){
  if(typeof name!=='string'||!name.trim()||name.trim().length>160)throw new Error('Use a search name with 1–160 characters.');
  if(typeof description!=='string'||description.length>2000)throw new Error('Description must be at most 2,000 characters.');
  if(!predicate||typeof predicate!=='object'||Array.isArray(predicate))throw new Error('A typed search predicate is required.');
  if(typeof splits!=='string'||typeof pinned!=='boolean')throw new Error('Invalid search layout or pin setting.');
  const body={name:name.trim(),description:description.trim(),predicate,splits,pinned};
  if(existing){if(!Number.isSafeInteger(existing.version)||existing.version<1)throw new Error('Reload this saved search before updating it.');body.expected_version=existing.version;}
  return body;
}
export function presetDownloadRecipe(preset){
  const body=searchPresetPayload(preset);
  return {format:'rieke-search-preset',version:1,project_uuid:preset.project_uuid,preset_uuid:preset.preset_uuid,preset_version:preset.version,catalog_ref:'catalog.json',membership_mode:'live-query',name:body.name,description:body.description,predicate:body.predicate,splits:body.splits};
}
export function parsePresetRecipe(text){
  if(typeof text!=='string'||text.length>1024*1024)throw new Error('Query recipe files are limited to 1 MiB.');
  let recipe;try{recipe=JSON.parse(text);}catch{throw new Error('Choose a valid query recipe JSON file.');}
  if(recipe?.format!=='rieke-search-preset'||recipe.version!==1)throw new Error('This importer accepts Rieke search preset v1 JSON.');
  if(recipe.membership_mode&&recipe.membership_mode!=='live-query')throw new Error('Import a query-only recipe, not a frozen epoch selection.');
  if(['epochs','membership','selection'].some(key=>Object.hasOwn(recipe,key)))throw new Error('Frozen selections are not reusable query preset files.');
  if(recipe.catalog_ref&&recipe.catalog_ref!=='catalog.json')throw new Error('Imported queries must target the current project catalog.');
  const body=searchPresetPayload({...recipe,pinned:false});
  validatePortablePredicate(body.predicate);
  return {...body,source_project_uuid:recipe.project_uuid||null};
}
export function validatePortablePredicate(predicate){
  const pending=[{node:predicate,depth:0}];let count=0;
  while(pending.length){
    const {node,depth}=pending.pop();if(++count>128||depth>8)throw new Error('Imported predicates are limited to 128 nodes and eight levels.');
    if(!node||typeof node!=='object'||Array.isArray(node))throw new Error('Every predicate condition must be a JSON object.');
    const keys=Object.keys(node),group=['all','any','not'].find(key=>Object.hasOwn(node,key));
    if(group){if(keys.length!==1||group!=='not'&&!Array.isArray(node[group]))throw new Error('Invalid predicate group.');const children=group==='not'?[node.not]:node[group];for(const child of children)pending.push({node:child,depth:depth+1});continue;}
    if(typeof node.field!=='string'||!node.field||!['eq','ne','in','not_in','contains','gt','gte','lt','lte','exists','missing','is_null'].includes(node.operator)||keys.some(key=>!['field','operator','value'].includes(key)))throw new Error('Invalid predicate field or operator.');
    const unary=['exists','missing','is_null'].includes(node.operator);
    if(unary===Object.hasOwn(node,'value'))throw new Error('This predicate has a missing or unexpected comparison value.');
    if(!unary){
      if(JSON.stringify(node.value).length>4096)throw new Error('Predicate values are limited to 4,096 JSON characters.');
      const values=[{value:node.value,depth:0}];
      while(values.length){const {value,depth}=values.pop();if(depth>6)throw new Error('Predicate values are nested too deeply.');if(typeof value==='number'&&(!Number.isFinite(value)||Number.isInteger(value)&&!Number.isSafeInteger(value)))throw new Error('A numeric value cannot be represented exactly.');if(Array.isArray(value)){if(value.length>100)throw new Error('Predicate lists are limited to 100 values.');for(const child of value)values.push({value:child,depth:depth+1});}else if(value!==null&&!['string','number','boolean'].includes(typeof value))throw new Error('This editor supports scalar and list predicate values.');}
    }
  }
}
export function validatePresetReceipt(value){
  if(!value||typeof value.preset_uuid!=='string'||!Number.isSafeInteger(value.version)||value.version<1||typeof value.name!=='string'||!value.predicate)throw new Error('The server did not return a saved-search receipt. Refresh project searches before retrying.');
  return value;
}
export function sortedProjectPresets(rows=[]){return [...rows].sort((a,b)=>Number(b.pinned)-Number(a.pinned)||(a.name||'').localeCompare(b.name||''));}
export function resolvedPresetMatch(result){
  if(!result||!Object.hasOwn(result,'preset'))throw new Error('Could not check for an existing search. Retry the check before saving.');
  return result.preset===null?null:validatePresetReceipt(result.preset);
}
export function presetSaveTarget(match,preset,mode){
  if(match)return validatePresetReceipt(match);
  if(mode==='update'&&preset)return validatePresetReceipt(preset);
  if(mode!=='new')throw new Error('Choose a valid save destination.');
  return null;
}
export function samePresetTarget(left,right){
  return left===null&&right===null||!!left&&!!right&&left.preset_uuid===right.preset_uuid&&left.version===right.version;
}
