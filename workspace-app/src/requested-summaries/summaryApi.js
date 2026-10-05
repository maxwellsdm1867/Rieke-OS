/**
 * Public requested-summaries entry; see ./AGENTS.md for the complete interface,
 * identity, cancellation and authority contract and executable consumer examples.
 */
import {api} from '../api.js';

// Additive service contract. Native preview/save/run/full catalogs stay intact.
export const summaryApi={
  submit:(body,signal)=>api('/explore/summaries',{method:'POST',body,signal}),
  poll:(id,signal)=>api(`/explore/summaries/${encodeURIComponent(id)}`,{signal}),
  cancel:id=>api(`/explore/summaries/${encodeURIComponent(id)}/cancel`,{method:'POST',body:{}}),
};
