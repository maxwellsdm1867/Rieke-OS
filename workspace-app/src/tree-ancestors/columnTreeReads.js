import {canonicalReadIdentity as canonical} from '../search-activation/pageReadCache.js';
import {treePageRequest} from '../pagedTreeRequest.js';
import {columnAncestorPages} from '../tree-browser/columnTreeNavigation.js';
import {reusableTreeBody} from './treeBranchReadCache.js';

// Every operation starts with a current server page. Only its nonterminal
// ancestors may use attested JSON. Selection/range/tag loaders never call this.
export async function loadColumnTreePages({scope,path=[],offset=0,anchor=null,revisionOverride=null,columnPositions=[],freshContinuation=false,readOwner,load,signal,isCurrent=()=>true}){
 const endpoint=scope.readContext?`${scope.readContext.root}/tree/page`:'/tree-pages';
 const current=()=>!signal?.aborted&&isCurrent()&&(!readOwner||readOwner.active());
 if(freshContinuation&&!scope.readContext&&!anchor&&(path.length||offset)){
  const rootBody=treePageRequest(scope,{path:[],offset:0,reset:true});
  const root=await load(endpoint,{method:'POST',body:rootBody,signal});
  if(!current())throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
  revisionOverride=root.revision;
 }
 const body=treePageRequest(scope,{path,offset,anchor,currentRevision:revisionOverride,reset:!revisionOverride});
 const batch=scope.readContext?.tree_column_pages===true;
 if(batch){body.include_ancestors=true;body.ancestor_offsets=Array.from(columnPositions.slice(0,8),position=>position?.offset==null?null:Number.isSafeInteger(position.offset)&&position.offset>=0?position.offset:0);}
 const page=await load(endpoint,{method:'POST',body,signal});
 if(!current())throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
 const lease=!scope.readContext&&endpoint==='/tree-pages'?readOwner?.attest(body,page):null;
 const targets=columnAncestorPages(page,{anchor:!!anchor,columnPositions});
 if(batch){
  const parents=page.ancestor_pages;
  if(!Array.isArray(parents)||parents.length!==targets.length||page.candidate_scope_revision!==scope.readContext.candidate_scope_revision
    ||page.query_revision!==page.candidate_scope_revision||!Number.isSafeInteger(page.expected_binding_version)||page.expected_binding_version<0
    ||!page.generation||typeof page.generation!=='object'||Array.isArray(page.generation)
    ||parents.some((parent,index)=>!parent||parent.kind!=='branches'||canonical(parent.path)!==canonical(targets[index].path)
      ||parent.offset!==targets[index].offset||parent.revision!==page.revision
      ||parent.candidate_scope_revision!==page.candidate_scope_revision||parent.query_revision!==page.query_revision
      ||parent.expected_binding_version!==page.expected_binding_version||canonical(parent.generation)!==canonical(page.generation)))
   throw Error('Tree column response changed or is incomplete; refresh the current tree');
  const {ancestor_pages,...target}=page;
  return [...parents,target];
 }
 const parents=await Promise.all(targets.map(target=>{
  const request=treePageRequest(scope,{path:target.path,offset:target.offset,currentRevision:page.revision});
  return lease&&reusableTreeBody(request)?readOwner.read(lease,request,{load,signal}):load(endpoint,{method:'POST',body:request,signal});
 }));
 if(!current()||lease&&!readOwner.current(lease))throw Object.assign(Error('Tree navigation superseded'),{name:'AbortError'});
 for(const parent of parents){
  if(parent.revision!==page.revision)throw Error('Tree revision changed; refresh the current tree');
  // An operation with attestation cannot silently combine a fresh target with
  // an ancestor from another publication/annotation/binding/source generation.
  if(lease&&canonical(parent.read_identity)!==canonical(page.read_identity))throw Error('Tree read identity changed; refresh the current tree');
 }
 return [...parents,page];
}
