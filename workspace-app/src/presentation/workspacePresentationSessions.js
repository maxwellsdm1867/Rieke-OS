import {pruneDeletedSourceSelections} from './internal/deletedSourceSelections.js';

export const AUTHORED_DRAFT_LIMITS=Object.freeze({entries:256,keyBytes:8192,textBytes:16384,payloadBytes:512*1024});
const utf8Bytes=value=>new TextEncoder().encode(value).byteLength;
function authoredIdentity(route,key){
 const scope=[route.page,route.page==='protocol'?route.protocol:route.page==='cell-qc'?route.cell_uuid:route.page==='explore'?(route.retainedViewKey||route.key):null];
 return JSON.stringify([scope,key]);
}
function authoredAddress(route,key){
 if(!Array.isArray(key)||!key.length||key.some(part=>typeof part!=='string'))throw new Error('Authored draft identity must contain stable string keys.');
 const address=authoredIdentity(route,key);
 if(utf8Bytes(address)>AUTHORED_DRAFT_LIMITS.keyBytes)throw new Error('Authored draft identity exceeds the saved-view limit.');
 return address;
}
function validateAuthoredDrafts(entries){
 if(!Array.isArray(entries)||entries.length>AUTHORED_DRAFT_LIMITS.entries)throw new Error('Too many unfinished fields to save this workspace view.');
 for(const entry of entries){
  if(!Array.isArray(entry)||entry.length!==2||typeof entry[0]!=='string'||utf8Bytes(entry[0])>AUTHORED_DRAFT_LIMITS.keyBytes)throw new Error('Saved authored draft identity is invalid.');
  let identity;try{identity=JSON.parse(entry[0]);}catch{throw new Error('Saved authored draft identity is invalid.');}
  if(!Array.isArray(identity)||identity.length!==2||!Array.isArray(identity[0])||!Array.isArray(identity[1])||identity[1].some(part=>typeof part!=='string'))throw new Error('Saved authored draft identity is invalid.');
  const value=entry[1];
  if(typeof value!=='string'&&typeof value!=='boolean')throw new Error('Only authored text and display options belong in saved drafts.');
  if(typeof value==='string'&&utf8Bytes(value)>AUTHORED_DRAFT_LIMITS.textBytes)throw new Error('An unfinished field exceeds the saved-view text limit.');
 }
 if(utf8Bytes(JSON.stringify(entries))>AUTHORED_DRAFT_LIMITS.payloadBytes)throw new Error('Unfinished fields exceed the saved-view size limit.');
 return entries;
}

// One App mount owns these presentation values. Navigation, draft persistence,
// scientific authority and Protocol initialization remain with their callers.
/**
 * Create one in-memory presentation owner per App mount. No I/O or adapter.
 * @typedef {{page:string, key:string, protocol?:string, resumeExplorer?:boolean}} Route
 * @typedef {{route:unknown, sessions:Array<[string,unknown]>,
 *   protocolSessions:Array<[string,unknown]>, lastExplorerSession:unknown,
 *   lastStoresSession:unknown}} Checkpoint
 * @returns {{readDraft:(route:Route,key:string[])=>string|boolean|undefined, rememberDraft:(route:Route,key:string[],value:string|boolean|undefined)=>void, remember:(route:Route,value:unknown)=>void,
 *   read:(route:Route)=>{session:unknown,restoreSession:boolean},
 *   checkpoint:(route:unknown)=>Checkpoint, restore:(value:unknown)=>unknown,
 *   pruneDeleted:(removed:{removedEpochs?:string[],removedCells?:string[]})=>void}}
 * remember(route, value) retains the exact value by route.key and updates only
 * that destination's fallback (page: stores/explore/protocol; protocol identity).
 * read(route) returns {session, restoreSession}; exact truthy values precede
 * destination fallbacks. Object protocol snapshots inherit the latest protocol
 * tracePreference via a shallow copy when different; other fields retain their
 * route-specific values. Protocol restoreSession reports key presence, including
 * falsy saved values. Explorer fallback requires route.resumeExplorer.
 * checkpoint(route) returns {route, sessions, protocolSessions,
 * lastExplorerSession, lastStoresSession}: copied entry arrays, shared values.
 * Nonempty authoredDrafts adds bounded scalar text/options keyed by stable entity
 * identity; rejected writes block checkpoint until corrected, never evict earlier
 * input. readDraft/rememberDraft do not submit actions or restore consent.
 * restore(value) rejects null/nonobjects before mutation; arrays are accepted.
 * Invalid pair collections become empty independently; duplicate keys keep the
 * last value. It replaces stores before returning the unvalidated value.route.
 * pruneDeleted({removedEpochs, removedCells}) recursively removes identities
 * from snapshots and clears the Stores fallback, even for empty identity lists.
 * Navigation validation, stable callbacks, persistence and scientific authority
 * belong to App/callers. No deep cloning, eviction or project reset is implied.
 */
export function createWorkspacePresentationSessions(){
 let sessions=new Map(),protocolSessions=new Map(),lastExplorerSession=null,lastStoresSession=null,authoredDrafts=new Map();
 const authoredFailures=new Map();let authoredIntent=0;
 return {
  authoredIntent(){return authoredIntent;},
  readDraft(route,key){return authoredDrafts.get(authoredAddress(route,key));},
  rememberDraft(route,key,value){
   authoredIntent++;
   let address;try{address=authoredAddress(route,key);}catch(error){const failureKey=authoredIdentity(route,key);if(value===undefined){authoredFailures.delete(failureKey);return;}authoredFailures.set(failureKey,error);throw error;}
   const next=new Map(authoredDrafts);
   if(value===undefined)next.delete(address);else next.set(address,value);
   try{validateAuthoredDrafts([...next]);}catch(error){authoredFailures.set(address,error);throw error;}
   authoredFailures.delete(address);authoredDrafts=next;
  },
  remember(route,value){
   sessions.set(route.key,value);
   if(route.page==='stores')lastStoresSession=value;
   if(route.page==='explore')lastExplorerSession=value;
   if(route.page==='protocol'&&route.protocol)protocolSessions.set(route.protocol,value);
  },
  read(route){
   const saved=sessions.get(route.key);
   if(route.page==='protocol'){
    const latest=protocolSessions.get(route.protocol),view=saved||latest;
    // Viewing defaults follow the protocol's latest choice, not history's epoch.
    const session=view&&typeof view==='object'&&!Array.isArray(view)&&latest&&Object.hasOwn(latest,'tracePreference')&&view.tracePreference!==latest.tracePreference?{...view,tracePreference:latest.tracePreference}:view;
    return {session,restoreSession:sessions.has(route.key)};
   }
   if(route.page==='stores')return {session:saved||lastStoresSession,restoreSession:false};
   if(route.page==='explore')return {session:saved||(route.resumeExplorer?lastExplorerSession:null),restoreSession:false};
   return {session:saved,restoreSession:false};
  },
  checkpoint(route){
   if(authoredFailures.size)throw [...authoredFailures.values()][0];
   return {route,sessions:[...sessions],protocolSessions:[...protocolSessions],lastExplorerSession,lastStoresSession,...(authoredDrafts.size?{authoredDrafts:[...authoredDrafts]}:{})};
  },
  restore(value){
   if(!value||typeof value!=='object')throw new Error('The saved workspace view is invalid.');
   const restoredDrafts=validateAuthoredDrafts(value.authoredDrafts??[]);
   const pairs=entries=>Array.isArray(entries)&&entries.every(pair=>Array.isArray(pair)&&pair.length===2&&typeof pair[0]==='string')?entries:[];
   sessions=new Map(pairs(value.sessions));protocolSessions=new Map(pairs(value.protocolSessions));
   authoredDrafts=new Map(restoredDrafts);authoredFailures.clear();
   lastExplorerSession=value.lastExplorerSession||null;lastStoresSession=value.lastStoresSession||null;
   // Store replacement precedes the navigation owner's route validation.
   return value.route;
  },
  pruneDeleted({removedEpochs,removedCells}){
   const ids=new Set([...(removedEpochs||[]),...(removedCells||[])]);
   for(const address of authoredDrafts.keys()){const [scope,key]=JSON.parse(address);if([...scope,...key].some(part=>ids.has(part))){authoredDrafts.delete(address);authoredFailures.delete(address);}}
   sessions=new Map([...sessions].map(([key,value])=>[key,pruneDeletedSourceSelections(value,ids)]));
   protocolSessions=new Map([...protocolSessions].map(([key,value])=>[key,pruneDeletedSourceSelections(value,ids)]));
   lastExplorerSession=pruneDeletedSourceSelections(lastExplorerSession,ids);
   lastStoresSession=null;
  },
 };
}
