# Predicate traces, Live metadata, and the cache boundary

This note separates the user-visible regression from the architecture violation found while assembling Disco 0.1.12. The packaged application candidate is `add33d153ae8f533d5c4a68c50690764323c4336`.

## The behavior that must work

A search predicate produces matching epochs. Selecting an epoch must display its recorded response with **Live metadata off**. Moving to another matching epoch must change the response. Turning Live metadata on may load the full metadata panel; turning it off again must not stop subsequent trace navigation or leave a previous epoch's response active.

Live metadata controls full metadata reads. It must not control whether the trace viewer receives the small recorded stream descriptor needed to request a waveform.

## Where the regression came from and how it was fixed

The predicate matching-page projection in `python/disco/navigation/matching_epochs.py` omitted `streams`. The frontend already supported constructing a lightweight inspection descriptor from a matching row, but the predicate page did not supply that descriptor. With full metadata disabled, that route could not provide the trace viewer with the recorded response stream. Loading full metadata could conceal the omission.

Commit `e86232f448d7205e9ca8851d81945da8186d8713` adds the existing `streams` field to the bounded matching-page projection. It does not turn full metadata on, fetch waveform samples while building the page, broaden the predicate, or change scientific membership. This fix belongs to the navigation projection owner.

The backend regression test, `MatchingEpochTests.test_matching_pages_supply_trace_descriptors_without_details_or_waveform_reads`, asserts that the matching page supplies the same stream descriptors as the protocol page. It makes both full epoch-detail loading and H5 opening fail if invoked during page construction. It also covers a streamless next epoch and verifies that full metadata fields remain absent.

## Where the separate boundary violation came from

Commit `be4042bb901c61759b79f62a281d1c7f57add520` improved shared cached zoom and pan. Its short-window cache handling added a direct `resourceCache.js` dependency to `traces/ui/TraceViewer.jsx`. That put cache lookup, descriptor validation, retry and generation-bound admission in presentation code.

The existing trace contract keeps the shared cache lifecycle outside the trace UI. The release architecture check rejected this import in GitHub run `38209276440`:

> `TraceViewer.jsx: forbidden dependency workspace-app/src/resourceCache.js; contract traces at workspace-app/src/traces/AGENTS.md`

Passing behavioral tests did not make that dependency valid. The predicate projection fix and this cache ownership problem are separate changes; the predicate fix did not introduce the forbidden import.

## The boundary-preserving repair

Commit `add33d153ae8f533d5c4a68c50690764323c4336` moves the unchanged canonical short-window policy into `requestTraceWindow` in the existing `workspace-app/src/api.js` resource adapter. The viewer supplies its epoch, stream, requested window, revision and cancellation signal.

The adapter owns warm lookup, source/descriptor matching, fresh retry, cancellation checking and generation-bound cache admission. The viewer owns presentation and selection of the window it needs. Scoped/imported request owners and chunked trace reads keep their existing paths. The repair does not widen the import allowlist or grant a scoped viewer access to the global cache. The trace contract and existing adoption records now describe this entry point.

## Catch this while developing

1. Start at the local owner contract before adding an import. For this workflow read `python/disco/navigation/CONTRACT.md`, `workspace-app/src/epoch-browser/AGENTS.md`, and `workspace-app/src/traces/AGENTS.md`.
2. Identify the missing responsibility before choosing a file. Missing lightweight stream descriptors belong to the bounded navigation projection. Shared cache admission belongs to the resource adapter. Full metadata policy and trace rendering remain separate.
3. Run `python tools/architecture_guard.py check` immediately after changing cross-module imports, before committing or packaging. Do not wait for release CI. An import failure is a prompt to find the owning public entry, not to enlarge the allowlist.
4. Use an explicit pre-change base with `python tools/architecture_guard.py plan --base <base>` and the mapped tests. For the adapter extraction the mapped JavaScript run was `python tools/architecture_guard.py test --base e86232f --language javascript`.
5. Keep the behavioral regression test in the same iteration: Live metadata off, navigate A→B, enable it, disable it, navigate A→B again. Assert the selected epoch/stream and actual trace request at each step; assert that full-detail reads stay absent while Live metadata is off. Do not accept only a mounted canvas or a successful build as proof.
6. Review the dependency change separately from the behavior change. A correct-looking result can still move policy into the wrong module. Contract changes require independent review and updates to the existing adoption record.

## Evidence and limits

For `add33d1`, the architecture check, 69 focused frontend checks, 700 mapped frontend checks and fixed core correctness suite passed. Independent Standards and Spec source reviews reported no actionable findings. The focused suite includes Live-metadata-off navigation and toggling for main, Workbench and search, plus warm-cache adoption, stale-response rejection, and shared zoom/pan behavior.

The unmodified 0.1.12 package was checked in an isolated native project after importing a copied recording. A protocol predicate returned 334 epochs; epoch 1 and 2 rendered different recorded response streams with Live metadata off, then continued to navigate correctly after On/Off toggling. Enabling Live metadata loaded parameter values. A displayed sample matched the copied H5 recording using the packaged interpreter, and the original and copied file hashes were unchanged. Both matched million-epoch comparisons passed. Exact artifact checks and GitHub updater results are recorded separately in the release qualification report. Earlier source tests or screenshots are not evidence for the final package. This note does not claim stable release qualification or full native scientific-workflow coverage.

## Separate updater-test harness follow-up

GitHub candidate run `38211317227` passed architecture and frontend checks, then cancelled updater-observer tests because a pending promise had no referenced event-loop handle. This was reproduced with Node 22.12.0, the workflow's pinned version; the same original tests passed on the local Node 24 runtime.

The fake reporter uses in-memory streams, so it lacks the real child process pipe handles that keep an observer alive. The production polling timer is intentionally unreferenced. The test-only repair awaits observer closure with a bounded, referenced two-second deadline and clears it on completion. It neither changes production timers nor suppresses failed assertions. This follow-up is outside the immutable `desktop-test-v0.1.12` application tag; the app artifact remains bound to `add33d1`.

After the harness repair, all 10 observer tests and the full desktop suite (325 passed, one skipped, no failures or cancellations) passed on Node 22.12.0. The architecture check also passed.
