export default function SummaryStatus({state,label='Metadata summaries'}){
  const text={idle:'unavailable',pending:'pending',ready:'ready',cancelled:'cancelled',stale:'stale; refresh to use the current generation',failed:'failed'}[state.status]||'unavailable';
  return <div className="metadata-summary-status" role="status" aria-live="polite">
    <span>{label}: {text}{state.error?` · ${state.error}`:''}</span>
    {state.status==='pending'&&<button type="button" onClick={state.cancel}>Cancel summaries</button>}
    {['failed','stale','cancelled'].includes(state.status)&&<button type="button" onClick={state.retry}>Refresh summaries</button>}
  </div>;
}
