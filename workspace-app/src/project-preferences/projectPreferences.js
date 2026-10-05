// Project-owned shortcuts hydrate before writes; localStorage is only a cache
// and a one-time source for migrating preferences saved by earlier app versions.
const fields=['recent_searches','protocol_shortcuts'];
export function preferenceStorageKey(projectId,field){
  return field==='recent_searches'?`rieke-os.search-presets.v1.${projectId}`:`rieke-os.sidebar.protocols.v1.${projectId}`;
}
const empty=field=>field==='recent_searches'?[]:{};
function renderableLegacySearch(entry){
  if(!entry||typeof entry!=='object'||Array.isArray(entry)||typeof entry.id!=='string'||!entry.id||entry.id.length>65536)return false;
  if(entry.name!=null&&(typeof entry.name!=='string'||entry.name.length>255))return false;
  if(entry.splits!=null&&(typeof entry.splits!=='string'||entry.splits.length>4096))return false;
  if(entry.pinned!=null&&typeof entry.pinned!=='boolean')return false;
  if(entry.lastRunAt!=null&&(typeof entry.lastRunAt!=='string'||entry.lastRunAt.length>64))return false;
  if(['matched_count','cell_count'].some(key=>entry[key]!=null&&(!Number.isSafeInteger(entry[key])||entry[key]<0)))return false;
  let nodes=0,literals=0;
  const literal=(value,depth=0)=>{
    if(++literals>4096||depth>6)return false;
    if(value===null||typeof value==='string'||typeof value==='boolean')return true;
    if(typeof value==='number')return Number.isFinite(value)&&(!Number.isInteger(value)||Number.isSafeInteger(value));
    if(Array.isArray(value))return value.length<=100&&value.every(child=>literal(child,depth+1));
    return value&&typeof value==='object'&&Object.values(value).every(child=>literal(child,depth+1));
  };
  const walk=(node,depth=0)=>{
    if(++nodes>128||depth>8||!node||typeof node!=='object'||Array.isArray(node))return false;
    const keys=Object.keys(node);
    if(keys.length===1&&keys[0]==='not')return walk(node.not,depth+1);
    if(keys.length===1&&['all','any'].includes(keys[0]))return Array.isArray(node[keys[0]])&&node[keys[0]].every(child=>walk(child,depth+1));
    if(keys.some(key=>!['field','operator','value'].includes(key))||typeof node.field!=='string'||!node.field||node.field.length>2048)return false;
    if(['exists','missing','is_null'].includes(node.operator))return keys.length===2&&!Object.hasOwn(node,'value');
    if(!['eq','ne','in','not_in','contains','gt','gte','lt','lte'].includes(node.operator)||!Object.hasOwn(node,'value')||!literal(node.value))return false;
    if(['in','not_in'].includes(node.operator)&&!Array.isArray(node.value))return false;
    return !['gt','gte','lt','lte'].includes(node.operator)||typeof node.value==='number';
  };
  return walk(entry.predicate);
}
function legacySearches(value){
  const seen=new Set();
  return value.filter(entry=>renderableLegacySearch(entry)&&!seen.has(entry.id)&&seen.add(entry.id)).slice(0,100).map(entry=>({
    id:entry.id,predicate:entry.predicate,splits:entry.splits??'date,cell',pinned:entry.pinned??false,
    ...Object.fromEntries(['name','matched_count','cell_count','lastRunAt'].filter(key=>Object.hasOwn(entry,key)).map(key=>[key,entry[key]])),
  }));
}
export function createProjectPreferenceClient({projectId,request,storage}){
  let loaded=false,loading=null,queue=Promise.resolve(),revisions={},values={},errors={};
  const listeners=new Set();
  const legacy={};
  for(const field of fields){
    try{const value=JSON.parse(storage?.getItem(preferenceStorageKey(projectId,field))||'null');legacy[field]=field==='recent_searches'?(Array.isArray(value)?legacySearches(value):undefined):(value&&typeof value==='object'&&!Array.isArray(value)?value:undefined);}catch{}
    values[field]=empty(field);
  }
  const publish=()=>listeners.forEach(listener=>listener());
  function accept(receipt,savedField=null){
    if(receipt?.format!=='rieke-project-preferences'||receipt.version!==1||receipt.project_uuid!==projectId||!receipt.state||!receipt.revisions)throw new Error('Project preference response has the wrong identity or format.');
    revisions={...receipt.revisions};
    for(const field of fields){
      if(loaded&&errors[field]&&field!==savedField)continue;
      const saved=Object.hasOwn(receipt.state,field);
      values[field]=saved?receipt.state[field]:legacy[field]??empty(field);
      // A missing field has not acknowledged migration. Retain the earlier
      // browser copy until PUT succeeds, including across a page refresh.
      if(saved)try{storage?.setItem(preferenceStorageKey(projectId,field),JSON.stringify(values[field]));}catch{}
    }
  }
  async function load(){
    if(loaded)return;
    if(loading)return loading;
    loading=(async()=>{
      let receipt=await request('/project-preferences');
      accept(receipt);
      errors={};
      // Never seed a recipient's portable preferences from that browser's cache.
      for(const field of fields){
        if(Object.hasOwn(receipt.state,field)||legacy[field]===undefined)continue;
        try{
          receipt=await request('/project-preferences',{method:'PUT',body:{field,value:legacy[field],expected_revision:revisions[field]}});
          accept(receipt);
        }catch(error){
          if(error.message==='Project preferences changed; reload before saving.'){
            receipt=await request('/project-preferences');accept(receipt);
          }else{errors[field]=`Earlier device shortcuts could not be saved to this project: ${error.message}`;}
        }
      }
      loaded=true;publish();
    })().catch(error=>{for(const field of fields)errors[field]=error.message;publish();throw error;}).finally(()=>{loading=null;});
    return loading;
  }
  function update(field,change){
    const operation=queue.catch(()=>{}).then(async()=>{
      await load();
      const revise=typeof change==='function'?change:()=>change;
      let next=revise(values[field]);
      values[field]=next;errors[field]=null;publish();
      try{
        let receipt;
        try{receipt=await request('/project-preferences',{method:'PUT',body:{field,value:next,expected_revision:revisions[field]}});}
        catch(error){
          if(error.message!=='Project preferences changed; reload before saving.')throw error;
          accept(await request('/project-preferences'),field);
          next=revise(values[field]);
          receipt=await request('/project-preferences',{method:'PUT',body:{field,value:next,expected_revision:revisions[field]}});
        }
        accept(receipt,field);errors[field]=null;publish();return values[field];
      }catch(error){values[field]=next;errors[field]=`Changes are visible in this session, but could not be saved to the project: ${error.message}`;publish();throw error;}
    });
    queue=operation;return operation;
  }
  return {
    get:field=>({value:values[field],loading:!loaded&&!errors[field],error:errors[field]||null}),
    subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
    load,update,
    async flush(){await queue;if(Object.values(errors).some(Boolean))throw new Error('Project preferences have unsaved changes.');},
    async reload(){await queue.catch(()=>{});loaded=false;errors={};return load();},
    async refresh(){await queue.catch(()=>{});if(loaded&&Object.values(errors).some(Boolean))return;loaded=false;return load();},
  };
}
