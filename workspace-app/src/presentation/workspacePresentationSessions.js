import {pruneDeletedSourceSelections} from './internal/deletedSourceSelections.js';

// One App mount owns these presentation values. Navigation, draft persistence,
// scientific authority and Protocol initialization remain with their callers.
/**
 * Create one in-memory presentation owner per App mount. No I/O or adapter.
 * @typedef {{page:string, key:string, protocol?:string, resumeExplorer?:boolean}} Route
 * @typedef {{route:unknown, sessions:Array<[string,unknown]>,
 *   protocolSessions:Array<[string,unknown]>, lastExplorerSession:unknown,
 *   lastStoresSession:unknown}} Checkpoint
 * @returns {{remember:(route:Route,value:unknown)=>void,
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
 * restore(value) rejects null/nonobjects before mutation; arrays are accepted.
 * Invalid pair collections become empty independently; duplicate keys keep the
 * last value. It replaces stores before returning the unvalidated value.route.
 * pruneDeleted({removedEpochs, removedCells}) recursively removes identities
 * from snapshots and clears the Stores fallback, even for empty identity lists.
 * Navigation validation, stable callbacks, persistence and scientific authority
 * belong to App/callers. No deep cloning, eviction or project reset is implied.
 */
export function createWorkspacePresentationSessions(){
 let sessions=new Map(),protocolSessions=new Map(),lastExplorerSession=null,lastStoresSession=null;
 return {
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
   return {route,sessions:[...sessions],protocolSessions:[...protocolSessions],lastExplorerSession,lastStoresSession};
  },
  restore(value){
   if(!value||typeof value!=='object')throw new Error('The saved workspace view is invalid.');
   const pairs=entries=>Array.isArray(entries)&&entries.every(pair=>Array.isArray(pair)&&pair.length===2&&typeof pair[0]==='string')?entries:[];
   sessions=new Map(pairs(value.sessions));protocolSessions=new Map(pairs(value.protocolSessions));
   lastExplorerSession=value.lastExplorerSession||null;lastStoresSession=value.lastStoresSession||null;
   // Store replacement precedes the navigation owner's route validation.
   return value.route;
  },
  pruneDeleted({removedEpochs,removedCells}){
   const ids=new Set([...(removedEpochs||[]),...(removedCells||[])]);
   sessions=new Map([...sessions].map(([key,value])=>[key,pruneDeletedSourceSelections(value,ids)]));
   protocolSessions=new Map([...protocolSessions].map(([key,value])=>[key,pruneDeletedSourceSelections(value,ids)]));
   lastExplorerSession=pruneDeletedSourceSelections(lastExplorerSession,ids);
   lastStoresSession=null;
  },
 };
}
