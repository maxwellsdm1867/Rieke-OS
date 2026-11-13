# Protocol action refresh regression repair

Base: installed source `deb76e619ec5276fa4de745f34bedbf7026196df`.
Checkout: `codex/protocol-state-refresh`, isolated managed worktree.

## Findings and changes

- New pinned creation used the membership-only completion clock introduced in
  `82ddc88` (2026-10-18). The root overview feeding the sidebar defers populated
  membership summaries off Overview, so new protocol inventory stayed absent.
  New UUID completion now emits structure; existing UUIDs remain membership-scoped.
- Rename wrote the managed file and audit, then assigned into a frozen protocol
  entry. The immutable publication introduced in `f593ed7` (2026-10-18) rejected
  that assignment after persistence. Rename now prepares a replacement frozen map
  and publishes it only after successful file/audit writes. UUID/query/binding and
  membership are unchanged; existing audit-failure restoration remains intact.
- Retained Search draft previews omitted the workspace revision from their key.
  Returning after rename attempted row reads with a stale predicate witness.
  Visible results now renew after known changes, retaining annotation holds and
  suppressing previews while the editor is open. Interrupted reads restart on
  Activity reveal; completed unchanged results remain reusable.
- Native existing-protocol Update refused its own just-reviewed comparison.
  Apply unconditionally refreshed the service, which can republish/normalize a
  new pinned protocol and change its v5 publication token. Apply now uses the
  existing source-verification preflight; changed sources still refresh and reject
  stale comparisons. A bounded managed target manifest check retains detection
  of external edits, deletion or removal during source refresh. Binding CAS and
  transactional revision checks remain intact.

## Native observations before combined integration

Owned source Electron diagnostic at
`/private/tmp/disco-retention-native-refresh-gELswh`, isolated HOME/userData,
independent APFS-cloned runtime; installed application was neither replaced nor
modified. Source Electron was **44.5.0**, older than the candidate's pinned 44.9.2.
This is diagnostic native behavior, not final packaged qualification.

All UI actions used CUA. A donor-free synthetic H5 with 63 epochs, 2 cells and
126 responses passed its parser oracle and was imported into an owned project.
Search → Export → Create pinned protocol produced `Native refresh created`,
immediately visible in Pinned, breadcrumb, tab heading and prepared Overview
(63 epochs, 2 cells). Organize → Rename → Save changed all those labels to
`Native refresh renamed` without Refresh metadata or navigation.

Returning to retained Search exposed the stale-preview failure above. A new
explicit query narrowed to Synthetic cell A (61 epochs); Update pinned protocol
showed the correct 2 removals and required removal consent, then failed with
the unexpected stale comparison described above. No binding update was accepted.
The additional preview and apply fixes require combined-candidate native retest.
Ordinary Cmd-Q completed with Electron exit 0. The owned fixture is retained for
coordinated import, selection and final save verification, then cleanup by the
integration owner.

## Focused evidence

- 12 frontend workflow/sidebar tests passed (new inventory propagation, existing
  scoped membership request ledger, sidebar creation/rename controls).
- 14 requested-summary lifecycle tests passed, including one known-change
  renewal, hidden deferral, interrupted-read reconnect, ignored retired response,
  annotation hold, one manual refresh, and no previews during ordinary editing.
- The final requested-summary plus lifecycle-receipt check passed 18 cases under
  pinned Node 24.13.0, including an editor-open workspace revision change.
- 21 protocol-binding plus prepared-rename tests passed; all 21 prepared-overview
  tests passed before adding the apply regression.
- New native-v5 HTTP apply regression reproduced 409 before the preflight fix,
  passes after it, and still rejects a source-verification publication change.
  Actual target manifest edits/deletion and a missing refreshed target return 409
  without changing binding membership.
  SQL generation locks and source verification are explicit fixture doubles;
  actual native persistence is a separate gate.
- Final backend check passed all 88 cases across prepared overview, protocol
  binding and the full HTTP API suite. The shared HTTP fixture now persists its
  declared managed protocol manifest; file-list expectations include that file.
- Reviewed architecture byte witnesses change only workspace_api owner hashes;
  observer selectors, ASTs, targets and origins remain unchanged. Lifecycle
  receipts record the new result-read effect and unchanged App effect ownership.

Architecture guard check passed (metadata, Python, JavaScript). Raw final backend
log and guard JSON are retained in the adjacent evidence directory.

Required final core/million comparisons and native combined-candidate evidence
belong to coordinated integration. No performance or release qualification claim
follows from these focused checks.
