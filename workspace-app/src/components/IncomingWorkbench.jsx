import {useCallback,useEffect,useRef,useState} from 'react';
import {humanize,number,time} from '../api.js';
import {activeProtocolSuggestions} from '../protocolSuggestions.js';
import {reviewKey,reviewWorklist} from '../incomingReview.js';
import IncomingExportDialog from './IncomingExportDialog.jsx';
import MetadataExplorer from './MetadataExplorer.jsx';
import FrozenIncomingReview from './FrozenIncomingReview.jsx';
import useWorkbenchQueue from '../useWorkbenchQueue.js';
import './IncomingWorkbench.css';

export default function IncomingWorkbench({projectId,protocolId,protocols=[],suggestions=[],loading=false,error,onRetry,onChange,onApplied,onQC,onInspect,revision,session,onSession,initialCandidateId=null,authority=undefined}){
  const queue=useWorkbenchQueue(protocolId,revision,authority);
  const cumulative=queue.data?.contract_version===1;
  const saved=useRef(session||{}).current;
  const [selected,setSelected]=useState(saved.selected||[]),[active,setActive]=useState(initialCandidateId||saved.active||null);
  const [exports,setExports]=useState(saved.exports||{}),[dialog,setDialog]=useState(null);
  const drafts=useRef(saved.drafts||{}),snapshot=useRef(null);
  const items=cumulative?queue.data.candidates.filter(item=>item.pending_epoch_count>0):activeProtocolSuggestions({suggestions}).filter(item=>item.protocol_uuid===protocolId);
  const worklist=cumulative?items.filter(item=>selected.includes(reviewKey(item))):reviewWorklist({suggestions:items},selected);
  const current=items.find(item=>item.candidate_revision_uuid===active)||(cumulative&&active?{candidate_revision_uuid:active,protocol_uuid:protocolId}:null);
  snapshot.current={selected,active,exports,drafts:drafts.current};
  useEffect(()=>{onSession?.(snapshot.current);},[selected,active,exports,onSession]);
  const remember=useCallback(value=>{drafts.current={...drafts.current,[active]:value};onSession?.({...snapshot.current,drafts:drafts.current});},[active,onSession]);
  function toggle(item){const key=reviewKey(item);setSelected(previous=>previous.includes(key)?previous.filter(id=>id!==key):[...previous,key]);}
  const next=worklist.find(item=>item.candidate_revision_uuid!==active);
  const target=dialog&&items.find(item=>reviewKey(item)===dialog.key);
  return <div className="incoming-workbench">
    <header><div><div className="eyebrow">PROTOCOL WORKBENCH</div><h1>Needs review</h1><p>Review an incoming proposal, export it independently, then deliberately update the main dataset.</p></div><button disabled={loading||queue.loading} onClick={()=>{queue.reload();onRetry?.();}}>Refresh queue</button></header>
    {cumulative?<p className="incoming-contract-note">{number(queue.data.pending_cell_count)} distinct cells · {number(queue.data.pending_epoch_count)} incoming epochs awaiting review across saved proposals. Review decisions live in your actor draft; acceptance adds eligible incoming epochs to main.</p>:<p className="incoming-contract-note">This queue shows the latest saved proposal for this protocol. Earlier unmerged updates and durable review decisions require the cumulative review service. Closing review leaves the proposal pending. Viewer selections are session state.</p>}
    {queue.error&&<p className="incoming-contract-note" role="status">Cumulative queue unavailable: {queue.error}. {cumulative?'The previous queue receipt remains visible; refresh before continuing.':'Showing the current legacy proposal only.'}</p>}
    {error&&<div className="error" role="alert">{error}<button onClick={onRetry}>Retry</button></div>}
    {(loading||queue.loading)&&<p role="status">Loading current proposals…</p>}
    {!cumulative&&dialog&&target&&<IncomingExportDialog key={dialog.key} item={target} state={exports[dialog.key]} onState={value=>setExports(previous=>({...previous,[dialog.key]:value}))} onClose={()=>setDialog(null)} onChanged={onChange}/>}
    {!active?<>
      {!!worklist.length&&<div className="incoming-worklist"><span>{worklist.length} selected proposals · each reviewed independently</span><button onClick={()=>setActive(worklist[0].candidate_revision_uuid)}>Review selected</button></div>}
      {!items.length&&!loading&&!queue.loading&&!error&&<p>No current incoming proposals need review.</p>}
      {items.map(item=>{const key=reviewKey(item),counts=item.diff_counts||{},state=exports[key];return <section className="incoming-proposal" key={key} aria-label={`Incoming update for ${humanize(item.protocol_name)}`}>
        <header><label><input type="checkbox" checked={selected.includes(key)} onChange={()=>toggle(item)}/> {humanize(item.protocol_name)}</label><strong>{item.status==='stale'?'Refresh required':item.deferred?'Deferred':'Pending review'}</strong></header>
        <p>{item.source_filename||'Imported recording'} · {time(item.created_at)}</p>
        <div className="incoming-counts"><span>+{number(counts.added)} epochs</span><span>−{number(counts.removed)} epochs</span><span>{number(counts.changed)} metadata changes</span></div>
        <p>Base <code>{item.baseline_revision_uuid}</code> · proposal <code>{item.candidate_revision_uuid}</code></p>
        <div className="incoming-actions"><button className="primary" disabled={cumulative||item.status!=='pending'} onClick={()=>setDialog({key})}>Export</button><button disabled title="Requires an authoritative additive acceptance contract">Accept & export</button><button onClick={()=>setActive(item.candidate_revision_uuid)}>Review first</button></div>
        <p className="incoming-contract-note">{cumulative?'Review the frozen incoming cohort to save selections and preview additions to main. Incoming-only export is awaiting its versioned service.':'Export uses the full saved candidate. Add selected incoming epochs to main and accept all require the additive review service. The existing full-proposal update is a replacement operation.'}</p>
        {state?.exported&&<p role="status">Export saved: <a href={state.exported.download_url} download>{state.exported.name||'Download artifact'}</a></p>}
      </section>;})}
      {cumulative&&queue.data.next_cursor&&<button disabled={queue.loading} onClick={queue.more}>Load more proposals</button>}
    </>:queue.loading&&!queue.data?<p role="status">Loading the review service before opening this proposal…</p>:current?(cumulative?<FrozenIncomingReview capabilities={queue.data.capabilities} key={active} projectId={projectId} protocolId={protocolId} item={current} revision={revision} onChange={onChange} onQC={onQC} onDefer={()=>setActive(null)} onNext={next?()=>setActive(next.candidate_revision_uuid):null} session={drafts.current[active]} onSession={remember}/>:<MetadataExplorer key={active} projectId={projectId} undoScopeId={`incoming:${active}`} protocols={protocols} revision={revision} initialRevisionId={active} initialProtocolId={protocolId} incomingReview={current} onDefer={()=>setActive(null)} onNext={next?()=>setActive(next.candidate_revision_uuid):null} session={drafts.current[active]} onSession={remember} onChange={onChange} onProtocolApplied={onApplied} onQC={onQC} onInspect={onInspect} onExit={()=>setActive(null)}/>):<div role="status"><p>This proposal is no longer in the current pending queue. Its saved revision remains in candidate history. Refresh the queue to check the current binding.</p><button onClick={()=>setActive(null)}>Back to queue</button></div>}
  </div>;
}
