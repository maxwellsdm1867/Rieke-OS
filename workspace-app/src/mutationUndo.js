// Session memory only: never part of UI drafts, project snapshots or exports.
export const UNDO_LIMITS={actions:50,bytes:512*1024};
// A diagnostic opt-out supports like-for-like baseline measurements.
export const undoEnabled=(()=>{try{return globalThis.localStorage?.getItem('rieke.undo.enabled')!=='false';}catch{return true;}})();
const actionRows=action=>action.targets||action.operations||[];
const actionSize=action=>JSON.stringify(action).length*4+(actionRows(action).length||1)*(action.targets?128:256)+(action.patterns?.length||0)*256+256;
const targetKey=(action,row)=>Array.isArray(row)?action.kind==='annotations'?`a:${action.target_kind}:${row[0]}:${action.profile_uuid}`:`c:${action.protocol_uuid}:${row[0]}`:action.kind==='annotations'?`a:${row.target_kind}:${row.target_uuid}:${row.profile_uuid}`:`c:${action.protocol_uuid}:${row.epoch_uuid}`;
export function expandUndoAction(action){
 if(!action.targets)return action;
 return {...action,operations:action.targets.map(([id,expected_revision,before_revision,index])=>action.kind==='annotations'?{target_kind:action.target_kind,target_uuid:id,profile_uuid:action.profile_uuid,expected_revision,before_revision,...action.patterns[index]}:{epoch_uuid:id,expected_revision,before_revision,changes:action.patterns[index]})};
}
export function createUndoHistory(limits=UNDO_LIMITS){
 let project=null,stack=[],bytes=0,pending=0,busy=false,message='',version=0;
 const listeners=new Set(),locals=new Map();
 const emit=()=>{version++;for(const listener of listeners)listener();};
 const clear=()=>{stack=[];bytes=0;};
 const view=()=>({project,count:stack.length,bytes,pending,busy,message});
 return {
  subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},version:()=>version,view,
  project(value){if(project===value)return;project=value;clear();message='';emit();},
  begin(){if(busy)throw Error('Undo is still saving. Wait before another edit.');pending++;emit();const original=project;return {project:original};},
  complete(token,action){pending=Math.max(0,pending-1);if(token.project===project)this.record(action);emit();},
  failed(error){pending=Math.max(0,pending-1);clear();message=error?.saved?'The database edit was saved, but its inverse receipt was not confirmed. Refresh its targets; session undo was cleared.':'The edit could not be confirmed. Refresh its state before further edits; session undo was cleared.';emit();},
  record(action){
   if(!project||!action)return;
   if(action.kind==='unavailable'){clear();message=action.reason;emit();return;}
   if(!['annotations','annotation_group','curation','search-inclusion'].includes(action.kind))return;
   if(action.kind==='annotation_group'&&(!Number.isSafeInteger(action.count)||action.count<1||typeof action.operation_uuid!=='string'||typeof action.profile_uuid!=='string'))return;
   if(!['search-inclusion','annotation_group'].includes(action.kind)&&!actionRows(action).length)return;
   if(actionRows(action).length>1000){clear();message='This gesture is too large for session undo.';emit();return;}
   const size=actionSize(action);
   if(size>limits.bytes){clear();message='This gesture exceeds session undo memory limits.';emit();return;}
   const saved=JSON.parse(JSON.stringify(action));stack.push({action:saved,size});bytes+=size;
   while(stack.length>limits.actions||bytes>limits.bytes)bytes-=stack.shift().size;
   message='';emit();
  },
  local(id,handler){locals.set(id,handler);return()=>locals.delete(id);},
  async undo(run){
   if(busy)return false;
   if(pending){message='Wait for the current edit to finish before undoing.';emit();return false;}
   const entry=stack.at(-1);if(!entry)return false;
   const original=project;busy=true;message='Undoing edit…';emit();
   try{
    const action=entry.action;
    const result=action.kind==='search-inclusion'?await locals.get(action.viewer)?.(action):await run(action);
    if(result===undefined)throw Error('That search is no longer active. Return to its original viewer before undoing.');
    if(project!==original)return false;
    stack.pop();bytes-=entry.size;
    // An inverse is a new revision. Advance only the nearest preceding edit on
    // each original target when its expected revision is the undone prior state.
    const updates=result.revisions||{};
    for(const row of actionRows(action)){
     const key=targetKey(action,row),revision=updates[key];if(!Number.isSafeInteger(revision))continue;
     for(let index=stack.length-1;index>=0;index--){
      const older=stack[index].action,match=actionRows(older).find(value=>targetKey(older,value)===key);
      if(match){if(Array.isArray(match)){if(match[1]===(Array.isArray(row)?row[2]:row.before_revision))match[1]=revision;}else if(match.expected_revision===(Array.isArray(row)?row[2]:row.before_revision))match.expected_revision=revision;break;}
     }
    }
    bytes=0;for(const saved of stack){saved.size=actionSize(saved.action);bytes+=saved.size;}
    while(bytes>limits.bytes)bytes-=stack.shift().size;
    message='Last edit undone.';return true;
   }catch(error){if(error.saved&&entry.action.kind==='annotation_group'){message=`The inverse SQL commit needs recovery confirmation: ${error.message} Retry Undo to replay the same operation.`;}else if(error.saved){clear();message=`The inverse edit was saved to the database, but recovery needs attention: ${error.message} Session undo was cleared; refresh the targets.`;}else message=`Undo was not confirmed: ${error.message} ${entry.action.kind==='annotation_group'?'Earlier overlapping group edits retain their original author revisions and can conflict after a later inverse. ':''}Refresh the original targets before retrying.`;return false;}
   finally{busy=false;emit();}
  },
 };
}
export const mutationUndo=createUndoHistory();
export function isUndoableRequest(path,options){return undoEnabled&&options?.method==='POST'&&!options.undoOperation&&(path==='/annotations'||/^\/protocols\/[^/]+\/curation$/.test(path));}
export function shouldUndoData(target){
 if(!target)return true;
 if(target.isContentEditable)return false;
 if(target.readOnly||target.disabled||['checkbox','radio','button','submit','reset','range','file'].includes(target.type))return true;
 if(['INPUT','TEXTAREA','SELECT'].includes(target.tagName))return target.getAttribute?.('data-saved-undo')==='true'&&!target.value;
 return true;
}

export function localUndoScope(value){
 const words=[0x811c9dc5,0x9e3779b9,0x85ebca6b,0xc2b2ae35];
 for(let index=0;index<value.length;index++)for(let part=0;part<4;part++)words[part]=Math.imul(words[part]^value.charCodeAt(index),16777619+part*2)>>>0;
 return words.map(word=>word.toString(16).padStart(8,'0')).join('');
}
