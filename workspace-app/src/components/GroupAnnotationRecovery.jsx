import {useState,useSyncExternalStore} from 'react';
import {groupAnnotationRecovery} from '../group-save/groupAnnotationRecovery.js';
import {number} from '../api.js';
import './GroupAnnotationRecovery.css';

// Always mounted by the application header, independently of tag dialogs and
// of the diagnostic undo preference. Retry sends the original project/body.
export default function GroupAnnotationRecovery(){
 useSyncExternalStore(groupAnnotationRecovery.subscribe,groupAnnotationRecovery.version);
 const [error,setError]=useState('');
 const rows=groupAnnotationRecovery.view(),project=groupAnnotationRecovery.currentProject();
 async function retry(operation){try{setError('');await groupAnnotationRecovery.retry(operation);}catch(failure){setError(failure.message);}}
 return rows.length?<div className="group-annotation-recovery" aria-label="Group tag save recovery">{rows.map(row=><div key={row.operation_uuid} role={row.status==='unconfirmed'?'alert':'status'}><strong>{row.status==='pending'?'Saving':row.status==='rejected'?'Refused':'Unconfirmed'} group tag “{row.tag}” · {number(row.count)} epochs</strong><small>Original author {row.profile_uuid} · {row.error||'The complete operation is still saving.'}</small>{row.status==='rejected'?<button onClick={()=>groupAnnotationRecovery.dismiss(row.operation_uuid)}>Dismiss refused group save</button>:row.project===project?<button disabled={row.status==='pending'} onClick={()=>retry(row.operation_uuid)}>Retry original group save</button>:<small>Return to the original project to confirm this operation.</small>}</div>)}{error&&<p role="alert">{error}</p>}</div>:null;
}
