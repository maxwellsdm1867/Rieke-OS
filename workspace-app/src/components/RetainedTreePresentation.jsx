import {Activity,useState} from 'react';
import {useTreeBranchReads} from '../treeBranchReads.jsx';
import {canonicalReadIdentity} from '../pageReadCache.js';
import PagedTree from './PagedTree.jsx';

// One React presentation slot, no second query/payload cache. Frozen views are
// excluded. A changed authority owner or exact view evicts the mounted subtree.
export default function RetainedTreePresentation({active,tree}){
 const owner=useTreeBranchReads();
 const key=canonicalReadIdentity({owner:owner?.identity??null,protocol:tree.protocolId??null,filters:tree.filters||{},predicate:tree.predicate??null,splits:tree.splits??'',revision:tree.revision??0,expectedRevision:tree.expectedRevision??null,selected:tree.selected??null});
 const eligible=!!owner&&!tree.readContext;
 const [slot,setSlot]=useState({key,seen:active,active,visit:0});
 const next=slot.key!==key?{key,seen:active,active,visit:slot.visit+1}:slot.active!==active?{...slot,seen:slot.seen||active,active,visit:slot.visit+1}:slot;
 if(next!==slot)setSlot(next);
 const retained=active||eligible&&slot.key===key&&slot.seen;
 return retained?<Activity mode={active?'visible':'hidden'}>
  <PagedTree key={key} {...tree} active={active} presentationActivation={next.visit} actionsDisabled={!active||tree.actionsDisabled} presentation="columns" design/>
 </Activity>:null;
}
