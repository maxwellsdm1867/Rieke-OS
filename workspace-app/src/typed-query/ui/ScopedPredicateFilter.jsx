import {useMemo} from 'react';
import PredicateDialog from './PredicateDialog.jsx';
import {predicateToDraft,newGroup} from './predicateState.js';
import {useFieldRegistry} from '../../summary-jobs/useFieldRegistry.js';

// The same editor as Search; this context always intersects frozen membership.
export default function ScopedPredicateFilter({protocol,projectId,filters,onChange,onClose,revision,purpose,readContext}){
  const id=protocol.protocol_uuid||protocol.definition?.protocol_uuid;
  const registry=useFieldRegistry(revision);
  const catalog=useMemo(()=>({...registry,supportsSummaries:readContext?false:registry.supportsSummaries,data:registry.data?{...registry.data,fields:registry.data.fields.filter(field=>!field.id.startsWith('curation/')||field.id===`curation/${id}/tags`)}:null}),[registry.data,registry.loading,registry.error,revision]);
  const initial=useMemo(()=>{const restored=predicateToDraft(filters.metadata_predicate?JSON.parse(filters.metadata_predicate):{all:[]});return restored.kind==='group'?restored:{...newGroup(),children:[restored]};},[]);
  const ordinary={...filters};delete ordinary.metadata_predicate;
  return <PredicateDialog draft={initial} catalog={catalog} projectId={projectId||protocol.definition?.project_uuid} protocolId={id}
    readContext={readContext?{...readContext,filters:ordinary}:{protocol_uuid:id,filters:ordinary}} title={purpose==='export'?'Filter export metadata':'Filter view metadata'} submitLabel={purpose==='export'?'Apply export criteria':'Apply view criteria'}
    onClose={onClose} onSearch={async(_draft,predicate)=>{onChange({...ordinary,metadata_predicate:JSON.stringify(predicate)});onClose();}}/>;
}
