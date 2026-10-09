# Recording import presentation and monitoring

Choose the existing entry for the responsibility:

- [importProgress.js](importProgress.js): terminal-state classification, actual counters, elapsed/
  stage display, polling delay and newly completed review candidates.
- [importReadiness.js](importReadiness.js): pinned protocol/suggestion display; [recordingIdentity.js](recordingIdentity.js):
  recorded dates and qualified cell labels shared by scientific views.
- [uploadRecording.js](uploadRecording.js): existing browser XHR/FormData submission and acceptance
  receipt; transfer bytes are separate from parsing or durable catalog completion.
- [useImportMonitor.js](useImportMonitor.js): bounded job-status reads and completion notification.
  [useImportQueue.js](useImportQueue.js): App-level sequential selection/upload/wait state.
- [useImportReviewStatus.js](useImportReviewStatus.js): last confirmed cumulative pending protocol count,
  reset on project change; proposal history is not a resolved-queue receipt.
- [ui/H5Inbox.jsx](ui/H5Inbox.jsx), [ui/ImportHistory.jsx](ui/ImportHistory.jsx), [ui/ImportStatusBar.jsx](ui/ImportStatusBar.jsx): existing inbox
  action, history and progress presentation, including the public progress meter.

## Contracts and dependencies

Only valid nonnegative bounded actual completed/total counters show percentages.
Missing counters do not become completion. Committed imports with failed/interrupted
follow-up remain distinct from unconfirmed catalog state. Preserve warning,
duplicate, interrupted and pending statuses, exact job UUIDs and source labels.
Date/cell display never synthesizes recorded identity or converts source units.

Upload progress reports browser-sent bytes, then awaiting_job; only a job UUID
receipt confirms acceptance. Inactivity, network/abort, malformed receipt and
unclassified server failures keep acceptance uncertain. Known request rejection
remains distinguishable. Queue progression waits for the matching terminal job,
stops on failure, refuses concurrent submission and never automatically retries
an uncertain POST. Existing XHR timers and upload lifetime remain unchanged.

Monitor GETs use their own eight-second timeout, abort on replacement/unmount and
retain last confirmed data on error. Existing 2.5/10-second polling and recovered
completion behavior remain unchanged. App owns the queue so route changes do not
lose chosen files. UI choice/review hints grant neither ingest nor acceptance
consent; backend import and incoming-workbench authorities stay separate.

Formatting/selection is in-process; XHR/clock/browser adapters are
local-substitutable, and jobs/upload/inbox endpoints are remote but owned.
KEEP the upload, monitor, queue and review-status interfaces: a single import facade
would make progress-only callers learn submission and reconciliation rules, while
removing these entries would repeat uncertainty and terminal-state policy. This
organization performs no H5 porting, ingestion, parser change or fixture expansion.

## Executable public examples

[importProgress.test.js](importProgress.test.js) and [importReadiness.test.js](importReadiness.test.js) use synthetic DTOs.
[uploadRecording.test.js](uploadRecording.test.js) replaces XHR/FormData with owned stand-ins; it sends no
recording. Retained review/route tests exercise the existing actual App workflow.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/recording-import/*.test.js src/importReviewStatus.test.js src/importMergeAppRoute.test.js
```

## Change and evidence procedure

Use the named file entries directly. Each keeps its existing exports and caller
contract; no barrel, forwarding layer or private demotion is introduced. The goal
is a clear interface with progressive disclosure of the responsibilities below,
not fewer exports or fewer lines. Co-location improves locality; moving these files
does not by itself establish deeper behavior or a performance improvement.

Read the relevant entry and executable public examples before editing. Preserve
identity, scientific meaning, errors, ordering and lifetime. Review any proposed
contract or runtime behavior change before implementation. Keep the existing tests
and their public interfaces; do not import test support into production. Root
integration owns catalog/ledger/navigation updates and aggregate frontend checks.
Run the listed commands from `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset,
only in the coordinated test lane. Native/packaged behavior, actual ingestion,
backend durability and performance remain separately qualified; these examples
use owned synthetic values and do not authorize deferred/native fixtures.

`ui/InspectImportButton.jsx` binds the imported-data card's normal click to
inspection of the displayed frozen candidate. Holding for one second (pointer,
Space or Enter) issues a single ephemeral source-specific merge request. Early
release keeps inspection; leave/cancel/blur/Escape, changed identity or disabled
state, and unmount retire the timer. The trailing click never also inspects after
a completed hold. This gesture is on the post-import recording card; choosing H5
files and the existing upload queue remain separate.
`inspectImportButton.test.js` checks the threshold and cancellation lifetime.
