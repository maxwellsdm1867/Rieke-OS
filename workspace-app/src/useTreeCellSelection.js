import {useCallback,useState} from 'react';

export function treeCellUuid(item,field){
  return field?.field==='cell'&&!item.missing&&typeof item.value==='string'&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(item.value)?item.value:null;
}

// Only explicit checkboxes from a current tree page supply cell identities.
// Epoch selections and group labels never become cell-tag targets.
export default function useTreeCellSelection(source){
  const scope=JSON.stringify(source?[source.protocolId,source.predicate,source.readContext,source.filters,source.splits,source.revision,source.expectedRevision]:null);
  const [selection,setSelection]=useState({scope,revision:null,cells:[]});
  const [page,setPage]=useState({scope,revision:null,loading:true,error:null});
  const [drafts,setDrafts]=useState({});
  const cells=selection.scope===scope&&selection.revision===page.revision?selection.cells:[];
  const blocked=!source||source.actionsDisabled||page.scope!==scope||page.loading||!!page.error||!page.revision;
  const status=useCallback(value=>setPage(previous=>({...previous,scope,...value})),[scope]);
  const metadata=useCallback(value=>setPage(previous=>({...previous,scope,revision:value.revision})),[scope]);
  const rememberDraft=useCallback((key,value)=>setDrafts(previous=>{if(previous[key]===value)return previous;const next={...previous};if(value)next[key]=value;else delete next[key];return next;}),[]);
  function toggle(cell,revision,checked){
    if(blocked||revision!==page.revision)return;
    setSelection(previous=>{
      const current=previous.scope===scope&&previous.revision===revision?previous.cells:[];
      const retained=current.filter(value=>value.cell_uuid!==cell.cell_uuid);
      return {scope,revision,cells:checked&&retained.length<1000?[...retained,cell]:retained};
    });
  }
  return {cells,ids:cells.map(cell=>cell.cell_uuid),blocked,revision:JSON.stringify([scope,page.revision,!!blocked]),status,metadata,toggle,
    clear:()=>setSelection({scope,revision:page.revision,cells:[]}),composer:{values:drafts,onChange:rememberDraft}};
}
