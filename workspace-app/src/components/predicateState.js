let sequence=0;
const identity=()=>`predicate-${++sequence}`;
export const newCondition=()=>({id:identity(),kind:'condition',field:'',operator:'eq',valueType:'string',valueText:'',negated:false});
export const newGroup=()=>({id:identity(),kind:'group',mode:'all',children:[],negated:false});
export function predicateToDraft(predicate) {
  if(predicate.not){const node=predicateToDraft(predicate.not);return {...node,negated:!node.negated};}
  if(predicate.all || predicate.any)return {...newGroup(),mode:predicate.all?'all':'any',children:(predicate.all || predicate.any).map(predicateToDraft)};
  const value=predicate.value;
  return {...newCondition(),field:predicate.field,operator:predicate.operator,
    valueType:value===null?'null':Array.isArray(value)?'array':typeof value==='number'?'number':typeof value==='boolean'?'boolean':'string',
    valueText:typeof value==='string'?value:value===undefined?'':JSON.stringify(value)};
}
function validateJSON(value) {
  if(typeof value==='number'&&(!Number.isFinite(value)||(Number.isInteger(value)&&!Number.isSafeInteger(value))))throw new Error('This numeric value cannot be represented exactly. Choose a safe recorded value.');
  if(Array.isArray(value))value.forEach(validateJSON);
  if(value&&typeof value==='object'&&!Array.isArray(value))throw new Error('Object values are not supported in this filter editor.');
}
export function typedValue(text,type) {
  if(type==='string')return text;
  if(type==='null')return null;
  if(type==='boolean'){if(!['true','false'].includes(text))throw new Error('Choose true or false.');return text==='true';}
  if(type==='number'){
    if(!String(text).trim()||!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/.test(String(text).trim()))throw new Error('Enter a complete numeric value.');
    const value=Number(text);validateJSON(value);return value;
  }
  if(type==='array'){
    let value;try{value=JSON.parse(text);}catch{throw new Error('Enter a valid JSON list, for example [25, 100].');}
    if(!Array.isArray(value))throw new Error('A list must use square brackets.');
    if(value.length>100)throw new Error('Use at most 100 list values.');validateJSON(value);return value;
  }
  throw new Error('Choose a supported value type.');
}
export function compilePredicate(node,fields=null,depth=0) {
  if(depth>6)throw new Error('Use at most six nested groups.');
  let result;
  if(node.kind==='group'){
    if(!['all','any'].includes(node.mode))throw new Error('Choose ALL or ANY for this group.');
    if(node.children.length>100)throw new Error('Use at most 100 conditions per group.');
    result={[node.mode]:node.children.map(child=>compilePredicate(child,fields,depth+1))};
  }else{
    if(!node.field)throw new Error('Choose a metadata field for every condition.');
    if(!['eq','ne','in','not_in','contains','gt','gte','lt','lte','exists','missing','is_null'].includes(node.operator))throw new Error('Choose a supported comparison operator.');
    const field=fields?.find(item=>item.id===node.field);
    if(fields&&!field)throw new Error('A field in this draft is not in the current metadata catalog.');
    if(field?.operators&&!field.operators.includes(node.operator))throw new Error(`The operator is unavailable for ${field.label}.`);
    result={field:node.field,operator:node.operator};
    if(!['exists','missing','is_null'].includes(node.operator)){
      result.value=typedValue(node.valueText,['in','not_in'].includes(node.operator)?'array':node.valueType);
      if(['gt','gte','lt','lte'].includes(node.operator)&&typeof result.value!=='number')throw new Error('Ordering comparisons require a numeric value.');
    }
  }
  return node.negated?{not:result}:result;
}
export function conditionCount(node){return node.kind==='group'?node.children.reduce((sum,child)=>sum+conditionCount(child),0):1;}
