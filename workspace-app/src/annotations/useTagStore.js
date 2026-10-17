import {useDeferredValue,useSyncExternalStore} from 'react';
import {tagStore} from './tagStore.js';

// Urgent: the tag editor paints the chip in the click's frame.
export function useTagVersion(store=tagStore){return useSyncExternalStore(store.subscribe,store.getVersion,store.getVersion);}
// Deferred: large views (trees, lists) catch up in an interruptible render
// after the editor has painted, never delaying the click-to-paint frame.
export function useDeferredTagVersion(store=tagStore){return useDeferredValue(useTagVersion(store));}
// Confirmed-only clock for results that depend on tags (filters, counts).
export function useTagGeneration(store=tagStore){return useSyncExternalStore(store.subscribe,store.getConfirmedGeneration,store.getConfirmedGeneration);}
