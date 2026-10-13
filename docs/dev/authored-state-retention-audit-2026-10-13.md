# Authored-state retention audit

2026-10-13, local combined candidate on `codex/ui-cache-design`. Scope: authored
input in the live App dependency closure, its warm retention and its actual
checkpoint/restore ownership. An eviction guard alone does not persist a field.

## Field inventory

| Screen / fields | Before audit | Current owner and reset semantics |
| --- | --- | --- |
| Inspector annotation composers and dataset-tag text | Already in `annotationDrafts` / `curationTagDraft` snapshots | Existing Inspector session remains owner; no duplicate store. |
| CellQC standalone tag composer | Local text; guard protected hiding/eviction, explicit Quit lost it | Authored field keyed by exact epoch/cell/scope; same tag field restores after disk roundtrip. |
| Tree group/individual epoch tags | Local composer destroyed when preview is released | Authored text keyed by captured protocol/query/path/kind plus exact individual epoch or cell identity. Reopening must obtain fresh group target/preview; no preview UUID or mutation authority is restored. Sibling epochs cannot share text. |
| MetadataExplorer query/name/layout | Already in explorer snapshot | Existing owner retained. |
| PredicateDialog edits before Search | Internal AST never reached outer snapshot | Bounded authored JSON text scoped by editor/protocol/frozen context. Explicit successful Search transfers to existing parent owner and retires draft; no preview or search runs on restore. |
| QueryPresetDialog name/description/pin display choice | Local fields; resolve response could replace restored/user text | Exact preset UUID or predicate identity. Canonical `adopt` is not authored input; user edits survive refresh. Validated successful save retires entries; failed save preserves them. Replacement-layout confirmation remains transient. |
| Protocol export name/format/filters | Already in protocol snapshot | Existing Protocol owner remains; no duplicate. |
| Candidate export name/format | Guarded local state only | Exact candidate UUID; defaults and same labels never identify a candidate. Successful export retires fields. |
| Incoming/Workbench export name/format before Submit | Local; Workbench published options only when submitting | Exact protocol/candidate identity. Existing accepted-operation recovery remains separate. Successful export retires fields; failures preserve. Approval mode/removal confirmation is not added to authored drafts. |
| New pinned protocol name | Local | Exact candidate identity; successful creation retires name. Multi-protocol confirmation remains transient and requires fresh review. |
| DataStores lifecycle reason | Local; pending action guard only | Exact source SHA/action text. Successful recorded state change retires reason. Reopening is explicit with current source/version; pending action, delete confirmation and permissions are not restored. |
| Project setup name/directory/root text | Local shell fields | Existing project-shell checkpoint scope; completed creation clears name/directory. Only text restores after explicit reopen; no project action replays. |
| ProjectFolder open/move/source/destination text | Local shell fields | Project UUID and explicit initial workflow identity. Inspection results, relocation choice and transfer execution are not restored. |
| New annotation-author name | Local profile dialog | Project-shell authored text; successful creation clears it. Selected profile authority remains its existing owner. |
| Tag exchange export scope/format | Local options | Bounded per-view options; import file contents, filename/handle, preview token and import consent are excluded. |
| Selection mask dialog | No independent authored name/text | Immediate file commands retain existing owner; no new persistence required. |
| H5 import queue | File handles and accepted job state, not a text editor | Existing import/job owners. Unaccepted OS file selections are not serialized or replayed. |
| Detached folder browser | Separate transient chooser root | Deliberate boundary: unaccepted temporary path/name and picker navigation are not checkpointed or automatically reopened. A chosen path returns to the owning form's persisted field. File handles remain unpersisted. |

## One checkpoint, bounded ownership

The existing `createWorkspacePresentationSessions` owner adds named
`readDraft`/`rememberDraft` accessors and optional `authoredDrafts` checkpoint
entries. `useAuthoredDraft` binds fields to retained routes; `AuthoredDraftScope`
binds project-shell dialogs outside those routes. The existing native DraftStore
still owns disk identity, atomic replacement, corruption recovery and its 2 MiB
whole-draft limit. No second store, resource cache or scientific table is added.

Authored values are strings/booleans; keys include stable entity identity.
Limits are 256 entries, 8 KiB encoded key, 16 KiB text and 512 KiB aggregate.
A rejected write preserves local text and blocks checkpoint acknowledgment instead
of silently evicting old unfinished work. Correcting/clearing that field restores
save eligibility. Exact deleted epoch/cell identities prune their draft entries.

Canonical defaults use `adopt`, which preserves edited/restored text and does not
consume draft capacity. Confirmed successful submissions use `clear`; errors keep
the draft. This distinction prevents ordinary completed work from accumulating
forever and eventually blocking Quit. UI text never grants author identity,
scientific membership, permissions, current revision, preview lease or consent.

## Behavior evidence and lifecycle classifications

`workspace-app/src/authoredDrafts.test.js` exercises the actual DraftStore with
fresh temporary directories, the real renderer draft session and new presentation/
component lifetimes. It covers CellQC tag text, candidate export fields, saved
query text, the unsubmitted predicate editor, sibling-epoch group-tag isolation,
bounded failures and canonical hydration/success retirement. Restores submit no
annotations, queries or exports. These are real disk roundtrips with controlled
read responses; they are not native Electron restart or power-loss qualification.

For the retained-lifecycle inventory:

- `presentation/useAuthoredDraft.js`: **authored presentation**. Field identity and
  local baseline survive Activity effect disconnects; late saved-view loads are
  superseded by local authored intent; callbacks capture their entity identity; canonical hydration and
  explicit save retirement are distinct from user editing. Behavior tests:
  `authoredDrafts.test.js`.
- `annotations/ui/AnnotationTags.jsx`, export name/format editors, source reason,
  query/preset/name and shell form bindings: **authored presentation**. Persist
  only fields listed above; existing request/operation effects must still renew
  authority. Behavior tests: `authoredDrafts.test.js`, `retainedControls.test.js`,
  `predicateDialogLifecycle.test.js`, existing command/recovery suites.
- `annotations/ui/TreeGroupTags.jsx`: **authority release plus retained text**.
  Preview release and fresh target verification remain required; authored identity
  excludes ephemeral selection UUID while individual epoch identity remains exact.
  Behavior test: sibling-epoch disk/reopen case in `authoredDrafts.test.js`.
- `retainedWorkspaceViews.js` and App shell wrapper: **presentation ownership**.
  Pass the existing owner and scope; no draft persistence from component cleanup.
  Existing `retainedWorkspaceViews.test.js` checks hidden/busy/eviction behavior;
  the new roundtrip suite distinguishes it from persistence.

Remaining qualification belongs to the combined implementation: full frontend/
architecture gates, native restart/quit, memory pressure and scientific operation
recovery. Historical source receipts do not qualify this new candidate.
