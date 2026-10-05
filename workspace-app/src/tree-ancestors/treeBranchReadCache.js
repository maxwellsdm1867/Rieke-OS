import {QueryClient,QueryObserver} from '@tanstack/react-query';
import {canonicalReadIdentity as canonical} from '../search-activation/pageReadCache.js';
// Cache storage only, not a total renderer heap claim. Mounted columns keep at
// most eight bounded pages; this adapter never owns terminal rows or raw H5.
export const TREE_BRANCH_LIMITS=Object.freeze({entries:24,bytes:4*1024*1024,inflight:8,retainMs:120000,leaseMs:10000});
const aborted=()=>Object.assign(Error('Tree read intent retired'),{name:'AbortError'});
const nonempty=value=>typeof value==='string'&&value.length>0;
const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const path=value=>Array.isArray(value)&&value.length<=8&&value.every(hash);
const recorded=field=>['date','cell','cell type','group','block','protocol','source'].includes(field)||/^(parameters|properties)\//.test(field);
export function reusableTreeBody(body){
 return !!body&&Object.keys(body).every(key=>['protocol_uuid','filters','splits','path','offset','limit','revision'].includes(key))&&
  nonempty(body.protocol_uuid)&&canonical(body.filters)==='{}'&&nonempty(body.splits)&&body.splits.split(',').length<=8&&body.splits.split(',').every(recorded)&&
  path(body.path)&&body.path.length<body.splits.split(',').length&&Number.isSafeInteger(body.offset)&&body.offset>=0&&body.limit===60&&hash(body.revision);
}
function identityFor(scope,body,page){
 const value=page?.read_identity,g=value?.generation;
 if(!value||value.version!==1||value.project_uuid!==scope.projectUuid||value.project_path!==scope.projectPath||value.protocol_uuid!==body.protocol_uuid||value.tree_revision!==page.revision||!hash(page.revision)||
  !g||!['metadata','source','annotation','binding','publication'].every(key=>nonempty(g[key]))||!(g.typed===null||nonempty(g.typed))||
  !Array.isArray(page.split_order)||page.split_order.join(',')!==body.splits)return null;
 try{return canonical(value);}catch{return null;}
}
function validBranch(body,page,identity){
 return page?.kind==='branches'&&identity===canonical(page.read_identity)&&page.revision===body.revision&&canonical(page.path)===canonical(body.path)&&page.offset===body.offset&&page.limit===body.limit&&page.depth===body.path.length&&page.split_order?.join(',')===body.splits&&
  Array.isArray(page.epochs)&&page.epochs.length===0&&Array.isArray(page.branches)&&page.branches.length<=60&&Number.isSafeInteger(page.total)&&page.total>=page.branches.length&&
  page.branches.every(row=>hash(row.key)&&path(row.path)&&canonical(row.path)===canonical([...body.path,row.key])&&Number.isSafeInteger(row.count)&&row.count>=0);
}
function immutable(value){
 canonical(value);const encoded=JSON.stringify(value);
 const clone=item=>Array.isArray(item)?item.map(clone):item&&typeof item==='object'?Object.fromEntries(Object.entries(item).map(([key,child])=>[key,clone(child)])):item;
 const data=clone(value),pending=[data];
 while(pending.length){const next=pending.pop();if(next&&typeof next==='object'){Object.freeze(next);pending.push(...Object.values(next));}}
 return {data,bytes:new TextEncoder().encode(encoded).length};
}
export function createTreeBranchReadCache(options={}){
 const limits={...TREE_BRANCH_LIMITS,...options},now=options.now||(()=>performance.now());
 for(const key of ['entries','bytes','inflight','retainMs','leaseMs'])if(!Number.isSafeInteger(limits[key])||limits[key]<1)throw Error('Finite positive tree cache bounds required');
 // QueryClient is the sole payload/request store. This ledger contains only
 // admission sizes and recency; QueryObserver owns coalescing and cancellation.
 const client=new QueryClient({defaultOptions:{queries:{retry:false,networkMode:'always',staleTime:Infinity,gcTime:limits.retainMs,refetchOnMount:false,refetchOnWindowFocus:false,refetchOnReconnect:false,structuralSharing:false}}});
 const ledger=new Map(),physical=new Set(),revocations=new Set(),leases=new WeakMap();let used=0,generation=0,owner=null;
 const counters={hits:0,reads:0,coalesced:0,evictions:0,oversized:0};
 const remove=key=>{const value=ledger.get(key);if(value){used-=value.bytes;ledger.delete(key);}client.removeQueries({queryKey:[key],exact:true});};
 client.getQueryCache().subscribe(event=>{if(event.type==='removed'){const key=event.query.queryKey[0],value=ledger.get(key);if(value){used-=value.bytes;ledger.delete(key);}}});
 const prune=()=>{for(const [key,value] of ledger)if(now()-value.at>=limits.retainMs)remove(key);};
 function retire(){generation++;owner=null;for(const cancel of [...revocations])cancel();client.clear();ledger.clear();used=0;}
 function invalidate(){const prior=owner;retire();owner=prior;}
 function activate(scope){const next=canonical(scope);if(next!==owner){retire();owner=next;}}
 function attest(scope,request,response){
  if(owner!==canonical(scope))return null;
  const identity=identityFor(scope,request,response);if(!identity)return null;
  const lease=Object.freeze({});leases.set(lease,{owner,generation,identity,protocol:request.protocol_uuid,splits:request.splits,revision:response.revision,at:now()});return lease;
 }
 function check(lease){const value=leases.get(lease);if(!value||value.owner!==owner||value.generation!==generation)throw aborted();if(now()-value.at>=limits.leaseMs)throw Object.assign(Error('Tree read witness expired; reload the current tree'),{name:'StaleTreeReadError'});return value;}
 function read(lease,body,{load,signal}={}){
  let proof,key;
  try{
   if(signal?.aborted)throw aborted();proof=check(lease);
   if(!reusableTreeBody(body)||body.protocol_uuid!==proof.protocol||body.splits!==proof.splits||body.revision!==proof.revision)throw Error('Tree read is outside the attested branch scope');
   key=canonical({owner:proof.owner,identity:proof.identity,method:'POST',path:'/tree-pages',body});
  }catch(error){return Promise.reject(error);}
  prune();const hit=ledger.get(key);
  if(hit){ledger.delete(key);ledger.set(key,hit);counters.hits++;}
  else if(client.getQueryState([key])?.fetchStatus==='fetching')counters.coalesced++;
  const expectedGeneration=generation;
  const observer=new QueryObserver(client,{queryKey:[key],queryFn:async({signal:querySignal})=>{
   if(physical.size>=limits.inflight)throw Error('Tree read capacity reached; retry after pending reads finish');
   const slot={};physical.add(slot);counters.reads++;
   try{
    const data=await load('/tree-pages',{method:'POST',body,signal:querySignal});
    if(querySignal.aborted||expectedGeneration!==generation)throw aborted();check(lease);
    if(!validBranch(body,data,proof.identity))throw Error('Tree read identity changed; refresh the current tree');
    return immutable(data).data;
   }finally{physical.delete(slot);}
  }});
  return new Promise((resolve,reject)=>{
   let unsubscribe,finished=false;
   const finish=(error,data)=>{
    if(finished)return;finished=true;signal?.removeEventListener('abort',cancel);revocations.delete(cancel);unsubscribe?.();observer.destroy();
    if(error){const query=client.getQueryCache().find({queryKey:[key],exact:true});if(!query?.getObserversCount())remove(key);if(error.status===409)invalidate();reject(error);return;}
    if(!ledger.has(key)){
     const bytes=immutable(data).bytes+new TextEncoder().encode(key).length+128;
     if(bytes<=limits.bytes){ledger.set(key,{bytes,at:now()});used+=bytes;while(ledger.size>limits.entries||used>limits.bytes){remove(ledger.keys().next().value);counters.evictions++;}}
     else{counters.oversized++;remove(key);}
    }
    resolve(data);
   };
   const cancel=()=>finish(aborted());
   const receive=result=>{if(result.isSuccess){try{check(lease);finish(null,result.data);}catch(error){finish(error);}}else if(result.isError)finish(result.error);};
   revocations.add(cancel);signal?.addEventListener('abort',cancel,{once:true});
   unsubscribe=observer.subscribe(receive);if(finished)unsubscribe();else receive(observer.getCurrentResult());
  });
 }
 return {client,activate,retire,attest,read,assertCurrent:lease=>!!check(lease),isActive:scope=>owner===canonical(scope),isCurrent(lease){try{check(lease);return true;}catch{return false;}},stats(){prune();return {...counters,entries:ledger.size,bytes:used,inflight:physical.size,generation};}};
}
