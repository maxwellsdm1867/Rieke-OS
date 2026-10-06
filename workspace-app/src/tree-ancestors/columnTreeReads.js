import {canonicalReadIdentity as canonical} from '../search-activation/pageReadCache.js';
import {treePageRequest} from '../pagedTreeRequest.js';
import {columnAncestorPages} from '../tree-browser/columnTreeNavigation.js';
import {reusableTreeBody} from './treeBranchReadCache.js';

// Every operation starts with a current server page. Only its nonterminal
// ancestors may use attested JSON. Selection/range/tag loaders never call this.
export async function loadColumnTreePages({scope,path=[],offset=0,anchor=null,revisionOverride=null,columnPositions=[],freshContinuation=false,retainedPages=[],readOwner,load,signal,isCurrent=()=>true}){
 let liveCapability=!scope.readContext&&retainedPages.some(page=>page.tree_column_pages===true);
 const endpoint=scope.readContext?`${scope.readContext.root}/tree/page`:'/tree-pages';
 const current=()=>!signal?.aborted&&isCurrent()&&(!readOwner||readOwner.active());
 if(freshContinuation&&!scope.readContext&&!anchor&&(path.length||offset)){
  const rootBody=treePageRequest(scope,{path:[],offset:0,reset:true});
  const root=await load(endpoint,{method:'POST',body:rootBody,signal});
  if(!current())throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
  revisionOverride=root.revision;liveCapability=root.tree_column_pages===true;
 }
 const body=treePageRequest(scope,{path,offset,anchor,currentRevision:revisionOverride,reset:!revisionOverride});
 // Retained geometry is only a scheduling hint. Fresh witness/lease checks
 // below remain the sole authority for cached JSON.
 const covered=!anchor&&path.every((_,depth)=>retainedPages.some(page=>page.kind==='branches'
  &&canonical(page.path)===canonical(path.slice(0,depth))
  &&page.offset===(columnPositions[depth]?.offset??page.offset)));
 const batch=scope.readContext?.tree_column_pages===true||liveCapability&&(!!anchor||path.length>0)&&(!covered||!readOwner?.available);
 if(batch){body.include_ancestors=true;body.ancestor_offsets=Array.from(columnPositions.slice(0,8),position=>position?.offset==null?null:Number.isSafeInteger(position.offset)&&position.offset>=0?position.offset:0);}
 const page=await load(endpoint,{method:'POST',body,signal});
 if(!current())throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
 const {include_ancestors,ancestor_offsets,...ordinaryBody}=body;
 const lease=!scope.readContext&&endpoint==='/tree-pages'?readOwner?.attest(ordinaryBody,page):null;
 const targets=columnAncestorPages(page,{anchor:!!anchor,columnPositions});
 const frozen=!!scope.readContext;
  const validLivePage=value=>value&&Array.isArray(value.path)&&value.path.length<=8
   &&value.path.every(key=>typeof key==='string'&&/^[a-f0-9]{64}$/.test(key))
   &&value.depth===value.path.length&&value.limit===ordinaryBody.limit
   &&Array.isArray(value.split_order)&&value.split_order.join(',')===ordinaryBody.splits
   &&Number.isSafeInteger(value.offset)&&value.offset>=0
   &&Number.isSafeInteger(value.total)&&value.total>=0
   &&Array.isArray(value.branches)&&Array.isArray(value.epochs)
   &&(value.kind==='branches'?value.epochs.length===0&&value.branches.length<=value.limit
     &&value.branches.every(row=>typeof row.key==='string'&&/^[a-f0-9]{64}$/.test(row.key)
       &&canonical(row.path)===canonical([...value.path,row.key])&&Number.isSafeInteger(row.count)&&row.count>=0)
    :value.kind==='epochs'&&value.branches.length===0&&value.epochs.length<=value.limit
     &&value.epochs.every(row=>typeof row.epoch_uuid==='string'&&row.epoch_uuid));
  const validTarget=frozen||validLivePage(page)&&(!ordinaryBody.revision||page.revision===ordinaryBody.revision)
   &&(anchor?page.anchor?.epoch_uuid===anchor&&canonical(page.anchor.path)===canonical(page.path)
     &&page.anchor.offset===page.offset&&Number.isSafeInteger(page.anchor.index)&&page.anchor.index>=page.offset
     &&page.anchor.index<page.offset+page.limit
    :canonical(page.path)===canonical(ordinaryBody.path)&&page.offset===ordinaryBody.offset);
 if(batch){
  const parents=page.ancestor_pages;
  const identity=page.read_identity;
  const invalidFence=frozen
   ?page.candidate_scope_revision!==scope.readContext.candidate_scope_revision||page.query_revision!==page.candidate_scope_revision
    ||!Number.isSafeInteger(page.expected_binding_version)||page.expected_binding_version<0
    ||!page.generation||typeof page.generation!=='object'||Array.isArray(page.generation)
   :page.tree_column_pages!==true||!identity||identity.version!==1||identity.protocol_uuid!==scope.protocolId
    ||identity.tree_revision!==page.revision||!identity.project_uuid||!identity.project_path
    ||!identity.generation||!['metadata','source','annotation','binding','publication'].every(key=>typeof identity.generation[key]==='string'&&identity.generation[key])
    ||!(identity.generation.typed===null||typeof identity.generation.typed==='string'&&identity.generation.typed)
    ||readOwner?.available&&!lease;
  if(!validTarget||invalidFence||!Array.isArray(parents)||parents.length!==targets.length
    ||parents.some((parent,index)=>!parent||parent.kind!=='branches'||canonical(parent.path)!==canonical(targets[index].path)
      ||parent.offset!==targets[index].offset||parent.revision!==page.revision
      ||(frozen?(parent.candidate_scope_revision!==page.candidate_scope_revision||parent.query_revision!==page.query_revision
        ||parent.expected_binding_version!==page.expected_binding_version||canonical(parent.generation)!==canonical(page.generation))
        :!validLivePage(parent)||canonical(parent.read_identity)!==canonical(identity))))
   throw Error('Tree column response changed or is incomplete; refresh the current tree');
  const {ancestor_pages,...target}=page;
  if(lease){
   // Admit already validated parents through the existing bounded immutable cache.
   // This adapter performs no HTTP; cached JSON still needs the next fresh witness.
   await Promise.all(parents.map(parent=>{
    const request=treePageRequest(scope,{path:parent.path,offset:parent.offset,currentRevision:page.revision});
    return reusableTreeBody(request)?readOwner.read(lease,request,{load:async()=>parent,signal}):null;
   }));
  }
  if(!current()||lease&&!readOwner.current(lease))throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
  return [...parents,target];
 }
 // The first fresh live target can discover support without a separate
 // discovery read. Fetch its remaining ancestors as one independently fenced
 // bundle, then join only if both responses carry the exact same identity.
 const discovered=!frozen&&page.tree_column_pages===true&&targets.length>1&&!covered;
 let parents;
 if(discovered){
  if(!validTarget||readOwner?.available&&!lease)throw Error('Tree column response changed or is incomplete; refresh the current tree');
  const deepest=targets.at(-1);
  parents=await loadColumnTreePages({scope,path:deepest.path,offset:deepest.offset,
   revisionOverride:page.revision,columnPositions:targets.map(parent=>({offset:parent.offset})),
   retainedPages:[page],load,signal,isCurrent:current});
  if(parents.length!==targets.length||parents.some((parent,index)=>parent.kind!=='branches'
    ||canonical(parent.path)!==canonical(targets[index].path)||parent.offset!==targets[index].offset
    ||canonical(parent.read_identity)!==canonical(page.read_identity)))
   throw Error('Tree column response changed or is incomplete; refresh the current tree');
 }else{
  parents=await Promise.all(targets.map(target=>{
  const request=treePageRequest(scope,{path:target.path,offset:target.offset,currentRevision:page.revision});
  return lease&&reusableTreeBody(request)?readOwner.read(lease,request,{load,signal}):load(endpoint,{method:'POST',body:request,signal});
 }));
 }
 if(!current()||lease&&!readOwner.current(lease))throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
 for(const parent of parents){
  if(parent.revision!==page.revision)throw Error('Tree revision changed; refresh the current tree');
  // An operation with attestation cannot silently combine a fresh target with
  // an ancestor from another publication/annotation/binding/source generation.
  if(lease&&canonical(parent.read_identity)!==canonical(page.read_identity))throw Error('Tree read identity changed; refresh the current tree');
 }
 if(discovered&&lease){
  await Promise.all(parents.map(parent=>{
   const request=treePageRequest(scope,{path:parent.path,offset:parent.offset,currentRevision:page.revision});
   return reusableTreeBody(request)?readOwner.read(lease,request,{load:async()=>parent,signal}):null;
  }));
  if(!current()||!readOwner.current(lease))throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
 }
 return [...parents,page];
}
