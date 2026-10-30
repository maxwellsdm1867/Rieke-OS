# Retained scientific project documents

`project-views.cjs` owns a bounded set of live scientific documents for one native
window. Main supplies verified backend bindings, Electron view construction,
draft preparation and lifecycle admission. It does not open/close project
processes, derive scientific authority or persist scientific data.

`ProjectViews.activate(binding,url)` serializes activation. Identity includes
project UUID, canonical project path, desktop session, PID, process creation time
and origin. A warm hit reuses its exact WebContentsView and document. A cold view
loads before replacing the visible view. Recovery/quit admission is checked both
before and after load. Visibility notifications identify the sending document;
only its native host owns bounds and native window controls.

`desktop:activate-retained-project` / `activateRetainedProject({projectUuid,path})`
is a retained-only project-switch entry. It validates the exact normalized path
and UUID, finds an existing owner only in the caller's native host, and authorizes
that owner's stored origin. It never inspects/opens a project folder, creates a
WebContentsView or calls `loadURL`. A genuine absent or cleanly LRU-evicted view
returns `{activated:false}` so the existing cold-open flow may run.
When Electron lacks WebContentsView, a validated active scientific BrowserWindow
also returns that cold miss; missing view state on supported Electron still rejects.

`ProjectViews.activateRetained(owner,authorize)` serializes authorization and
attachment with ordinary activations. It captures the owner, binding and lifecycle
generation, then checks them again after awaited authorization and before showing
anything. Main also captures the requesting active document, its activation token
and main frame, and checks current supervisor bindings on both sides of the await.
A different child on a reused port cannot replace the captured target. An earlier
request cannot steal focus after the caller changes, even if it later reappears.
Closing, crashed, replaced, stale, recovery or Quit states reject rather than
reporting a cache miss. Only acknowledged LRU disposal carries the clean-eviction
marker. No backend or scientific authority is inferred from retained DOM.

The default cap is three documents, including a retained launcher. Clean inactive
LRU documents are disposed only after a positive draft receipt. Draft failures,
busy workflows or unconfirmed writes are soft-cap exceptions. Eviction runs after
activation without blocking the visible return. It never shuts down the backend.
A document reactivated while a checkpoint is pending wins over eviction.

`prepareClose({projectUuid,path})` checkpoints the exact matching retained target,
including hidden documents. It blocks reactivation until cancellation or confirmed
closure. Main's `desktop:confirm-project-closed` requires authenticated root health
that no longer reports that UUID/path. Because the close response precedes HTTP-server exit, confirmation polls within the supervisor drain deadline and revalidates the captured root identity on every response. A live child, changed root, failed request or expired deadline retains the fenced view. A renderer declaration alone cannot
release a view. Closing the active target first activates the launcher, because
the old renderer cannot navigate after its WebContents is destroyed.

The preload adds `activateProject`, `activateRetainedProject`, `projectVisibility`, `onProjectVisibility`,
`prepareProjectClose`, `cancelProjectClose`, `confirmProjectClosed`, and
`onProjectResume`. These keep the existing origin/main-frame admission. Native
host windows and scientific renderer owners are distinct collections. IPC,
request headers, downloads and clipboard permission use exact registered owners;
scientific owners are additionally checked against the current backend binding.
Clipboard writes and user-facing project actions require the active document.

Each retained owner participates in strict replacement and bounded explicit Quit.
`DraftBarrier.prepare` now accepts optional `purpose:'project-checkpoint'` for a
view checkpoint; ordinary quit retains its previous payload and closing behavior.
The renderer uses a scoped unmount guard for checkpoints, preserving pending-write
and workflow refusal. Main sends `desktop:project-resume` after declined eviction,
failed preparation or explicit cancellation. Accepted work remains owned by its
existing operation lifecycle. Checkpoint persistence never grants mutation consent.

Hidden saves do not choose the startup project. Activation remembers the visible
project; visible draft saves can refine its last page. Global recovery detaches retained documents and fences new actions while preserving
healthy unsaved drafts for checkpointing. A crashed renderer stays unavailable in
lifecycle accounting; other projects remain live. If the active renderer crashes,
the launcher is shown. Reopening the failed document requires quitting and reopening
Disco. Draft barriers still checkpoint healthy owners while reporting the failed
owner as unconfirmed; strict replacement cannot claim a clean draft receipt.

A backend crash clears the supervisor's authenticated origins. Draft persistence
does not need the backend, so `desktop:save-draft` and `desktop:drafts-ack` (only)
also admit a retained owner at the exact binding origin recorded when it
registered; every other channel still requires a current origin. Recovery Retry
checkpoints retained owners (`project-checkpoint`) while their old bindings still
authenticate, and after a successful replacement start disposes owners whose
binding no longer matches the new root. A checkpoint that was not acknowledged
keeps Quit's "last saved view unconfirmed" warning for the rest of the session.
A failed Retry keeps the owners and their draft path.

**Invariant: one project = one draft writer.** The app has one live document per
project (single-instance lock with second-instance focus, one native window,
denied window.open, ProjectViews reuse per binding). The only way a second document
for a project's saved-view scope (UUID + canonical path; the launcher has its own
scope) can appear is a new backend binding while the previous document is still
retained. Main records the writer per scope at registration. A newer owner's
`desktop:save-draft` waits until the previous owner's final `project-checkpoint`
completes or times out (then declared unconfirmed, which Quit reports). The
previous owner may save only while that checkpoint is outstanding; afterwards its
saves are refused and it is disposed. Retry disposes stale owners before the new
root's documents register, so they never overlap. Browser/dev mode has no desktop
bridge and therefore no draft writer. Renderer skip-unchanged relies on this:
no other document writes the same saved view between a session's saves.

Host teardown can call `clear` from the native window’s `closed` event. Detaching
an active view first checks whether the host is already destroyed; both active
and detached WebContents still receive normal closure and are removed from
lifecycle accounting. Suspension likewise avoids accessing a destroyed host while
preserving the documents for their explicit close/checkpoint lifecycle.

Public behavior checks:

```
node --test desktop/tests/project-views.test.cjs desktop/tests/main-retained-views.test.cjs desktop/tests/security.test.cjs desktop/close/tests/*.test.cjs
```

These tests use Electron/transport doubles and disposable directories. They do
not qualify native attachment, packaged transport, memory limits, restart hydration
or scientific cleanup. Native evidence and required repository gates belong to
the exact combined candidate. The cap is a policy bound, not a measured memory
budget; large document memory remains a separately measured limit.
