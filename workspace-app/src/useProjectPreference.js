import {useEffect,useState} from 'react';
import {api} from './api.js';
import {createProjectPreferenceClient,preferenceStorageKey} from './projectPreferences.js';
import {registerDraftSaver} from './desktopLifecycle.js';

const clients=new Map();
function clientFor(projectId){
  if(!clients.has(projectId)){
    let storage;try{storage=window.localStorage;}catch{}
    clients.set(projectId,createProjectPreferenceClient({projectId,request:api,storage}));
  }
  return clients.get(projectId);
}
export function useProjectPreference(projectId,field){
  const client=clientFor(projectId);
  const [snapshot,setSnapshot]=useState(()=>({client,field,...client.get(field)}));
  useEffect(()=>{
    const stopSaving=registerDraftSaver(()=>client.flush());
    const update=()=>setSnapshot({client,field,...client.get(field)});
    update();const unsubscribe=client.subscribe(update);
    if(projectId)client.load().catch(()=>{});
    const refresh=()=>{if(projectId)client.refresh().catch(()=>{});};
    const storageChanged=event=>{if(event.key===preferenceStorageKey(projectId,field))refresh();};
    window.addEventListener('focus',refresh);
    window.addEventListener('storage',storageChanged);
    return()=>{stopSaving();unsubscribe();window.removeEventListener('focus',refresh);window.removeEventListener('storage',storageChanged);};
  },[client,field,projectId]);
  const visible=snapshot.client===client&&snapshot.field===field?snapshot:client.get(field);
  return {...visible,update:change=>client.update(field,change),reload:()=>client.reload()};
}
