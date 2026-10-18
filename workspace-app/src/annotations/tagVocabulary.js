// Project tag vocabulary for suggestions and inline completion. Loaded once,
// matched locally on every keystroke, and extended the moment a tag is saved.
// When the project has more tags than one load returns, callers keep the
// server query as a fallback for prefixes outside the loaded set.
import {useSyncExternalStore} from 'react';

const LIMIT=100;
let state={tags:[],complete:false,loaded:false,loading:false,stale:false,version:0};
const listeners=new Set();
function publish(next){state={...state,...next,version:state.version+1};for(const listener of [...listeners])listener();}

export function subscribeVocabulary(listener){listeners.add(listener);return()=>listeners.delete(listener);}
export function vocabularyVersion(){return state.version;}
export function useVocabulary(){useSyncExternalStore(subscribeVocabulary,vocabularyVersion,vocabularyVersion);return state;}

export function loadVocabulary(request){
  if(state.loading||state.loaded&&!state.stale)return;
  publish({loading:true});
  Promise.resolve(request(`/annotation-tags?q=&limit=${LIMIT}`)).then(result=>{
    const tags=Array.isArray(result?.tags)?result.tags.filter(item=>typeof item?.tag==='string').map(item=>({tag:item.tag,count:Number(item.count)||0})):[];
    // Keep tags saved while the load was in flight.
    const known=new Set(tags.map(item=>item.tag));for(const item of state.tags)if(!known.has(item.tag))tags.push(item);
    publish({tags,complete:result?.has_more!==true,loaded:true,loading:false,stale:false});
  },()=>publish({loading:false}));
}
export function addVocabularyTag(tag){
  if(typeof tag!=='string'||!tag.trim())return;
  const current=state.tags.find(item=>item.tag===tag);
  publish({tags:current?state.tags.map(item=>item===current?{...item,count:item.count+1}:item):[...state.tags,{tag,count:1}]});
}
export function markVocabularyStale(){if(state.loaded)publish({stale:true});}
export function resetVocabulary(){state={tags:[],complete:false,loaded:false,loading:false,stale:false,version:state.version+1};for(const listener of [...listeners])listener();}

const rank=(a,b)=>b.count-a.count||a.tag.localeCompare(b.tag);
/** Prefix matches first, then other substring matches; case-insensitive. */
export function matchVocabulary(query,limit=12,tags=state.tags){
  const needle=query.trim().toLocaleLowerCase();
  if(!needle)return [...tags].sort(rank).slice(0,limit);
  const prefix=[],inner=[];
  for(const item of tags){const at=item.tag.toLocaleLowerCase().indexOf(needle);if(at===0)prefix.push(item);else if(at>0)inner.push(item);}
  return [...prefix.sort(rank),...inner.sort(rank)].slice(0,limit);
}
/** The most used existing tag that extends what was typed, or null. */
export function completeVocabulary(typed,tags=state.tags){
  if(!typed)return null;
  const needle=typed.toLocaleLowerCase();
  const match=tags.filter(item=>item.tag.length>typed.length&&item.tag.toLocaleLowerCase().startsWith(needle)).sort(rank)[0];
  return match?.tag??null;
}
