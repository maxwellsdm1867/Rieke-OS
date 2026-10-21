import {number} from '../../api.js';

// Shared by Overview/import cards and the prepared Workbench review. Callers
// retain their current queue or candidate fences; this panel grants only consent.
export default function FinishReviewConfirmation({count,disabled=false,cancelDisabled=false,onConfirm,onCancel}){
  return <section className="incoming-selection-review" aria-label="Finish reviewing"><strong>Leave out {number(count)} remaining epochs?</strong><span>This finishes this batch. Future updates show new arrivals; you can explicitly review left-out epochs again.</span><button className="primary" disabled={disabled} onClick={onConfirm}>Leave out &amp; finish</button><button disabled={cancelDisabled} onClick={onCancel}>Keep reviewing</button></section>;
}
