// Shared cell/epoch tag state as its own change channel, separate from the app
// revision clock. Confirmed facts come only from verified server receipts.
// Pending operations are presentation: they render in the same frame as the
// click, never supply expected revisions, and roll back visibly on failure.
import {applyAnnotationReceipts} from './annotationReceipts.js';

const keyOf=(kind,uuid)=>JSON.stringify([kind,uuid]);

export function createTagStore({limit=2048}={}){
  const entries=new Map(),listeners=new Set(),turns=new Map(),verified=new Map(),hints=new Map();
  let version=0,confirmedGeneration=0,staleGeneration=0,ticketSequence=0;
  const memo=new WeakMap();
  function emit(){version++;for(const listener of [...listeners])listener();}
  function entry(kind,uuid,create=false){
    const key=keyOf(kind,uuid);let value=entries.get(key);
    if(!value&&create){value={kind,uuid,confirmed:null,pending:[],error:null,version:0};entries.set(key,value);}
    if(value){entries.delete(key);entries.set(key,value);} // LRU order
    return value;
  }
  function evict(){
    for(const [key,value] of entries){
      if(entries.size<=limit)break;
      if(!value.pending.length)entries.delete(key); // pending intent is never discarded
    }
  }
  function touch(value){value.version++;}
  function confirmTarget(target){
    const value=entry(target.target_kind,target.target_uuid,true),previous=value.confirmed?.revisions||{};
    // Author revisions are monotonic; an older receipt never overwrites a newer one.
    const revisions={...previous},tags=[...(value.confirmed?.tags||[])];
    let changed=false;
    for(const [profile,next] of Object.entries(target.revisions)){
      if(next<(previous[profile]??0))continue;
      revisions[profile]=next;changed=true;
      for(let index=tags.length-1;index>=0;index--)if(tags[index].profile_uuid===profile)tags.splice(index,1);
      tags.push(...target.tags.filter(chip=>chip.profile_uuid===profile));
    }
    if(changed){value.confirmed={target_kind:target.target_kind,target_uuid:target.target_uuid,revisions,tags};touch(value);}
    return changed;
  }
  const store={
    subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
    getVersion:()=>version,
    getConfirmedGeneration:()=>confirmedGeneration,
    getStaleGeneration:()=>staleGeneration,
    read:(kind,uuid)=>entries.get(keyOf(kind,uuid)),
    /** Last confirmed author revision known for a target, or undefined. */
    confirmedRevision(kind,uuid,profile){return entries.get(keyOf(kind,uuid))?.confirmed?.revisions?.[profile];},
    /** Best known revision for building a write: confirmed, else a page hint, else 0.
     *  Never displayed; the server verifies it and rejects a stale value. */
    knownRevision(kind,uuid,profile){return store.confirmedRevision(kind,uuid,profile)??hints.get(keyOf(kind,uuid))?.[profile]??0;},
    /** Record author revisions seen on loaded epoch rows (no emit, no display effect). */
    hint(rows){
      for(const row of Array.isArray(rows)?rows:[]){
        const revisions=row?.annotations?.revisions;if(!revisions)continue;
        if(row.epoch_uuid&&revisions.epoch)hints.set(keyOf('epoch',row.epoch_uuid),revisions.epoch);
        if(row.cell_uuid&&revisions.cell)hints.set(keyOf('cell',row.cell_uuid),revisions.cell);
      }
      while(hints.size>limit*4)hints.delete(hints.keys().next().value);
    },
    /** Show an add/remove now. Returns a ticket; the caller must confirm or fail it. */
    begin({kind,uuid,profile,authorName,tag,remove=false}){
      const value=entry(kind,uuid,true),ticket=++ticketSequence;
      value.pending.push({ticket,profile,authorName,tag,remove});value.error=null;touch(value);evict();emit();
      return ticket;
    },
    /** Show one add on many targets in a single update; returns one ticket. */
    beginMany({kind,uuids,profile,authorName,tag}){
      const ticket=++ticketSequence;
      for(const uuid of uuids){const value=entry(kind,uuid,true);value.pending.push({ticket,profile,authorName,tag,remove:false});value.error=null;touch(value);}
      evict();emit();return ticket;
    },
    /** Resolve when every earlier operation on this target/profile has settled. */
    turn(kind,uuid,profile,ticket){return store.turnMany(kind,[uuid],profile);},
    /** One turn across many targets: resolves when every earlier operation on any
     *  of them has settled, and later single or selection writes on any of them
     *  wait for this one. Keys are taken synchronously, so turns cannot deadlock. */
    turnMany(kind,uuids,profile){
      let release;const current=new Promise(resolve=>{release=resolve;});const previous=[];
      for(const uuid of new Set(uuids)){
        const key=JSON.stringify([kind,uuid,profile]),prior=turns.get(key)||Promise.resolve();previous.push(prior);
        const chained=prior.then(()=>current);turns.set(key,chained);
        chained.then(()=>{if(turns.get(key)===chained)turns.delete(key);});
      }
      return Promise.all(previous).then(()=>release);
    },
    confirm(ticket,receipt){
      let changed=false;
      for(const target of receipt?.targets||[])changed=confirmTarget(target)||changed;
      for(const value of entries.values()){
        const before=value.pending.length;value.pending=value.pending.filter(op=>op.ticket!==ticket);
        if(value.pending.length!==before)touch(value);
      }
      if(changed)confirmedGeneration++;
      emit();
    },
    /** Roll back a failed operation. Later queued operations by the same author on
     *  the same target depended on it and are cancelled (never sent); they are
     *  returned once each (by ticket) so the caller can restore or name their text. */
    fail(ticket,error){
      const cancelled=new Map();
      for(const value of entries.values()){
        const index=value.pending.findIndex(op=>op.ticket===ticket);
        if(index<0)continue;
        // Later queued operations on the same target depended on this one.
        const failed=value.pending[index];
        for(const op of value.pending.slice(index+1))if(op.profile===failed.profile&&op.ticket!==ticket&&!cancelled.has(op.ticket))
          cancelled.set(op.ticket,{ticket:op.ticket,kind:value.kind,uuid:value.uuid,profile:op.profile,tag:op.tag,remove:op.remove});
        value.pending=value.pending.filter((op,position)=>position<index||op.profile!==failed.profile);
        value.error=error?.message||String(error||'Tag save failed');touch(value);
      }
      emit();
      // A selection operation still pending on other targets will be sent.
      return [...cancelled.values()].filter(op=>!store.isPending(op.ticket));
    },
    /** Confirmed receipts from undo, imports or other producers. */
    ingest(receipt){
      let changed=false;for(const target of receipt?.targets||[])changed=confirmTarget(target)||changed;
      if(changed){confirmedGeneration++;evict();emit();}
    },
    /** Facts changed without per-target receipts (group saves, external sync).
     *  Overlays stay (author revisions only move forward), but any epoch shown
     *  afterwards is read fresh once (needsVerification) before it is trusted. */
    changed(){confirmedGeneration++;staleGeneration++;emit();},
    needsVerification(epochUuid){return staleGeneration>0&&(verified.get(epochUuid)??0)<staleGeneration;},
    /** Fresh annotations for one epoch (and its cell) from the server. */
    ingestAnnotations(epochUuid,cellUuid,annotations,generation=staleGeneration){
      if(!annotations)return;
      const targets=[['epoch',epochUuid,annotations.epoch_tags,annotations.revisions?.epoch],['cell',cellUuid,annotations.cell_tags,annotations.revisions?.cell]]
        .filter(([,uuid,,revisions])=>uuid&&revisions).map(([kind,uuid,tags,revisions])=>({target_kind:kind,target_uuid:uuid,revisions,tags:tags||[]}));
      for(const target of targets)confirmTarget(target);
      verified.set(epochUuid,generation);if(verified.size>limit)verified.delete(verified.keys().next().value);
      evict();emit();
    },
    /** Facts changed elsewhere without a receipt: drop confirmed overlays. */
    invalidate(){store.changed();},
    /** Overlay confirmed receipts, then pending operations, on an epoch row. */
    apply(row){
      if(!row?.annotations)return row;
      const epochEntry=entries.get(keyOf('epoch',row.epoch_uuid)),cellEntry=row.cell_uuid?entries.get(keyOf('cell',row.cell_uuid)):undefined;
      if(!epochEntry&&!cellEntry)return row;
      const stamp=`${epochEntry?.version??-1}:${cellEntry?.version??-1}`,cached=memo.get(row);
      if(cached?.stamp===stamp)return cached.value;
      const confirmed=new Map();
      for(const value of [epochEntry,cellEntry])if(value?.confirmed)confirmed.set(keyOf(value.kind,value.uuid),{target:value.confirmed});
      let result=confirmed.size?applyAnnotationReceipts(row,confirmed):row;
      const pending=[[epochEntry,'epoch'],[cellEntry,'cell']].filter(([value])=>value?.pending.length);
      if(pending.length){
        const annotations={...result.annotations};
        for(const [value,kind] of pending){
          let chips=[...(annotations[`${kind}_tags`]||[])];
          for(const op of value.pending){
            chips=chips.filter(chip=>!(chip.profile_uuid===op.profile&&chip.tag===op.tag));
            if(!op.remove)chips.push({target_kind:kind,target_uuid:value.uuid,profile_uuid:op.profile,author_name:op.authorName,tag:op.tag,pending:true});
          }
          annotations[`${kind}_tags`]=chips;
        }
        annotations.effective_tags=[...(annotations.cell_tags||[]),...(annotations.epoch_tags||[])];
        result={...result,annotations};
      }
      memo.set(row,{stamp,value:result});
      return result;
    },
    isPending(ticket){for(const value of entries.values())if(value.pending.some(op=>op.ticket===ticket))return true;return false;},
    error:(kind,uuid)=>entries.get(keyOf(kind,uuid))?.error||null,
    reset(){entries.clear();turns.clear();verified.clear();hints.clear();staleGeneration=0;confirmedGeneration++;emit();},
  };
  return store;
}

export const tagStore=createTagStore();
