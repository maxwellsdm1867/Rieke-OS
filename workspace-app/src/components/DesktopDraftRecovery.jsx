import {useState} from 'react';
export default function DesktopDraftRecovery({draft}){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function act(operation){
    setBusy(true);setError('');
    try{const result=await operation();if(result?.ready===false)setError(result.reason||'The app is waiting for its active work to finish.');}
    catch{setError('The saved view could not be recovered. Its existing copy is preserved.');}
    finally{setBusy(false);}
  }
  return <main className="project-launcher"><section className="section" role="alert" aria-labelledby="draft-recovery-title">
    <h1 id="draft-recovery-title">Saved view needs recovery</h1><p>{draft.message}</p>
    {error&&<p className="error">{error}</p>}
    <div className="protocol-heading-actions">
      {draft.resetAllowed?<button className="primary" disabled={busy} onClick={()=>act(draft.startFresh)}>Start with a new view</button>:<button className="primary" disabled={busy} onClick={()=>act(draft.retry)}>Retry saved view</button>}
      <button disabled={busy} onClick={()=>act(draft.quitPreserving)}>Keep saved view and quit</button>
    </div>
  </section></main>;
}
