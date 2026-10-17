import {startTransition,useEffect,useState,useSyncExternalStore} from 'react';
import {tagStore} from './tagStore.js';

// Urgent: the tag editor paints the chip in the click's frame.
export function useTagVersion(store=tagStore){return useSyncExternalStore(store.subscribe,store.getVersion,store.getVersion);}
// Background: large views (trees, lists, QC) subscribe through a transition, so
// a tag never re-renders them inside the click's frame; they catch up after
// paint in an interruptible render. (A useSyncExternalStore subscription would
// re-render the subscriber urgently even if its value were deferred.)
export function useDeferredTagVersion(store=tagStore){
  const [version,setVersion]=useState(store.getVersion);
  useEffect(()=>{
    const update=()=>startTransition(()=>setVersion(store.getVersion()));
    update();return store.subscribe(update);
  },[store]);
  return version;
}
// Confirmed-only clock for results that depend on tags (filters, counts).
export function useTagGeneration(store=tagStore){
  const [generation,setGeneration]=useState(store.getConfirmedGeneration);
  useEffect(()=>{
    const update=()=>startTransition(()=>setGeneration(store.getConfirmedGeneration()));
    update();return store.subscribe(update);
  },[store]);
  return generation;
}
// Facts changed without receipts (group saves, external sync): shown epochs re-read.
export function useTagStaleGeneration(store=tagStore){
  const [generation,setGeneration]=useState(store.getStaleGeneration);
  useEffect(()=>{
    const update=()=>startTransition(()=>setGeneration(store.getStaleGeneration()));
    update();return store.subscribe(update);
  },[store]);
  return generation;
}
