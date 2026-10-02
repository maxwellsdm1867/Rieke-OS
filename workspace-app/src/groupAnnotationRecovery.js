import {mutationUndo,undoEnabled} from './mutationUndo.js';
import {epochResourceCache} from './resourceCache.js';

// Session-only, at most four compact original requests. Never evict an
// unconfirmed operation or retain the server's target list/annotation graphs.
const MAX_PENDING=4,MAX_RECORD_BYTES=16*1024;
const records=new Map(),listeners=new Set(),changes=new Set();
let project=null,version=0;
const emit=()=>{version++;for(const listener of listeners)listener();};
const notify=record=>{epochResourceCache.invalidate();for(const listener of changes)listener({project:record.project,kind:'annotations'});};
export const groupAnnotationRecovery={
 subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},version:()=>version,
 project(value){project=value;emit();},currentProject:()=>project,
 view:()=>[...records.values()].map(row=>({operation_uuid:row.body.operation_uuid,project:row.project,profile_uuid:row.body.profile_uuid,tag:row.body.tag,count:row.count,status:row.status,error:row.error||''})),
 dismiss(operation){const record=records.get(operation);if(record?.status!=='rejected')throw Error('Confirm the original operation before dismissing it.');records.delete(operation);emit();},
 onChange(listener){changes.add(listener);return()=>changes.delete(listener);},
 async retry(operation){const record=records.get(operation);if(!record)throw Error('The original operation is no longer pending.');return run(record,true);},
};
export function retainGroupOperation({body,count,request,confirm,onTerminal}){
 if(records.size>=MAX_PENDING)throw Error('Resolve an earlier group save before starting another; four unconfirmed operations are retained.');
 const exact=Object.freeze({...body});
 if(JSON.stringify(exact).length*4+4096>MAX_RECORD_BYTES)throw Error('The original group request exceeds recovery memory admission.');
 const record={body:exact,count,project,request,confirm,onTerminal,status:'ready',error:'',pending:null,result:null};
 records.set(exact.operation_uuid,record);emit();
 return record;
}
export async function runGroupOperation(record){return run(record,false);}
async function run(record,recovery){
 if(record.result)return record.result;
 if(record.status==='rejected'||records.get(record.body.operation_uuid)!==record)throw Error('This refused operation is terminal. Reopen the group for a new preview.');
 if(record.project!==project)throw Error('Return to the original project to retry this group operation.');
 if(record.pending)return record.pending;
 const token=undoEnabled?mutationUndo.begin():null;
 record.status='pending';record.error='';emit();
 const pending=(async()=>{
  try{
   const receipt=record.confirm(await Promise.resolve().then(()=>record.request('/annotations/group',{method:'POST',body:record.body})));
   record.result=receipt;record.status='confirmed';records.delete(record.body.operation_uuid);
   epochResourceCache.invalidate();
   if(token)mutationUndo.complete(token,{...receipt.undo,profile_uuid:record.body.profile_uuid});
   if(recovery)notify(record);
   record.onTerminal?.();return receipt;
  }catch(error){
   if(token)mutationUndo.complete(token,null);
   record.error=String(error.message).slice(0,1024);
   if(!error.saved&&[400,409].includes(error.status)){
    record.status='rejected';record.onTerminal?.();
   }else record.status='unconfirmed';
   if(error.saved)notify(record);
   throw error;
  }finally{record.pending=null;emit();}
 })();
 record.pending=pending;return pending;
}
