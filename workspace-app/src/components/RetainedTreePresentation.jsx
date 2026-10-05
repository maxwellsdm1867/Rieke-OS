import {Activity,useState} from 'react';
import {useTreeBranchReads} from '../tree-ancestors/treeBranchReads.jsx';
import {canonicalReadIdentity} from '../search-activation/pageReadCache.js';
import PagedTree from './PagedTree.jsx';

// One React presentation slot, no second query/payload cache. Frozen views are
// excluded. A changed authority owner or exact view evicts the mounted subtree.
export default function RetainedTreePresentation({active,tree}){
 const owner=useTreeBranchReads();
 const key=canonicalReadIdentity({owner:owner?.identity??null,protocol:tree.protocolId??null,filters:tree.filters||{},predicate:tree.predicate??null,splits:tree.splits??'',revision:tree.revision??0,expectedRevision:tree.expectedRevision??null,readContext:tree.readContext??null});
 const eligible=!!owner&&!tree.readContext;
 const focus=tree.selected??null;
 const [slot,setSlot]=useState({key,focus,seen:active,active,visit:0,mount:0});
 // Active focus belongs to the existing selection owner. Hidden presentation
 // reuse still requires the exact last active focus, including changed-on-return.
 const evict=slot.key!==key||(!active||!slot.active)&&slot.focus!==focus;
 const next=evict?{key,focus,seen:active,active,visit:slot.visit+1,mount:slot.mount+1}:
   slot.active!==active||slot.focus!==focus?{...slot,focus,seen:slot.seen||active,active,visit:slot.visit+(slot.active!==active?1:0)}:slot;
 if(next!==slot)setSlot(next);
 const retained=active||eligible&&next.key===key&&next.seen;
 return retained?<div hidden={!active} aria-busy={active&&!!tree.readPending} style={{display:active?'flex':'none',flexDirection:'column',position:'relative',minWidth:0,minHeight:0,overflow:'hidden'}}>
  {active&&tree.readPending&&<p role="status" data-retained-tree-status style={{position:'absolute',zIndex:2,top:0,right:8,pointerEvents:'none',background:'var(--surface)',padding:'4px 8px'}}>Refreshing — previous view. Actions are unavailable until validation completes.</p>}
  <Activity mode={active?'visible':'hidden'}>
  <PagedTree key={next.mount} {...tree} active={active} presentationActivation={next.visit} refreshingLabelOwned={tree.readPending!==undefined} actionsDisabled={!active||tree.actionsDisabled} presentation="columns" design/>
 </Activity></div>:null;
}
