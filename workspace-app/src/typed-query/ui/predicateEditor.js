// Presentation helpers preserve the predicate AST's exact boolean and value types.
export const valueTypes=['string','number','boolean','array','null'];
export function groupChoice(node){return node.negated?(node.mode==='any'?'none':'not_all'):node.mode;}
export function setGroupChoice(node,choice){
  if(!['all','any','none','not_all'].includes(choice))throw new Error('Unknown group operator');
  return {...node,mode:choice==='all'||choice==='not_all'?'all':'any',negated:choice==='none'||choice==='not_all'};
}
export function fieldCategory(field){
  if(field.category==='Parameters'||field.id.startsWith('parameters/'))return 'Protocol settings';
  const ancestry=field.id.match(/^metadata\/(experiment|cell|group|block|epoch)\//)?.[1];
  if(ancestry)return {experiment:'Experiment',cell:'Cell',group:'Epoch group',block:'Epoch block',epoch:'Epoch'}[ancestry];
  return field.category || 'Recording';
}
function typeOf(value){return value===null?'null':Array.isArray(value)?'array':typeof value;}
export function preferredValueType(field,operator='eq'){
  if(['in','not_in'].includes(operator))return 'array';
  if(['gt','gte','lt','lte'].includes(operator))return 'number';
  if(field?.id==='date')return 'string';
  if(operator==='contains'&&field?.types?.includes('array')&&!field.types.includes('string')){
    const element=(field.choices || []).flatMap(choice=>Array.isArray(choice.value)?choice.value:[]).find(value=>valueTypes.includes(typeOf(value)));
    return element===undefined?'string':typeOf(element);
  }
  const first=field?.types?.find(type=>valueTypes.includes(type)&&type!=='null');
  return first || (field?.types?.includes('null')?'null':'string');
}
export function blankValue(type){return type==='boolean'?'true':type==='array'?'[]':'';}
export function operatorChoices(field,labels,current){
  const permitted=(field?.operators || Object.keys(labels)).filter(operator=>!field ||
    (['gt','gte','lt','lte'].includes(operator)?field.types?.includes('number'):operator==='contains'?(field.types?.includes('string')||field.types?.includes('array')):true));
  // A loaded condition must remain visible, even when a refreshed catalog no
  // longer supports its operator. The compiler/backend still rejects it.
  return current&&!permitted.includes(current)?[current,...permitted]:permitted;
}
export function canUseDateInput(node){
  if(node.field!=='date'||node.valueType!=='string'||!['eq','ne'].includes(node.operator))return false;
  if(!node.valueText)return true;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(node.valueText))return false;
  const date=new Date(node.valueText+'T00:00:00Z');
  return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===node.valueText;
}

export function recordedValueChoices(field,operator){
  if(operator!=='contains')return field?.choices || [];
  const choices=[],seen=new Set();
  for(const choice of field?.choices || []){
    const values=Array.isArray(choice.value)?choice.value:[choice.value];
    for(const value of values){const type=typeOf(value);if(!valueTypes.includes(type))continue;const key=JSON.stringify([type,value]);if(seen.has(key))continue;seen.add(key);choices.push({value,type,example_only:true});}
  }
  return choices;
}

// Annotation arrays represent membership, so entering one tag should search for
// that tag rather than compare an entire JSON array of tags.
export function isTagField(field){return /^(annotations\/(cell|epoch|effective)|curation\/[^/]+)\/tags$/.test(typeof field==='string'?field:field?.id||'');}
export function fieldCondition(field){
  const operators=field.operators||(['array','string'].some(type=>field.types?.includes(type))?['eq','contains']:['eq']);
  const operator=(field.id==='protocol'||isTagField(field))&&operators.includes('contains')?'contains':operators.includes('eq')?'eq':operators[0];
  const valueType=preferredValueType(field,operator);
  return {field:field.id,operator,valueType,valueText:blankValue(valueType)};
}
