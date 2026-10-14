# Retained UI and last-good project overview

This implementation follows the [adversarially agreed scope](ui-cache-review-resolutions.md)
on the [combined local source](ui-cache-integration-2026-10-13.md). It preserves
newest local UI work plus release/startup and managed-recording changes in the
isolated `codex/ui-cache-design` worktree. It does not modify the installed app or
real scientific projects.

## Retained presentation ownership

`retainedWorkspaceViews.js` owns up to eight recent route presentations and
Protocol's visited Overview, Inspect and Workbench panels. Each destination keeps
its own route callbacks, history/undo identity and saved presentation. Explicit
inspection, recipe, search and merge intentions still have separate activation
semantics. Protected dirty or busy views may exceed the soft limit. In-progress
writes remain mounted even when hidden; hidden controls/dialogs are inert and
unmount guards remain registered above suspended effects.

Completed, explicitly named display reads can survive effect restarts. Scientific
browse contexts, pages and custom request owners retain their existing freshness
checks. Metadata/trace cache keys, actor identity, relevant revisions, explicit
reload and structural change remain invalidation boundaries. Retained layout and
summary presentation prevents those checks from tearing down the last successful
Inspector or trace canvas. Internal native project activation does not force an
unrelated overview reload; real online/out-of-app freshness checks remain.

Desktop [ProjectViews](../../desktop/PROJECT_VIEWS.md) keeps three recent live
project documents, including the launcher. Switching uses the existing exact
project/service admission but attaches the retained document. It does not wait
for the old renderer's accepted writes or save its draft as a navigation barrier;
that renderer continues owning its work. Browser full-document navigation retains
its prior flush requirement. Eviction, explicit project closure and Quit retain
their draft/accepted-operation obligations.

Native UI measurement also exposed that retaining the document alone left the
ordinary folder inspection/open route in every warm project switch. The renderer
now asks the desktop to activate the exact retained UUID/path first. The serialized
native owner freshly authorizes its captured backend binding and rechecks the
initiating caller, target and lifecycle before attachment. This path cannot create
a replacement document. Only an explicit absent/clean eviction miss falls back
to folder inspection; closing, stale ownership and recovery errors remain errors.
Legacy desktop adapters without retained-view support explicitly use the existing
cold path after sender and lifecycle validation.

The early native 30-second return observation is not a valid performance baseline:
the discovery helper could wait for the target project label in the departing
document. Final comparisons must use the same corrected nonwaiting discovery
helper for both sources. Eliminating folder requests and measuring visible-switch
latency are separate checks.

A crashed document cannot destroy another project's unsaved UI. The failed owner
remains unconfirmed in lifecycle accounting; healthy owners still checkpoint.
Global recovery hides retained documents, fences new work, and cancels queued or
in-flight activations without discarding healthy state. Strict replacement still
requires all drafts and backend-stop evidence. Recovery-host version restoration
retains its existing verified path.

## Disposable overview snapshot

`presentation_cache.py` writes a single latest successful canonical overview per
physical project into desktop user state, outside scientific project files. Its
positive field allowlist contains only overview display fields. The namespace
includes canonical folder and manifest UUID; schema, checksum, payload/file bounds
and a short SQLite lock timeout make failures optional cache misses.

The shell can serve this snapshot before SQL or H5 access. The overview stays
mounted and inert until canonical startup and overview publication finish, then
updates its values in place. A saved overview never carries a query revision,
lease, frozen-membership proof or mutation capability. It remains only historical
display even after a same-path database restore. The first implementation does not
persist waveforms or grant scientific freshness across process restarts.

The existing annotation watermark still invalidates the epoch resource cache, and
some project revisions still fan out to several consumers. A complete dependency
invalidation matrix, including avoiding every raw-sample reread after annotation
changes, is not established by this implementation. The unchanged-navigation
receipts have that narrower scope.

The cap is per project (4 MiB payload, 12 MiB SQLite file). There is no aggregate
cache-root LRU yet; removed/moved project namespaces can accumulate. Deleting this
disposable cache loses no scientific or authored state.

## Startup demand repair

The full-App fixture exposed a pre-existing race during saved Protocol restoration:
an initial annotation refresh could invalidate and abort the first overview while
its hidden summary revision stayed unchanged. The resource effect then had no
reason to issue another request, leaving the shell waiting for data. A mounted
missing-data demand now restarts after invalidation; a previous successful display
can remain visible on refresh error. This reproduction is not proof that the same
race caused the earlier real SRM incident.

## Lifecycle drift prevention

The recurring failure was a mismatch between effect lifetime and presentation
identity. [React Activity](https://react.dev/reference/react/Activity) retains component state while disconnecting and
reconnecting effects. Existing effects sometimes treated setup as a new epoch,
candidate, search, or dialog: that erased edits, reopened collapsed sections, or
discarded navigation. Keeping busy owners mounted exposed the opposite problem:
their global keyboard listeners and portals could remain active while hidden.

`useSemanticReset(identity, resetPresentation)` is the narrow shared seam for
synchronous presentation changes. It remembers the last committed semantic
identity, including through StrictMode and Activity reconnect. It is not for
requests, timers, storage, cleanup, leases, authority, or consent. Those owners
still reconnect or revalidate normally. Successful immutable initial hydration
has a separate completion witness; aborted or failed reads never count as done.

The audit follows the actual App dependency closure, including inline route
components, shared helpers and owners outside Activity. The checked
[lifetime inventory](../architecture/retained-ui-lifetimes.json) records module
ownership, effect/reset sites and behavioral tests. `npm test` compares canonical
AST fingerprints for the entire closure, so changes in a callback helper cannot
slip through an unchanged hook call. New modules, changed dependencies and
unsupported module loading fail review. The gate exposes a read-only census;
there is no accept/update command. Review the change, its lifetime and its
behavioral evidence before updating a receipt.

The effect-site listing recognizes direct imported hooks, named import aliases,
React namespace calls, and the semantic-reset helper. It rejects common binding
escapes; arbitrary namespace rebinding or hook re-export composition is not a
complete semantic census. Whole-module fingerprints still require review for
those changes. The inventory is a review aid, not a static proof of correctness.

Behavioral checks cover same-identity hide/reveal, actual identity replacement,
changes while hidden, aborted/late replies, pending writes after departure,
hidden keyboard/Undo/modal/portal ownership, dirty eviction, refused checkpoint,
and restart without authority reuse. The independent review and findings are in
[the lifecycle audit](retained-lifecycle-independent-audit-2026-10-13.md).

Preparing the dual-channel UI check also exposed a missing persisted response-channel choice.
The existing trace preference now retains one last explicit epoch/stream UUID
pair. Restore selects it only after matching current descriptors; another epoch
or a missing UUID defaults to its first response, never to a matching label.
Warm mounted viewers retain their own selection. No samples or read authority
are persisted with the choice.

## Compact inspection correction

The baseline/candidate UI click-through exposed an inherited metadata overlay at
1100×760 that covered trace Count/Apply controls. Resizable panes now stay inline
whenever their minimum widths fit, with clamped display sizes and unchanged saved
preferences. The old 990px CSS overlay rule applies only to non-resizable layouts.
Below the combined pane minima, the existing narrow overlay remains; hiding the
tree lowers the inline threshold. The matched browser audit checks actual compact
geometry and control hit targets.

The same visual review found flex auto margins vertically centering short direct
page children such as Data stores. The retained wrapper now preserves their
original top alignment, full available width, max-width centering and natural
height. Protocol pane layout is unaffected. At tree widths up to 260px, Edit Tree uses
its existing labeled icon/tooltip so the adjacent Epochs and Split tree controls
remain unobscured. Actual CSS measurements at 180/220/223/260/270px verify all four
control centers and nonoverlapping label bounds; the labeled action remains at
270px.

## Native host teardown repair

The native audit’s cleanup exposed access to a destroyed BrowserWindow from its
`closed` handler. An isolated Electron reproduction confirmed that the exception
left the active WebContents alive after detached documents had closed. Retained
view teardown now checks host destruction before detaching, then normally closes
and unregisters every owned document. Draft and scientific shutdown coordination
still precede application exit. This fixes a native lifecycle defect that the
original window doubles did not model.

## Validation status

Authored text and display options use the existing project DraftStore checkpoint,
with stable entity keys and bounded capacity. Canonical default hydration does
not create unfinished work; validated successful submissions retire their fields.
Rejected persistence keeps text in memory and refuses a false successful flush.
Restoring these fields never reopens a confirmation or replays a command. The
[authored-state audit](authored-state-retention-audit-2026-10-13.md) records exact
owners, covered fields and the deliberate detached-folder-picker boundary.

### Completed retained-UI validation at `27a0117`

These receipts belong to clean source `27a0117a0b701b178089c7b0687fcf87886675ee`.
They establish the retained-UI checkpoint below. Later projection-contract
compatibility evidence is attributed separately in the following subsection.

- **Required regression gates:** the [core receipt](../../benchmarks/results/ui-retention-27a0117-core/benchmark.json)
  has no validation errors, with all ten cases passed and fixtures cleaned. The
  [pinned million-epoch comparison](../../benchmarks/results/ui-retention-27a0117-pinned/comparison.json)
  passed. Against combined baseline `ceaf776`, the [first comparison](../../benchmarks/results/ui-retention-27a0117-previous/comparison.json)
  flagged `tree.return_root` and `tree.change_splits`; the [investigation](../../benchmarks/results/ui-retention-27a0117-previous/investigation.json)
  and [complete matched repeat](../../benchmarks/results/ui-retention-27a0117-previous-repeat/comparison.json)
  are preserved. The repeat passed without changing thresholds or averaging away
  the first result. These are synthetic correctness/stress gates, not native latency qualification.
- **Actual browser click-through:** [candidate checks](ui-cache-design-evidence-2026-10-13/ui-audit-27a0117/candidate/browser/receipt.json)
  recorded 86 passes, five unsupported checks and no failures or blocked checks.
  All [22 paired visual sheets](ui-cache-design-evidence-2026-10-13/ui-audit-27a0117/comparison/comparison.html)
  were [reviewed](ui-cache-design-evidence-2026-10-13/ui-audit-27a0117/visual-review.json),
  covering Light, Dark, Fred and 1100×760 compact layout. The baseline's compact
  Apply occlusion remains recorded; the candidate's real control hit/click passed.
  Unsupported checks are four single-stream channel probes and Activity's missing
  fixture relation. This browser fixture does not qualify scientific writes,
  export/merge execution, real imports or widths below 1100px.
- **Full-App returns:** the [matched comparison](../../benchmarks/results/ui-retention-27a0117-app-comparison.json)
  preserves Inspector and canvas identity, scroll, expansion and sample window,
  while renderer requests fell from 5→4 for tab return and 7→4 for history return.
  Median elapsed actions nevertheless increased from 101.1→116.8 ms and
  147.0→163.3 ms (three samples each). This is a retention improvement, with no
  browser speedup established. The [baseline cold-restoration failure](../../benchmarks/results/ui-retention-27a0117-app-baseline/browser/receipt.json)
  after its successful warm samples remains a failure; the [candidate restore](../../benchmarks/results/ui-retention-27a0117-app-candidate/browser/receipt.json)
  passed. Its held-activation snapshot check is not native startup timing.
- **Native development Electron:** [empty-project lifecycle](../../benchmarks/results/ui-retention-27a0117-native-empty/receipt.json)
  and [populated dual-response UI checks](../../benchmarks/results/ui-retention-27a0117-native-populated/receipt.json)
  passed, including fresh-process restoration and orderly initial/restart exits.
  The latter verified exact trace values, retained scroll/channel/window and
  unchanged H5 bytes on a synthetic 63-epoch, two-cell fixture. In the
  [matched incremental fast-path comparison](../../benchmarks/results/ui-retention-native-comparison-27a0117.json)
  against `b504962` (which already retained documents), warm switch medians fell
  90.1→55.0 ms and 73.7→57.3 ms: 38.9% and 22.2%, three samples per direction.
  Renderer folder calls fell from two to zero; main-process health/authorization
  checks still run. The receipt separately preserves 26 expected quit-phase 503
  draining trace responses. This does not establish general waveform performance,
  native scale performance or the full improvement over `ceaf776`.

These `27a0117` results alone do not qualify later source, an installed package
or a production release. Earlier failed and superseded diagnostic receipts remain intact.

### Cache compatibility follow-up at `b026a29`

The [version-first-open investigation](project-version-first-open-2026-10-14.md)
now proves reuse of the original sealed source/native/typed caches across the
published 0.1.12 testing-prerelease upgrade on an owned 63-epoch fixture, with
unchanged scientific hashes/stats and exact dual-response trace values. It does
not demonstrate a cold-start speedup: first upgraded readiness remained 63.049 s,
and a same-version fresh stage reproduced 62.253 s versus 12.560 s on reopen
without rebuilding. The finer startup cause remains unresolved.

The [current core gate](../../benchmarks/results/ui-cache-compatible-b026a29-core/benchmark.json)
passed in 15.724 s and the [pinned million-epoch comparison](../../benchmarks/results/ui-cache-compatible-b026a29-pinned/comparison.json)
passed without review flags. The [comparison against previous candidate
`79449da`](../../benchmarks/results/ui-cache-compatible-b026a29-previous/comparison.json)
also passed both million-epoch lanes without review flags. Neither comparison
required a repeat. The 102 scoped metadata/compatibility checks, full architecture
check and packaged-source closure check also passed.
These unpackaged native-fixture and synthetic regression checks do not qualify
an installed release or establish general cold-start/waveform performance.
