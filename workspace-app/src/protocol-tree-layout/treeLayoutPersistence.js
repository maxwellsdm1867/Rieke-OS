// Serialize autosaves so a slower response cannot overwrite a newer arrangement.
/**
 * Serialize {split_order, expected_version} writes and coalesce desired edits.
 * remember(fields) and retry() retain the last acknowledged version on failure;
 * onState reports errors rather than rejecting the caught write failure.
 * Version zero persists even an unchanged order. See the executable test example.
 */
export function createTreeLayoutSaver({version,splitOrder,write,onState=()=>{}}){
  let saved=[...splitOrder],desired=[...splitOrder],running=null;
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  async function flush(){
    if(running)return running;
    if(version>0&&same(saved,desired)){onState({status:'saved',version});return;}
    onState({status:'saving',version});
    running=(async()=>{
      try{
        while(version===0||!same(saved,desired)){
          const fields=[...desired];
          const result=await Promise.resolve().then(()=>write({split_order:fields,expected_version:version}));
          if(result.version!==version+1||!same(result.split_order,fields))throw new Error('Tree save returned an invalid receipt. Reload before retrying.');
          version=result.version;saved=fields;
        }
        onState({status:'saved',version});
      }catch(error){onState({status:'error',version,error:error.message});}
      finally{running=null;}
    })();
    return running;
  }
  return {remember:fields=>{desired=[...fields];return flush();},retry:flush};
}
