import {pruneDeletedSourceSelections} from './deletedSourceSelections.js';

// One App mount owns these presentation values. Navigation, draft persistence,
// scientific authority and Protocol initialization remain with their callers.
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
   if(route.page==='protocol')return {session:saved||protocolSessions.get(route.protocol),restoreSession:sessions.has(route.key)};
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
