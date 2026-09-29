import {predicateIdentity} from './predicateIdentity.js';
function normalizedPredicate(predicate){
 if(predicate.not){const child=normalizedPredicate(predicate.not);return child.not&&Object.keys(child).length===1?child.not:{not:child};}
 const mode=predicate.all?'all':predicate.any?'any':null;
 if(!mode){if(['in','not_in'].includes(predicate.operator)&&Array.isArray(predicate.value)){const values=new Map(predicate.value.map(value=>[predicateIdentity(value),value]));return {...predicate,value:[...values.keys()].sort().map(key=>values.get(key))};}return predicate;}
 const children=predicate[mode].flatMap(child=>{const normalized=normalizedPredicate(child);return normalized[mode]&&Object.keys(normalized).length===1?normalized[mode]:[normalized];});
 const unique=new Map(children.map(child=>[predicateIdentity(child),child]));const sorted=[...unique.keys()].sort().map(key=>unique.get(key));
 return sorted.length===1?sorted[0]:{[mode]:sorted};
}
export function presetKey(predicate){return predicateIdentity(normalizedPredicate(predicate));}
export function predicateSummary(predicate){
 if(predicate.not)return `NOT (${predicateSummary(predicate.not)})`;
 if(predicate.all||predicate.any){const items=predicate.all||predicate.any;return items.length?items.map(predicateSummary).join(predicate.all?' AND ':' OR '):'All active epochs';}
 const field=predicate.field==='protocol'?'Protocol ID':String(predicate.field||'Field').replace(/^parameters\//,'Setting · ');
 const operator={eq:'is',contains:'contains',gt:'>',gte:'≥',lt:'<',lte:'≤',exists:'is recorded',missing:'is missing',ne:'is not'}[predicate.operator]||predicate.operator;
 return `${field} ${operator}${Object.hasOwn(predicate,'value')?' '+(typeof predicate.value==='string'?(predicate.field==='protocol'?predicate.value.split('.').at(-1):predicate.value):JSON.stringify(predicate.value)):''}`;
}
export function rememberSearch(entries,entry,now=new Date().toISOString()){
 const id=presetKey(entry.predicate),previous=entries.find(item=>item.id===id);
 const next={id,name:entry.name||previous?.name,predicate:entry.predicate,splits:entry.splits??previous?.splits??'date,cell',matched_count:entry.matched_count??previous?.matched_count,cell_count:entry.cell_count??previous?.cell_count,pinned:entry.pinned??previous?.pinned??false,lastRunAt:entry.lastRunAt??(Object.hasOwn(entry,'matched_count')&&!Object.hasOwn(entry,'pinned')?now:previous?.lastRunAt)};
 const all=[next,...entries.filter(item=>item.id!==id)];
 return [...all.filter(item=>item.pinned),...all.filter(item=>!item.pinned).slice(0,12)];
}
export function suggestedSearches(fields=[]){
 const suggestions=[{name:'History noise',predicate:{field:'protocol',operator:'contains',value:'History'}},{name:'Mean noise',predicate:{field:'protocol',operator:'contains',value:'VariableMeanNoise'}}];
 const setting=fields.find(field=>field.id==='parameters/frequencyCutoff');
 const choice=setting?.choices?.find(choice=>choice.type==='number'&&Number.isFinite(choice.value));
 if(choice)suggestions.push({name:`Frequency cutoff · ${choice.value}`,predicate:{field:setting.id,operator:'eq',value:choice.value}});
 return suggestions.map(item=>({...item,id:presetKey(item.predicate),splits:'date,cell'}));
}

export function searchRunSummary(item){
 const run=item.last_run;
 return {at:run?.ran_at??item.lastRunAt??item.created_at??null,epochs:run?.epoch_count??item.matched_count??item.summary?.matched_count??null,cells:run?.cell_count??item.cell_count??item.summary?.cell_count??null};
}
