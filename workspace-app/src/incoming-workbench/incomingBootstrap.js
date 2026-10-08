import {requireWorkbenchContext} from './workbenchAuthority.js';

// A response-only projection; durable preparation receipts never own this data.
export function requireIncomingBootstrap(value,{root,protocolId,projectId,candidateRevision}){
  const context=requireWorkbenchContext(value?.context),page=value?.page,request=value?.request;
  const definition=context.protocol?.definition;
  if(value?.contract_version!==1||value.kind!=='workbench_initial_page'||value.root!==root||
    value.protocol_uuid!==protocolId||value.candidate_revision_uuid!==candidateRevision||context.candidate_revision_uuid!==candidateRevision||
    definition?.protocol_uuid!==protocolId||value.project_uuid!==definition?.project_uuid||projectId&&value.project_uuid!==projectId||
    typeof value.actor!=='string'||!value.actor||!request||request.offset!==0||request.limit!==60||request.include_cells!==true||
    !request.filters||typeof request.filters!=='object'||Array.isArray(request.filters)||
    !Number.isSafeInteger(context.expected_binding_version)||context.expected_binding_version<0||
    context.protocol?.query_revision!==context.candidate_scope_revision||context.protocol?.expected_binding_version!==context.expected_binding_version||
    !context.generation||typeof context.generation!=='object'||Array.isArray(context.generation)||
    page?.candidate_scope_revision!==context.candidate_scope_revision||page.query_revision!==context.candidate_scope_revision||
    page.expected_binding_version!==context.expected_binding_version||JSON.stringify(page.generation)!==JSON.stringify(context.generation)||
    !Number.isSafeInteger(page.total)||page.total<0||page.offset!==0||page.limit!==60||
    !Array.isArray(page.epochs)||page.epochs.length!==Math.min(60,page.total)||!Array.isArray(page.cells))throw new Error('The incoming bootstrap does not match its frozen context.');
  const cells=new Map();
  for(const cell of page.cells){
    if(typeof cell?.cell_uuid!=='string'||!cell.cell_uuid||cells.has(cell.cell_uuid)||!Number.isSafeInteger(cell.epochs)||cell.epochs<0)throw new Error('The incoming bootstrap has incomplete cell counts.');
    cells.set(cell.cell_uuid,cell.epochs);
  }
  const ids=new Set(),shown=new Map();
  for(const row of page.epochs){
    if(typeof row?.epoch_uuid!=='string'||!row.epoch_uuid||ids.has(row.epoch_uuid)||!cells.has(row.cell_uuid))throw new Error('The incoming bootstrap has incomplete epoch identities.');
    ids.add(row.epoch_uuid);
    shown.set(row.cell_uuid,(shown.get(row.cell_uuid)||0)+1);
    if(shown.get(row.cell_uuid)>cells.get(row.cell_uuid))throw new Error('The incoming bootstrap cell membership disagrees.');
  }
  if([...cells.values()].reduce((total,count)=>total+count,0)!==page.total)throw new Error('The incoming bootstrap cell counts disagree.');
  return value;
}

function requestKey(path){
  const url=new URL(path,'http://workspace.invalid');
  if(url.origin!=='http://workspace.invalid'||url.hash)return null;
  const keys=[...url.searchParams.keys()];
  if(new Set(keys).size!==keys.length)return null;
  return JSON.stringify([url.pathname,[...url.searchParams].sort(([a],[b])=>a.localeCompare(b))]);
}

export function incomingPageOffer(bootstrap,{root,protocolId,projectId,candidateRevision,profileUuid,profileReady}){
  if(!bootstrap||!profileReady||bootstrap.actor!==profileUuid||bootstrap.root!==root||bootstrap.protocol_uuid!==protocolId||
    bootstrap.project_uuid!==projectId||bootstrap.candidate_revision_uuid!==candidateRevision)return null;
  requireIncomingBootstrap(bootstrap,{root,protocolId,projectId,candidateRevision});
  const query=new URLSearchParams(bootstrap.request.filters);
  query.set('candidate_scope_revision',bootstrap.context.candidate_scope_revision);
  query.set('offset','0');query.set('limit','60');query.set('include_cells','true');
  const expected=requestKey(`${root}/epochs?${query}`),page=structuredClone(bootstrap.page);
  let claimed=null;
  return {claim({consumer,path}){
    if(requestKey(path)!==expected||claimed&&claimed!==consumer)return undefined;
    claimed=consumer;
    // StrictMode may repeat one consumer's unchanged effect. No new mount or
    // another resource can claim this response, and each DTO stays detached.
    return structuredClone(page);
  }};
}
